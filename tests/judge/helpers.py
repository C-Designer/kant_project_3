from src.contracts import ChunkMeta, Citation, ContextChunk, GroundTruth, RunRecord
from src.judge.platform_adapter import LLMResult


def make_run(status="answered", answer="SI 마감은 11월 4일 낮 12시입니다.", context=True, error=None) -> RunRecord:
    ctx = [ContextChunk(source_id="S1", text="예정 출항일이 11월 6일이면 SI 마감은 11월 4일 낮 12시다.",
                        metadata=ChunkMeta(book_id="SB11", file_name="SB11.pdf", page=1, chunk_id="SB11-p1-c1"))] if context else []
    return RunRecord(
        question_id="Q1", request_id="r1", retrieval_mode="naive", question="11월 6일 출항 SI 마감은?",
        status=status, answer=answer, reason="", error=error,
        citations=[Citation(source_id="S1", book_id="SB11", file_name="SB11.pdf", page=1)] if context else [],
        retrieved_book_ids=["SB11"] if context else [], final_context=ctx,
        latency_ms=None, input_tokens=None, output_tokens=None,
    )


def make_truth() -> GroundTruth:
    return GroundTruth(question_id="Q1", evidence_book_ids=["SB11"], expected_action="answer",
                       reference_answer="11월 4일 낮 12시", rubric={"required_facts": ["11월 4일 낮 12시"], "forbidden_claims": ["15:00"]})


def fake_llm(*texts, tokens=(10, 5)):
    """정해 둔 답을 차례로 돌려주는 가짜 AI. 마지막 답은 계속 반복."""
    replies = list(texts)
    calls = []

    def call(messages):
        calls.append(messages)
        text = replies.pop(0) if len(replies) > 1 else replies[0]
        return LLMResult(text=text, input_tokens=tokens[0], output_tokens=tokens[1], latency_ms=1)

    call.calls = calls
    return call
