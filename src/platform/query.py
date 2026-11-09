"""API와 metrics 러너가 공유하는 단일 실행 경로."""

import logging
import time
import uuid

from src import config
from src.answer import chain, context as ctx_mod
from src.answer.validate import ValidationFailed
from src.contracts import RunRecord
from src.platform import jsonl, llm, tracing
from src.search import retrieve as search

log = logging.getLogger(__name__)


def _reason_for(e: Exception) -> tuple[str, str]:
    if isinstance(e, ValidationFailed):
        return "output_validation", str(e)
    if isinstance(e, llm.LLMError):
        return e.reason, str(e)
    if isinstance(e, search.IndexNotFound):
        return "index_missing", str(e)
    if isinstance(e, NotImplementedError):
        return "mode_not_implemented", str(e)
    log.error("run_query 내부 오류", exc_info=True)
    return "internal_error", "내부 오류"  # 원문은 로그에만


def run_query(question: str, mode, *, request_id: str | None = None, question_id: str = "", user_id: str = "eval") -> RunRecord:
    request_id = request_id or uuid.uuid4().hex
    start = time.perf_counter()
    chunks, context = [], []
    status, answer, reason, citations, error = "error", "", "", [], None

    with tracing.request_trace(request_id, question, user_id) as root, llm.usage_scope() as usage:
        try:
            chunks = search.retrieve(question, mode, config.K)
            context = ctx_mod.build_context(chunks, token_limit=config.CONTEXT_TOKEN_LIMIT)
            out, citations = chain.generate(question, context)
            status, answer, reason = out.status, out.answer, out.reason
        except Exception as e:
            reason, error = _reason_for(e)
            citations = []
        root.update(output={"status": status, "reason": reason})

    record = RunRecord(
        question_id=question_id,
        request_id=request_id,
        retrieval_mode=mode,
        question=question,
        status=status,
        answer=answer,
        reason=reason,
        citations=citations,
        retrieved_book_ids=list(dict.fromkeys(c.metadata.book_id for c in chunks)),
        final_context=context,
        latency_ms=int((time.perf_counter() - start) * 1000),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        error=error,
    )
    if config.RUN_LOG_PATH is not None:
        jsonl.append(config.RUN_LOG_PATH, record)
    return record
