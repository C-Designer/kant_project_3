from fastapi import FastAPI, Request

from src.contracts import QueryRequest, QueryResponse
from src.platform.query import run_query

app = FastAPI(title="shipping-rag")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query(req: QueryRequest, request: Request) -> QueryResponse:
    # Cloudflare Access 로그인 계정. 헤더가 없는 로컬 호출은 None → run_query가 TRACE_USER로 채운다
    email = request.headers.get("cf-access-authenticated-user-email")
    r = run_query(req.question, req.retrieval_mode, channel="api", user_id=email.split("@")[0] if email else None)
    # 처리된 요청은 status "error"여도 HTTP 200: 실패는 status·reason으로 구분한다 (#38)
    return QueryResponse(
        request_id=r.request_id, status=r.status, answer=r.answer, reason=r.reason, citations=r.citations
    )
