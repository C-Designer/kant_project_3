import json

import pytest
from fastapi.testclient import TestClient

from src import config
from src.api.main import app
from src.search import index
from tests.conftest import timeout_error

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_query_정상(pdf_dir, fake_llm):
    index.build_index(pdf_dir)
    fake_llm.script = [json.dumps({"status": "answered", "answer": "a", "reason": "r", "source_ids": ["S1"]})]
    r = client.post("/query", json={"question": "demurrage per day", "retrieval_mode": "naive"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "answered" and body["request_id"]
    assert body["citations"][0]["book_id"] == "FB01"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "", "retrieval_mode": "naive"},
        {"question": "   ", "retrieval_mode": "naive"},
        {"question": "q", "retrieval_mode": "bm25"},
    ],
)
def test_잘못된_요청은_422(payload):
    assert client.post("/query", json=payload).status_code == 422


def test_error_상태도_HTTP_200(fake_llm):
    r = client.post("/query", json={"question": "q", "retrieval_mode": "naive"})
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["reason"]) == ("error", "index_missing")


def test_timeout도_HTTP_200(pdf_dir, fake_llm):
    index.build_index(pdf_dir)
    fake_llm.script = [timeout_error()] * (1 + config.LLM_MAX_RETRIES)
    r = client.post("/query", json={"question": "demurrage", "retrieval_mode": "naive"})
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["reason"], r.json()["citations"]) == ("error", "model_timeout", [])
