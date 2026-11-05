"""영역 간에 주고받는 값의 타입. 바꾸려면 PR 제목에 [interface]를 붙이고 짝의 확인을 받는다.

필드는 docs/specs/*.md의 인터페이스 절과 1:1이다. 측정 못 한 값은 None이며 0으로 바꾸지 않는다.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

RetrievalMode = Literal["naive", "hybrid", "hybrid_rerank"]
LLMStatus = Literal["answered", "needs_clarification", "abstained"]
Status = Literal["answered", "needs_clarification", "abstained", "error"]
ExpectedAction = Literal["answer", "clarify", "abstain"]


def book_id_from_file_name(file_name: str) -> str:
    """book_id = 파일명에서 .pdf를 뺀 값 (FB01.pdf -> FB01)."""
    return file_name.removesuffix(".pdf")


class ChunkMeta(BaseModel):
    book_id: str
    file_name: str
    page: int = Field(ge=1)  # 첫 페이지 = 1
    chunk_id: str  # "<book_id>-p<page>-c<n>", 컬렉션 안에서 유일


class RetrievedChunk(BaseModel):
    text: str
    score: float
    metadata: ChunkMeta


class ContextChunk(BaseModel):
    source_id: str  # "S1"
    text: str
    metadata: ChunkMeta


class LLMOutput(BaseModel):  # 모델이 내는 JSON
    status: LLMStatus
    answer: str
    reason: str
    source_ids: list[str]


class Citation(BaseModel):
    source_id: str
    book_id: str
    file_name: str
    page: int


class QueryRequest(BaseModel):
    question: str
    retrieval_mode: RetrievalMode

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question은 비어 있을 수 없다")
        return v


class QueryResponse(BaseModel):
    request_id: str
    status: Status
    answer: str
    reason: str
    citations: list[Citation]


class RunRecord(BaseModel):  # 질문 하나 x 방식 하나. metrics가 만들고 judge가 읽는다
    question_id: str
    request_id: str
    retrieval_mode: RetrievalMode
    question: str
    status: Status
    answer: str
    reason: str
    citations: list[Citation]
    retrieved_book_ids: list[str]
    final_context: list[ContextChunk]
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None


class GroundTruth(BaseModel):  # 로더가 judge에 넘기는 정답 측. 채점에만 쓴다
    question_id: str
    evidence_book_ids: list[str]  # evidence_groups 평탄화·중복 제거
    expected_action: ExpectedAction
    reference_answer: str
    rubric: dict


class JudgeItem(BaseModel):
    score: Literal[0, 1] | None
    reason: str


class TokenUsage(BaseModel):
    input: int | None
    output: int | None


class EvalRecord(BaseModel):  # judge가 만들고 metrics가 합친다
    question_id: str
    retrieval_mode: RetrievalMode
    faithfulness: float | None
    judge: dict[str, JudgeItem] | None  # facts, conditions, evidence, decision
    eval_tokens: TokenUsage | None
    not_applicable: list[str]  # 해당 없음 이유
    unscorable: list[str]  # 평가 불가 이유
