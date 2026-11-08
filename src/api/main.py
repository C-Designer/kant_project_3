from fastapi import FastAPI

from src.contracts import QueryRequest, QueryResponse
from src.platform.query import run_query

app = FastAPI(title="shipping-rag")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query")
def query(req: QueryRequest) -> QueryResponse:
    r = run_query(req.question, req.retrieval_mode)
    # 처리된 요청은 status "error"여도 HTTP 200: 실패는 status·reason으로 구분한다 (#38)
    return QueryResponse(
        request_id=r.request_id, status=r.status, answer=r.answer, reason=r.reason, citations=r.citations
    )
