"""LLM 없는 순차 검색 지표 실험.

    PYTHONPATH=. uv run python scripts/exp_retrieval_bench.py --out results/exp2.csv
"""

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

from scripts.exp_config import apply as apply_exp_config

try:
    apply_exp_config()
except ImportError as exc:
    print(f"경고: scripts.exp_config를 불러올 수 없어 기본 설정을 사용합니다: {exc}", file=sys.stderr)

from src import config
from src.answer.context import build_context, count_tokens
from src.metrics.loader import load_evaluation
from src.metrics.questions import (
    DEFAULT_MIN_DOCS,
    DEFAULT_MIN_PER_SOURCE,
    DEFAULT_QUOTA,
    DEFAULT_SEED,
    select_questions,
)
from src.metrics.retrieval_metrics import hit_recall
from src.search.retrieve import retrieve  # src.search.retrieve는 모듈이라 함수를 직접 가져온다

FIELDS = [
    "label", "variable", "value", "mode", "question_id", "hit", "recall", "retrieve_ms",
    "n_chunks", "context_tokens", "dropped_chunks", "truncated", "retrieve_ms_range",
]


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="LLM 없는 순차 검색 지표 실험")
    parser.add_argument("--modes", default="naive,hybrid,hybrid_rerank")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--variable", default="")
    parser.add_argument("--value", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    args.modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    if args.repeats < 1:
        parser.error("--repeats는 1 이상이어야 합니다")
    if not args.modes:
        parser.error("--modes에 하나 이상 지정해야 합니다")
    return args


def context_metrics(chunks, token_limit: int) -> tuple[int, int, int]:
    context = build_context(chunks, token_limit=token_limit)
    tokens = sum(count_tokens(chunk.text) for chunk in context)
    dropped = len(chunks) - len(context)
    truncated = int(bool(dropped) or (bool(chunks) and bool(context) and context[0].text != chunks[0].text))
    return tokens, dropped, truncated


def run(args) -> list[dict]:
    questions, truths = load_evaluation(config.DATA_DIR / "evaluation")
    picked = select_questions(
        questions, truths, DEFAULT_QUOTA, DEFAULT_SEED,
        min_per_source=DEFAULT_MIN_PER_SOURCE, min_docs=DEFAULT_MIN_DOCS,
    )
    rows = []
    for mode in args.modes:
        retrieve(picked[0].question, mode, config.K)  # warm up model and local index
        for question in picked:
            durations = []
            chunks = []
            for _ in range(args.repeats):
                start = time.perf_counter()
                chunks = retrieve(question.question, mode, config.K)
                durations.append((time.perf_counter() - start) * 1000)
            score = hit_recall(
                truths[question.id].evidence_book_ids,
                [chunk.metadata.book_id for chunk in chunks],
                config.K,
            )
            context_tokens, dropped, truncated = context_metrics(chunks, config.CONTEXT_TOKEN_LIMIT)
            rows.append({
                "label": config.env("EXP_LABEL") or "", "variable": args.variable, "value": args.value,
                "mode": mode, "question_id": question.id,
                "hit": "" if score.hit is None else score.hit,
                "recall": "" if score.recall is None else score.recall,
                "retrieve_ms": statistics.median(durations),
                "retrieve_ms_range": max(durations) - min(durations),
                "n_chunks": len(chunks), "context_tokens": context_tokens,
                "dropped_chunks": dropped, "truncated": truncated,
            })
    return rows


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = run(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"저장: {out} ({len(rows)}행)")


if __name__ == "__main__":
    assert parse_args(["--out", "x.csv"]).repeats == 3
    assert parse_args(["--modes", "naive", "--repeats", "1", "--out", "x.csv"]).modes == ["naive"]
    assert statistics.median([1, 2, 9]) == 2
    assert max([1, 2, 9]) - min([1, 2, 9]) == 8
    assert hit_recall([], ["A"], 5).hit is None
    from src.contracts import ChunkMeta, RetrievedChunk
    fake = RetrievedChunk(text="x" * 20, score=1, metadata=ChunkMeta(
        book_id="A", file_name="A.pdf", page=1, chunk_id="A-p1-c1"))
    assert context_metrics([fake], 2)[2] == 1
    assert context_metrics([fake, fake.model_copy(update={"metadata": fake.metadata.model_copy(update={"chunk_id": "A-p1-c2"})})], 3)[2] == 1
    main()
