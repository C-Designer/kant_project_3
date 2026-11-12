from fastapi import FastAPI, Request

from src.answer import masking
from src.contracts import QueryRequest, QueryResponse
from src.platform import tracing
from src.platform.query import run_query

app = FastAPI(title="shipping-rag")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query(req: QueryRequest, request: Request) -> QueryResponse:
    # Cloudflare Access 로그인 계정. 헤더가 없는 로컬 호출은 None → run_query가 TRACE_USER로 채운다
    email = request.headers.get("cf-access-authenticated-user-email")
    user_id = email.split("@")[0] if email else None
    if req.unmask:  # 사용자가 동의한 재질문: 원문은 모델에 가고, 기록에서는 다시 가린다
        table = {}
        with tracing.hide_pii():
            r = run_query(req.question, req.retrieval_mode, channel="api", user_id=user_id)
    else:  # 기본: 질문의 개인정보를 가리고 응답 직전에 되돌린다. 대응표는 이 함수 밖으로 나가지 않는다
        masked, table = masking.mask(req.question)
        r = run_query(masked, req.retrieval_mode, channel="api", user_id=user_id)
    # 가린 값이 있었는데 답하지 못했을 때만 제안한다. unmask 요청은 table이 비어 다시 제안하지 않는다
    offer = masking.UNMASK_OFFER if table and r.status in ("needs_clarification", "abstained") else None
    # 처리된 요청은 status "error"여도 HTTP 200: 실패는 status·reason으로 구분한다 (#38)
    return QueryResponse(
        request_id=r.request_id, status=r.status, answer=masking.restore(r.answer, table),
        reason=masking.restore(r.reason, table), citations=r.citations, unmask_offer=offer,
    )
