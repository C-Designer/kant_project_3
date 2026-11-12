"""Langfuse Experiments로 질문 x 검색 방식을 돌리고 방식별 지표표를 만든다. 방식마다 데이터셋 run 하나가 생겨 화면에서 나란히 비교된다.

    PYTHONPATH=. uv run python scripts/lf_experiment.py                       # 공식 15문항 x 세 방식
    PYTHONPATH=. uv run python scripts/lf_experiment.py --modes hybrid_rerank --no-quality

.env의 Langfuse 키가 실험 전용 프로젝트(kant-exp-stone)가 아니면 시작하지 않는다(팀원 로그와 섞이지 않게).
task에는 질문 문장만 넘기고, 정답·기대 동작은 expected_output으로 evaluator에만 간다.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from langfuse import get_client
from langfuse.experiment import Evaluation

from src import config
from src.contracts import GroundTruth, RunRecord
from src.judge.score import llm_call, score_one
from src.metrics.aggregate import mean_excluding_none
from src.metrics.loader import load_evaluation
from src.metrics.questions import DEFAULT_MIN_DOCS, DEFAULT_MIN_PER_SOURCE, DEFAULT_QUOTA, DEFAULT_SEED, select_questions
from src.metrics.retrieval_metrics import hit_recall
from src.platform.query import run_query

PROJECT = "kant-exp-stone"
DATASET = "kant-exp-basic15"
EVAL_DIR = config.DATA_DIR / "evaluation"
STATUS_TO_ACTION = {"answered": "answer", "needs_clarification": "clarify", "abstained": "abstain"}

# (표 열 이름, 점수 이름, 합계로 낼지). 합계가 아니면 None을 뺀 평균
COLUMNS = [
    ("Hit@k", "hit", False), ("Recall@k", "recall", False), ("판단 일치", "action_match", False),
    ("Faithfulness", "faithfulness", False), ("사실", "judge_facts", False), ("조건", "judge_conditions", False),
    ("근거", "judge_evidence", False), ("판단", "judge_decision", False),
    ("오류율", "error", False), ("응답 시간(ms, 정상)", "latency_ms", False),
    ("입력 토큰 합", "input_tokens", True), ("출력 토큰 합", "output_tokens", True),
    ("평가 입력 토큰 합", "eval_input_tokens", True), ("평가 출력 토큰 합", "eval_output_tokens", True),
]


def retrieval_and_action(*, output, expected_output, **_):
    evals = [Evaluation(name="action_match", value=int(STATUS_TO_ACTION.get(output["status"]) == expected_output["expected_action"]))]
    score = hit_recall(expected_output["evidence_book_ids"], output["retrieved_book_ids"], config.K)
    if score.hit is not None:  # 근거 목록이 없는 질문은 측정 못 함: 0이 아니라 건너뜀
        evals += [Evaluation(name="hit", value=score.hit), Evaluation(name="recall", value=score.recall)]
    return evals


def ops(*, output, **_):
    failed = output["status"] == "error"
    evals = [Evaluation(name="error", value=int(failed))]
    if not failed:  # 응답 시간은 정상 요청만
        evals.append(Evaluation(name="latency_ms", value=output["latency_ms"]))
    for name in ("input_tokens", "output_tokens"):
        if output[name] is not None:
            evals.append(Evaluation(name=name, value=output[name]))
    return evals


def quality(*, output, expected_output, **_):
    # 실험이 평가 함수를 이벤트 루프 안에서 부르는데 RAGAS는 asyncio.run을 써서 실패한다. 루프 없는 별도 스레드에서 돌린다
    with ThreadPoolExecutor(1) as pool:
        rec = pool.submit(score_one, RunRecord.model_validate(output), GroundTruth.model_validate(expected_output), llm_call).result()
    evals = [Evaluation(name="faithfulness", value=rec.faithfulness)] if rec.faithfulness is not None else []
    evals += [Evaluation(name=f"judge_{k}", value=v.score, comment=v.reason) for k, v in (rec.judge or {}).items() if v.score is not None]
    if rec.eval_tokens:
        evals += [Evaluation(name=f"eval_{k}_tokens", value=v) for k, v in rec.eval_tokens.model_dump().items() if v is not None]
    return evals


def summarize(result) -> dict[str, float | None]:
    values: dict[str, list[float]] = {}
    for item in result.item_results:
        for e in item.evaluations:
            values.setdefault(e.name, []).append(e.value)
    return {col: (sum(values[s]) if total and s in values else None if total else mean_excluding_none(values.get(s, [])))
            for col, s, total in COLUMNS}


def table(rows: dict[str, dict], n: int) -> str:
    fmt = lambda v: "-" if v is None else f"{v:,.0f}" if abs(v) >= 100 else f"{v:.2f}"
    lines = [f"| 방식 | {' | '.join(c for c, _, _ in COLUMNS)} |", "|---|" + "---|" * len(COLUMNS)]
    lines += [f"| {m} | {' | '.join(fmt(r[c]) for c, _, _ in COLUMNS)} |" for m, r in rows.items()]
    return f"질문 {n}개, k={config.K}. `-`은 측정·해당 없음(0 아님). 평균은 None을 뺀 값.\n\n" + "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--modes", default="naive,hybrid,hybrid_rerank")
    p.add_argument("--no-quality", action="store_true", help="Faithfulness·Judge(평가 LLM 호출)를 건너뛴다")
    args = p.parse_args()

    lf = get_client()
    name = lf.api.projects.get().data[0].name
    if name != PROJECT:
        raise SystemExit(f"Langfuse 프로젝트가 {name!r}이다. 실험 전용 {PROJECT!r}가 아니라서 중단한다.")

    questions, truths = load_evaluation(EVAL_DIR)
    picked = select_questions(questions, truths, DEFAULT_QUOTA, DEFAULT_SEED,
                              min_per_source=DEFAULT_MIN_PER_SOURCE, min_docs=DEFAULT_MIN_DOCS)
    lf.create_dataset(name=DATASET, description=f"공식 선택 {len(picked)}문항(시드 {DEFAULT_SEED})")
    for q in picked:
        lf.create_dataset_item(  # id를 질문 id로 고정해 다시 돌려도 중복이 안 생긴다
            id=f"{DATASET}-{q.id}", dataset_name=DATASET, input=q.question,
            metadata={"question_id": q.id, "source": q.source}, expected_output=truths[q.id].model_dump(mode="json"),
        )
    dataset = lf.get_dataset(DATASET)
    stamp = datetime.now().strftime("%m%d-%H%M")
    evaluators = [retrieval_and_action, ops] + ([] if args.no_quality else [quality])

    rows = {}
    for mode in args.modes.split(","):
        def task(*, item, _mode=mode, **_):
            return run_query(item.input, _mode, question_id=item.metadata["question_id"], channel="experiment").model_dump(mode="json")

        result = dataset.run_experiment(
            name="kant-modes", run_name=f"{stamp}-{mode}", description=f"{mode}, k={config.K}", task=task,
            evaluators=evaluators, max_concurrency=3, metadata={"mode": mode, "k": config.K},
        )
        rows[mode] = summarize(result)
        print(f"{mode} 완료")
    lf.flush()

    out = Path("results") / f"lf_experiment-{stamp}.md"
    out.write_text(table(rows, len(picked)), encoding="utf-8")
    print(table(rows, len(picked)), f"\n\n저장: {out}")


if __name__ == "__main__":
    assert set(STATUS_TO_ACTION.values()) == set(DEFAULT_QUOTA)
    main()
