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
    # status "error"도 지금은 HTTP 200으로 돌려준다 (정책 미정, issue #38)
    return QueryResponse(
        request_id=r.request_id, status=r.status, answer=r.answer, reason=r.reason, citations=r.citations
    )
