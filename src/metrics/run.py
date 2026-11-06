"""일괄 실행 러너: 질문 x 3방식을 `run_query()`로 돌려 RunRecord JSONL로 남긴다.

    uv run python -m src.metrics.run --questions results/questions.json --modes naive,hybrid,hybrid_rerank
    uv run python -m src.metrics.run --questions results/questions.json --mock   # platform 없이 연습 실행

- `run_query`에는 질문 문장과 방식만 넘긴다(정답·id·source는 넘기지 않는다).
- 반환된 RunRecord의 question_id·question·retrieval_mode는 러너가 입력 값으로 덮어쓴다(조인 키를 믿을 수 있게).
- 호출이 예외로 끝나도 error 기록을 남기고 계속 간다. 시간은 러너가 잰 값, 토큰은 모르므로 None.
- 같은 run_id 폴더가 있으면 FileExistsError. 덮어쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
import zlib
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from src.contracts import RunRecord
from .loader import Question

MODES = ("naive", "hybrid", "hybrid_rerank")
DEFAULT_RESULTS_DIR = Path("results")

RunQuery = Callable[..., RunRecord]  # run_query(question, mode, *, request_id=None) -> RunRecord


def make_run_id(now: datetime | None = None, label: str | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{label}" if label else stamp


def _call(run_query: RunQuery, q: Question, mode: str, clock: Callable[[], float]) -> RunRecord:
    started = clock()
    try:
        rec = run_query(q.question, mode)
    except Exception as e:  # noqa: BLE001 - 어떤 실패든 기록하고 다음으로 간다
        elapsed_ms = int((clock() - started) * 1000)
        return RunRecord(
            question_id=q.id,
            request_id=f"runner-{uuid.uuid4().hex[:12]}",
            retrieval_mode=mode,
            question=q.question,
            status="error",
            answer="",
            reason="",
            citations=[],
            retrieved_book_ids=[],
            final_context=[],
            error=f"{type(e).__name__}: {e}",
            latency_ms=elapsed_ms,
            input_tokens=None,  # 호출이 중단돼 사용량을 모른다: 0이 아니라 None
            output_tokens=None,
        )
    return rec.model_copy(update={"question_id": q.id, "question": q.question, "retrieval_mode": mode})


def run_all(
    questions: Iterable[Question],
    modes: Iterable[str],
    run_query: RunQuery,
    results_dir: Path | str = DEFAULT_RESULTS_DIR,
    *,
    run_id: str | None = None,
    label: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
    extra: dict | None = None,
) -> Path:
    questions, modes = list(questions), list(modes)
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        raise ValueError(f"지원하지 않는 방식: {unknown} (가능: {list(MODES)})")

    run_id = run_id or make_run_id(label=label)
    run_dir = Path(results_dir) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)  # 있으면 FileExistsError: 덮어쓰지 않는다

    started_at = datetime.now().isoformat(timespec="seconds")
    with ExitStack() as stack:
        files = {m: stack.enter_context((run_dir / f"{m}.jsonl").open("w", encoding="utf-8")) for m in modes}
        for q in questions:  # 질문 단위로 방식을 돌려, 중간에 멈춰도 방식 간 치우침이 작다
            for mode in modes:
                rec = _call(run_query, q, mode, clock)
                files[mode].write(rec.model_dump_json() + "\n")
                files[mode].flush()

    meta = {
        "run_id": run_id,
        "label": label,
        "modes": modes,
        "question_ids": [q.id for q in questions],
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        **(extra or {}),  # 선택 시드·유형별 개수 등 비교표 상단에 적을 실행 조건
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


def load_runs(run_dir: Path | str) -> list[RunRecord]:
    run_dir = Path(run_dir)
    records: list[RunRecord] = []
    for mode in MODES:
        path = run_dir / f"{mode}.jsonl"
        if path.exists():
            records += [RunRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return records


def mock_run_query(question: str, mode: str, *, request_id: str | None = None) -> RunRecord:
    """platform이 없을 때 쓰는 연습용 가짜 run_query. 같은 입력이면 같은 결과."""
    h = zlib.crc32(f"{question}|{mode}".encode())
    books = [f"SB{(h >> s) % 15 + 1:02d}" for s in (0, 3, 6)]
    return RunRecord(
        question_id="",
        request_id=request_id or f"mock-{h:08x}",
        retrieval_mode=mode,
        question=question,
        status=("answered", "answered", "needs_clarification", "abstained")[h % 4],
        answer="(mock 답변)",
        reason="mock",
        citations=[],
        retrieved_book_ids=books,
        final_context=[],
        latency_ms=80 + h % 400,
        input_tokens=900 + h % 300,
        output_tokens=60 + h % 40,
        error=None,
    )


def _real_run_query() -> RunQuery:
    try:
        from src.platform.query import run_query
    except ImportError as e:
        raise SystemExit(f"platform.run_query()를 가져올 수 없다({e}). `uv sync` 후 다시 하거나 --mock으로 실행한다.") from e
    return run_query


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="질문 x 방식 일괄 실행")
    p.add_argument("--questions", required=True, type=Path, help="results/questions.json")
    p.add_argument("--modes", default=",".join(MODES))
    p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    p.add_argument("--label")
    p.add_argument("--mock", action="store_true", help="platform 없이 가짜 run_query로 실행")
    args = p.parse_args(argv)

    from .questions import load_selection

    run_query = mock_run_query if args.mock else _real_run_query()
    selection = json.loads(args.questions.read_text(encoding="utf-8"))
    extra = {"selection_seed": selection.get("seed"), "quota": selection.get("quota"), "questions_file": str(args.questions)}
    run_dir = run_all(
        load_selection(args.questions), args.modes.split(","), run_query, args.results_dir, label=args.label, extra=extra
    )
    print(f"완료: {run_dir}")


if __name__ == "__main__":
    main()
