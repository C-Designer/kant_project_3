"""답안 묶음을 채점해 EvalRecord 목록을 만든다.

한 답안의 채점 순서
1. rules.precheck  : 서비스 오류면 AI를 부르지 않고 규칙대로 결론
2. Faithfulness    : RAGAS (ragas_eval.py)
3. Judge 4항목     : 채점관 AI (judge.py)
4. 점수를 Langfuse 트레이스에 붙이기 (record_score)

실행 예
  uv run ... python -m src.judge.score --runs data/judge_mock/runs.jsonl \
      --truths data/shipping/evaluation/development.json --out data/judge_mock/eval.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.judge import ragas_eval
from src.contracts import EvalRecord, GroundTruth, RunRecord, TokenUsage
from src.judge.platform_adapter import llm_call, record_score
from src.judge.judge import LLMCall, judge_one
from src.judge.rules import JUDGE_ITEMS, precheck, tag


def load_ground_truths(paths: list[Path]) -> dict[str, GroundTruth]:
    """평가 정답 JSON → GroundTruth. (metrics 로더가 생기면 그것으로 교체)"""
    truths: dict[str, GroundTruth] = {}
    for path in paths:
        for row in json.loads(path.read_text(encoding="utf-8")):
            book_ids = sorted({e["book_id"] for group in row["evidence_groups"] for e in group})
            truths[row["id"]] = GroundTruth(
                question_id=row["id"],
                evidence_book_ids=book_ids,
                expected_action=row["expected_action"],
                reference_answer=row["reference_answer"],
                rubric={k: v for k, v in row.items() if k not in ("id", "question", "reference_answer", "expected_action")},
            )
    return truths


def _sum_tokens(*usages: TokenUsage | None) -> TokenUsage | None:
    used = [u for u in usages if u is not None]
    if not used:
        return None
    total_in: int | None = 0
    total_out: int | None = 0
    for u in used:
        total_in = None if total_in is None or u.input is None else total_in + u.input
        total_out = None if total_out is None or u.output is None else total_out + u.output
    return TokenUsage(input=total_in, output=total_out)


def score_one(run: RunRecord, truth: GroundTruth, llm: LLMCall, *, use_ragas: bool = True) -> EvalRecord:
    early = precheck(run)
    if early is not None:
        return early

    not_applicable: list[str] = []
    unscorable: list[str] = []

    # Faithfulness
    faith, faith_tokens = None, None
    if use_ragas:
        faith, faith_tokens, na, us = ragas_eval.faithfulness(run, llm)
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
        eval_tokens=_sum_tokens(faith_tokens, judge_tokens),
        not_applicable=not_applicable,
        unscorable=unscorable,
    )


def score(runs: list[RunRecord], truths: list[GroundTruth] | dict[str, GroundTruth], llm: LLMCall = None, *, use_ragas: bool = True) -> list[EvalRecord]:
    """spec 인터페이스: score(runs, truths) -> list[EvalRecord]. truths는 목록(spec)이나 id→정답 사전 모두 받는다."""
    llm = llm or (lambda messages: llm_call(messages, kind="eval"))
    by_id = truths if isinstance(truths, dict) else {t.question_id: t for t in truths}
    records = []
    for run in runs:
        truth = by_id.get(run.question_id)
        if truth is None:  # 정답지가 없으면 채점하지 않고 평가 불가로 남긴다 (점수를 지어내지 않음)
            reason = "정답지(GroundTruth) 없음"
            records.append(EvalRecord(question_id=run.question_id, retrieval_mode=run.retrieval_mode, faithfulness=None, judge=None,
                                      eval_tokens=None, not_applicable=[], unscorable=[tag(i, reason) for i in ("faithfulness", *JUDGE_ITEMS)]))
            continue
        rec = score_one(run, truth, llm, use_ragas=use_ragas)
        record_score(run.request_id, "faithfulness", rec.faithfulness)
        for item, result in (rec.judge or {}).items():
            record_score(run.request_id, f"judge_{item}", result.score, result.reason)
        records.append(rec)
    return records


DEFAULT_TRUTHS = [Path(f"data/shipping/evaluation/{n}.json") for n in ("development", "additional", "expansion_validation")]
MODES = ("naive", "hybrid", "hybrid_rerank")


def _read_runs(path: Path) -> list[RunRecord]:
    return [RunRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    p = argparse.ArgumentParser(description="답안(RunRecord JSONL)을 채점해 EvalRecord JSONL로 저장")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--run", help="metrics 러너의 run_id. results/runs/<run_id>/<mode>.jsonl 세 개를 읽고 같은 폴더의 eval.jsonl에 쓴다")
    src.add_argument("--runs", type=Path, help="RunRecord JSONL 파일 하나 (시험지 등)")
    p.add_argument("--truths", type=Path, nargs="+", default=DEFAULT_TRUTHS)
    p.add_argument("--out", type=Path, help="--runs를 쓸 때 출력 파일")
    p.add_argument("--no-ragas", action="store_true", help="Faithfulness를 건너뜀 (평가 불가로 기록)")
    args = p.parse_args()

    if args.run:
        folder = Path("results/runs") / args.run
        runs = [r for mode in MODES if (folder / f"{mode}.jsonl").exists() for r in _read_runs(folder / f"{mode}.jsonl")]
        args.out = folder / "eval.jsonl"
    else:
        if not args.out:
            p.error("--runs를 쓸 때는 --out이 필요합니다")
        runs = _read_runs(args.runs)
    records = score(runs, load_ground_truths(args.truths), use_ragas=not args.no_ragas)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(r.model_dump_json() for r in records) + "\n", encoding="utf-8")
    print(f"채점 {len(records)}건 → {args.out}")


if __name__ == "__main__":
    main()
