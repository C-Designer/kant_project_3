"""발제 예시(장비 A 자동 화면 꺼짐 15분)로 채점관을 돌려 4항목이 모두 1인지 확인한다 (Issue #31 완료 조건).

발제 STEP 5 예시를 그대로 옮겼다. 가상 자료이며 실제 데이터셋이 아니다.

실행 예 (실제 AI 필요)
  python -m src.judge.brief_demo
"""

from __future__ import annotations

import json

from src.contracts import ChunkMeta, Citation, ContextChunk, GroundTruth, RunRecord
from src.judge.platform_adapter import llm_call
from src.judge.judge import judge_one


def brief_example() -> tuple[RunRecord, GroundTruth]:
    s1 = ContextChunk(source_id="S1", text="장비 A의 자동 화면 꺼짐 시간은 10분입니다. 장비 B는 5분입니다.",
                      metadata=ChunkMeta(book_id="DEMO_MANUAL", file_name="DEMO_MANUAL.pdf", page=3, chunk_id="DEMO_MANUAL-p3-c1"))
    s2 = ContextChunk(source_id="S2", text="2026년 11월 1일부터 장비 A의 자동 화면 꺼짐 시간을 15분으로 정정합니다. 기존 안내의 10분을 대체합니다. 장비 B에는 적용하지 않습니다.",
                      metadata=ChunkMeta(book_id="DEMO_NOTICE", file_name="DEMO_NOTICE.pdf", page=1, chunk_id="DEMO_NOTICE-p1-c1"))
    run = RunRecord(
        question_id="DEMO-01", request_id="demo-001", retrieval_mode="hybrid",
        question="2026년 11월 2일 기준 장비 A의 자동 화면 꺼짐 시간은 몇 분인가요?",
        status="answered",
        answer="2026년 11월 2일 기준 장비 A의 자동 화면 꺼짐 시간은 15분입니다.",
        reason="장비 A에 적용되는 정정 공지가 기존 10분을 15분으로 바꿉니다.",
        citations=[Citation(source_id="S2", book_id="DEMO_NOTICE", file_name="DEMO_NOTICE.pdf", page=1)],
        retrieved_book_ids=["DEMO_MANUAL", "DEMO_NOTICE"], final_context=[s1, s2],
        latency_ms=None, input_tokens=None, output_tokens=None, error=None,
    )
    truth = GroundTruth(
        question_id="DEMO-01", evidence_book_ids=["DEMO_NOTICE"], expected_action="answer",
        reference_answer="2026년 11월 2일 기준 장비 A의 자동 화면 꺼짐 시간은 15분입니다.",
        rubric={"required_facts": ["장비 A, 2026년 11월 2일 기준 15분"], "forbidden_claims": ["10분"], "grading_notes": "정정 공지의 적용 대상과 적용일을 확인한다."},
    )
    return run, truth


def main() -> None:
    run, truth = brief_example()
    items, tokens, err = judge_one(run, truth, lambda m: llm_call(m, kind="eval"))
    out = {k: v.model_dump() for k, v in (items or {}).items()}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"채점 토큰 입력 {tokens.input} / 출력 {tokens.output}" + (f" / 실패: {err}" if err else ""))


if __name__ == "__main__":
    main()
