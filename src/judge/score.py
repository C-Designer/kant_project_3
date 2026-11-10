"""답안 묶음을 채점해 EvalRecord 목록을 만든다.

한 답안의 채점 순서
1. rules.precheck  : 서비스 오류면 AI를 부르지 않고 규칙대로 결론
2. Faithfulness    : RAGAS (ragas_eval.py). config.FAITHFULNESS_REPEATS번 채점해 평균
3. Judge 4항목     : 채점관 AI (judge.py)
4. 점수를 Langfuse 트레이스에 붙이기 (record_score)

실행 예
  uv run python -m src.judge.score --run <run_id> --workers 4
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, get_args

from src import config
from src.judge import ragas_eval
from src.contracts import EvalRecord, GroundTruth, RetrievalMode, RunRecord
from src.judge.judge import judge_one
from src.judge.rules import JUDGE_ITEMS, LLMCall, precheck, sum_usage, tag
from src.metrics.loader import load_ground_truth
from src.platform import llm as _llm
from src.platform import tracing as _tracing
from src.platform.llm import LLMResult


def llm_call(messages: list[dict[str, str]]) -> LLMResult:
    """judge가 AI를 부르는 유일한 지점: 팀 `platform.llm.call(kind="eval")`. 평가 호출은 서비스 사용량과 섞이지 않는 별도 트레이스로 남는다."""
    return _llm.call(messages, kind="eval")


def record_score(request_id: str, name: str, value: float | None, comment: str | None = None) -> None:
    """점수를 Langfuse 트레이스에 붙인다(`platform.tracing.record_score`). 기록 실패는 platform이 삼킨다(요청을 깨지 않음).

    value가 None(해당 없음·평가 불가)이면 보내지 않는다. Langfuse는 값 없는 점수를 거절하고,
    빈 값을 0이나 1로 바꿔 보내면 안 되기 때문이다. None과 그 이유는 eval.jsonl이 기준이다.
    """
    if value is None:
        return
    _tracing.record_score(request_id, name, value, comment)


DEFAULT_EVAL_DIR = config.DATA_DIR / "evaluation"


def load_ground_truths(eval_dir: Path = DEFAULT_EVAL_DIR) -> dict[str, GroundTruth]:
    """평가 폴더의 정답 JSON → {질문 id: GroundTruth}. 읽는 규칙은 metrics 로더 하나만 쓴다."""
    return {t.question_id: t for t in load_ground_truth(eval_dir)}


def score_one(run: RunRecord, truth: GroundTruth, llm: LLMCall, *, use_ragas: bool = True) -> EvalRecord:
    early = precheck(run)
    if early is not None:
        return early

    not_applicable: list[str] = []
    unscorable: list[str] = []

    # Faithfulness
    faith, faith_tokens, faith_runs = None, None, None
    if use_ragas:
        faith, faith_tokens, na, us, faith_runs = ragas_eval.faithfulness_repeated(run, llm)
        if na:
            not_applicable.append(tag("faithfulness", na))
        if us:
            unscorable.append(tag("faithfulness", us))
    else:
        unscorable.append(tag("faithfulness", "이번 실행에서 RAGAS를 끔"))

    # Judge 4항목
    judge, judge_tokens, failure = judge_one(run, truth, llm)
    if judge is None:
        unscorable += [tag(i, failure or "알 수 없는 실패") for i in JUDGE_ITEMS]
    else:
        for item, result in judge.items():
            if result.score is None:
                bucket = not_applicable if result.reason.startswith("해당 없음") else unscorable
                bucket.append(tag(item, result.reason))

    return EvalRecord(
        question_id=run.question_id,
        retrieval_mode=run.retrieval_mode,
        faithfulness=faith,
        judge=judge,
        eval_tokens=sum_usage(faith_tokens, judge_tokens),
        not_applicable=not_applicable,
        unscorable=unscorable,
        faithfulness_runs=faith_runs,
    )


def _unscorable_record(run: RunRecord, reason: str) -> EvalRecord:
    """채점하지 못한 답안: 모든 칸을 평가 불가 + 사유로 남긴다 (0이나 1로 바꾸지 않는다)."""
    return EvalRecord(question_id=run.question_id, retrieval_mode=run.retrieval_mode, faithfulness=None, judge=None,
                      eval_tokens=None, not_applicable=[], unscorable=[tag(i, reason) for i in ("faithfulness", *JUDGE_ITEMS)])


def _score_one_safely(run: RunRecord, truth: GroundTruth, llm: LLMCall, use_ragas: bool) -> EvalRecord:
    """한 답안에서 예상 못 한 오류가 나도 전체 채점을 멈추지 않고 그 답안만 평가 불가로 남긴다."""
    try:
        return score_one(run, truth, llm, use_ragas=use_ragas)
    except Exception as e:
        return _unscorable_record(run, f"채점 중 예상 못 한 오류: {type(e).__name__}: {e}")


def _record_scores(run: RunRecord, rec: EvalRecord) -> None:
    record_score(run.request_id, "faithfulness", rec.faithfulness)
    for item, result in (rec.judge or {}).items():
        record_score(run.request_id, f"judge_{item}", result.score, result.reason)


def reusable_prefix(runs: list[RunRecord], saved: list[EvalRecord]) -> list[EvalRecord]:
    """이미 채점된 결과 중 runs의 앞에서부터 질문·방식이 하나하나 맞는 구간만 돌려준다.

    결과는 runs 순서대로 저장되므로 '앞에서부터 같은 만큼'이 다시 쓸 수 있는 전부다.
    (같은 질문·방식이 여러 번 나오는 시험 데이터에서도 엉키지 않는다. 어긋나는 지점부터는 다시 채점한다.)
    """
    out: list[EvalRecord] = []
    for run, rec in zip(runs, saved):
        if (rec.question_id, rec.retrieval_mode) != (run.question_id, run.retrieval_mode):
            break
        out.append(rec)
    return out


def score(
    runs: list[RunRecord],
    truths: list[GroundTruth] | dict[str, GroundTruth],
    llm: LLMCall | None = None,
    *,
    use_ragas: bool = True,
    workers: int = 1,
    on_record: Callable[[EvalRecord], None] | None = None,
    done: list[EvalRecord] | None = None,
) -> list[EvalRecord]:
    """spec 인터페이스: score(runs, truths) -> list[EvalRecord]. truths는 목록(spec)이나 id→정답 사전 모두 받는다.

    결과는 항상 runs와 같은 순서다.
    - workers : 동시에 채점할 답안 수. 1이면 한 번에 하나씩 처리한다.
    - on_record: 한 건의 채점·점수 기록이 끝날 때마다 호출된다(중간 저장용, runs 순서대로).
    - done    : runs 앞쪽에서부터 이미 채점된 결과 목록(이어하기). 질문·방식이 맞는 구간은 다시 부르지 않고 그대로 쓴다.
    """
    llm = llm or llm_call
    by_id = truths if isinstance(truths, dict) else {t.question_id: t for t in truths}
    done = reusable_prefix(runs, done or [])
    workers = max(1, int(workers))

    def finish(run: RunRecord, rec: EvalRecord, *, record: bool) -> EvalRecord:
        if record:
            _record_scores(run, rec)
        if on_record is not None:
            on_record(rec)
        return rec

    # 1) 각 답안이 (이미 있음 / 정답지 없음 / 채점 필요) 중 무엇인지 정한다
    plan: list[tuple[str, RunRecord, GroundTruth | EvalRecord | None]] = []
    for i, run in enumerate(runs):
        if i < len(done):
            plan.append(("done", run, done[i]))
        elif by_id.get(run.question_id) is None:
            plan.append(("no_truth", run, None))
        else:
            plan.append(("score", run, by_id[run.question_id]))

    records: list[EvalRecord] = []

    def settle(kind: str, run: RunRecord, payload, scored: EvalRecord | None) -> None:
        if kind == "done":  # 이미 채점·기록된 건: 그대로 쓴다
            records.append(payload)
        elif kind == "no_truth":  # 정답지가 없으면 채점하지 않고 평가 불가로 남긴다 (점수를 지어내지 않음)
            records.append(finish(run, _unscorable_record(run, "정답지(GroundTruth) 없음"), record=False))
        else:
            records.append(finish(run, scored, record=True))

    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = [executor.submit(_score_one_safely, run, payload, llm, use_ragas) if kind == "score" else None for kind, run, payload in plan]
        for (kind, run, payload), future in zip(plan, futures):  # 끝난 순서가 아니라 runs 순서대로 거둔다
            settle(kind, run, payload, future.result() if future is not None else None)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)  # 중간에 멈추면 아직 안 시작한 건은 취소
    return records


MODES = get_args(RetrievalMode)  # contracts가 정한 세 방식. 이름을 여기서 다시 적지 않는다


def read_jsonl(path: Path, model):
    return [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_run_folder(folder: Path) -> list[RunRecord]:
    """metrics 러너가 만든 results/runs/<run_id>/ 의 세 방식 파일을 방식 순서대로 읽는다 (없는 방식은 건너뜀)."""
    return [r for mode in MODES if (folder / f"{mode}.jsonl").exists() for r in read_jsonl(folder / f"{mode}.jsonl", RunRecord)]


def _read_partial(path: Path, runs: list[RunRecord]) -> list[EvalRecord]:
    """중간 저장 파일에서 다시 쓸 수 있는 앞쪽 결과를 읽는다. 끊기며 반쯤 쓰인 줄에서 멈춘다."""
    saved: list[EvalRecord] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                saved.append(EvalRecord.model_validate_json(line))
            except ValueError:
                break
    return reusable_prefix(runs, saved)


def main() -> None:
    p = argparse.ArgumentParser(description="답안(RunRecord JSONL)을 채점해 EvalRecord JSONL로 저장")
    p.add_argument("--run", required=True, help="metrics 러너의 run_id. results/runs/<run_id>/<mode>.jsonl 세 개를 읽고 같은 폴더의 eval.jsonl에 쓴다")
    p.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR, help="평가 JSON 폴더 (정답은 *.json, 질문은 *_questions.json)")
    p.add_argument("--workers", type=int, default=1, help="동시에 채점할 답안 수 (기본 1 = 하나씩). 늘렸을 때 '평가 불가'가 늘면 다시 줄인다")
    p.add_argument("--resume", action="store_true", help="중간에 끊긴 채점을 이어서 한다 (<출력파일>.partial에 남은 건은 다시 채점하지 않음)")
    args = p.parse_args()

    folder = Path("results/runs") / args.run
    runs = read_run_folder(folder)
    out = folder / "eval.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    done = _read_partial(partial, runs) if args.resume else []
    with partial.open("w", encoding="utf-8") as f:  # 한 건 끝날 때마다 저장. 이어하기면 깨끗한 줄만 먼저 다시 쓴다
        for rec in done:
            f.write(rec.model_dump_json() + "\n")
        f.flush()

        def save(rec: EvalRecord) -> None:
            f.write(rec.model_dump_json() + "\n")
            f.flush()

        records = score(runs, load_ground_truths(args.eval_dir), workers=args.workers, on_record=save, done=done)
    # 끝까지 마친 뒤에만 최종 파일을 쓴다 (예전과 같은 모양). 중간 저장 파일은 지운다.
    out.write_text("\n".join(r.model_dump_json() for r in records) + "\n", encoding="utf-8")
    partial.unlink()
    note = f" (이어하기로 건너뜀 {len(done)}건)" if done else ""
    print(f"채점 {len(records)}건 → {out}{note}")


if __name__ == "__main__":
    main()
