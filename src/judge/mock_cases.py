"""채점관 시험지 만들기: "정답을 이미 아는" 가짜 답안 묶음.

주의: 여기서는 정답지의 근거 인용문을 가짜 문맥으로 쓴다. 이것은 **채점관을 시험하는
용도로만** 허용된다. 실제 서비스의 검색·생성에는 절대 정답지를 넣지 않는다.

만드는 답안 종류 (kind)            기대하는 채점 결과
- good          참고 답변 그대로        decision 1 (답변 문항은 네 칸 모두 1)
- time_swap     낮 12시 ↔ 오후 3시       conditions 0
- forbidden     금지 주장을 단정         decision 0
- wrong_abstain 답할 수 있는데 보류      decision 0, facts 0
- no_context    문맥·인용 없이 같은 답   evidence 0
- error         서비스 오류              decision 0, 나머지 null (규칙으로 처리)

실행 예
  python -m src.judge.mock_cases --truths data/shipping/evaluation/development.json --out data/judge_mock
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pydantic import BaseModel

from src.contracts import ChunkMeta, Citation, ContextChunk, GroundTruth, RunRecord
from src.judge.score import load_ground_truths

ACTION_TO_STATUS = {"answer": "answered", "clarify": "needs_clarification", "abstain": "abstained"}
TIME_SWAP = [("낮 12시", "오후 3시"), ("오후 3시", "낮 12시"), ("12:00", "15:00"), ("15:00", "12:00")]


class MockCase(BaseModel):
    case_id: str
    kind: str
    run: RunRecord
    expected: dict[str, int | None]  # 확인할 칸만 적는다. 예: {"conditions": 0}


def _context_from_evidence(truth: GroundTruth) -> list[ContextChunk]:
    """근거 그룹의 인용문을 모두 문맥 조각으로 만든다 (같은 쪽은 한 번만).

    v1은 그룹마다 첫 인용문만 넣었더니, 필요한 내용이 두 번째 인용문에 있어
    "좋은 답안"인데도 근거가 부족해 보이는 시험지가 생겼다(S-DEV-18). 그래서 전부 넣는다.
    """
    chunks: list[ContextChunk] = []
    seen: set[tuple[str, int]] = set()
    for e in (e for group in truth.rubric.get("evidence_groups", []) for e in group):
        key = (e["book_id"], e["page"])
        if key in seen:
            continue
        seen.add(key)
        sid = f"S{len(chunks) + 1}"
        chunks.append(
            ContextChunk(
                source_id=sid,
                text=e["quote"].strip(),
                metadata=ChunkMeta(book_id=e["book_id"], file_name=f"{e['book_id']}.pdf", page=e["page"], chunk_id=f"{e['book_id']}-p{e['page']}-mock"),
            )
        )
    return chunks


def _citations(context: list[ContextChunk]) -> list[Citation]:
    return [Citation(source_id=c.source_id, book_id=c.metadata.book_id, file_name=c.metadata.file_name, page=c.metadata.page) for c in context]


def _run(truth: GroundTruth, question: str, kind: str, *, status: str, answer: str, reason: str, context: list[ContextChunk], error: str | None = None) -> RunRecord:
    return RunRecord(
        question_id=truth.question_id,
        request_id=f"mock-{truth.question_id}-{kind}",
        retrieval_mode="naive",
        question=question,
        status=status,
        answer=answer,
        reason=reason,
        citations=[] if status == "error" else _citations(context),
        retrieved_book_ids=sorted({c.metadata.book_id for c in context}),
        final_context=context,
        latency_ms=None,
        input_tokens=None,
        output_tokens=None,
        error=error,
    )


def make_cases(truth: GroundTruth, question: str) -> list[MockCase]:
    ctx = _context_from_evidence(truth)
    good_status = ACTION_TO_STATUS[truth.expected_action]
    ref = truth.reference_answer
    forbidden = truth.rubric.get("forbidden_claims", [])
    cases: list[MockCase] = []

    def add(kind: str, run: RunRecord, expected: dict) -> None:
        cases.append(MockCase(case_id=f"{truth.question_id}:{kind}", kind=kind, run=run, expected=expected))

    # good
    good_expected = {"decision": 1}
    if truth.expected_action == "answer":
        good_expected = {"facts": 1, "conditions": 1, "evidence": 1, "decision": 1}
    add("good", _run(truth, question, "good", status=good_status, answer=ref, reason="근거 자료에 따라 판단함", context=ctx), good_expected)

    # time_swap: 시각을 "마감"으로 단정하는 답변만.
    # "공통으로 낮 12시라고 답할 수 없습니다"처럼 시각을 부정하는 문장은 바꿔도 여전히 맞는 말이라
    # 시험지가 되지 않는다(S-DEV-16). 시각이 든 문장에 부정 표현이 있으면 건너뛴다.
    swapped = ref
    for old, new in TIME_SWAP:
        sentence = next((s for s in re.split(r"(?<=[.다])\s+", ref) if old in s), "")
        if old in ref and not re.search(r"없|않|아니", sentence):
            swapped = ref.replace(old, "\0").replace(new, old).replace("\0", new)
            break
    if swapped != ref:
        add("time_swap", _run(truth, question, "time_swap", status=good_status, answer=swapped, reason="근거 자료에 따라 판단함", context=ctx), {"conditions": 0})

    # forbidden: 금지 주장 하나를 단정
    if forbidden:
        claim = f"확인 결과: {forbidden[0]}."
        add("forbidden", _run(truth, question, "forbidden", status="answered", answer=claim, reason="자료에 따라 단정함", context=ctx), {"decision": 0})

    if truth.expected_action == "answer":
        # wrong_abstain: 답할 수 있는데 보류
        add(
            "wrong_abstain",
            _run(truth, question, "wrong_abstain", status="abstained", answer="제공된 자료만으로는 확인할 수 없어 답변을 보류합니다.", reason="근거 부족", context=ctx),
            {"facts": 0, "decision": 0},
        )
        # no_context: 같은 답인데 근거 자료가 없음
        add("no_context", _run(truth, question, "no_context", status="answered", answer=ref, reason="근거 자료에 따라 판단함", context=[]), {"evidence": 0})

    # error: 규칙으로 처리되는지
    add("error", _run(truth, question, "error", status="error", answer="요청을 처리하지 못했습니다.", reason="model_timeout", context=[], error="model_timeout"),
        {"facts": None, "conditions": None, "evidence": None, "decision": 0})
    return cases


def build_all(truth_paths: list[Path]) -> list[MockCase]:
    truths = load_ground_truths(truth_paths)
    questions = {}
    for path in truth_paths:
        for row in json.loads(path.read_text(encoding="utf-8")):
            questions[row["id"]] = row["question"]
    cases: list[MockCase] = []
    for qid, truth in truths.items():
        cases += make_cases(truth, questions[qid])
    return cases


def main() -> None:
    p = argparse.ArgumentParser(description="채점관 시험용 가짜 답안 생성")
    p.add_argument("--truths", type=Path, nargs="+", required=True)
    p.add_argument("--out", type=Path, required=True, help="출력 폴더")
    args = p.parse_args()
    cases = build_all(args.truths)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cases.jsonl").write_text("\n".join(c.model_dump_json() for c in cases) + "\n", encoding="utf-8")
    (args.out / "runs.jsonl").write_text("\n".join(c.run.model_dump_json() for c in cases) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for c in cases:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    print(f"가짜 답안 {len(cases)}건 → {args.out}  종류별: {kinds}")


if __name__ == "__main__":
    main()
