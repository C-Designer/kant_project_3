import json

import pytest
from fastapi.testclient import TestClient

from src import config
from src.answer import masking
from src.api.main import app
from src.search import index
from tests.conftest import make_pdf, timeout_error

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


def test_질문의_개인정보만_가리고_답에서_되돌린다(tmp_path, fake_llm):
    # 검색 자료의 번호(02-123-4567)는 그대로 가고, 질문의 번호만 자리표시자로 간다
    d = tmp_path / "documents"
    d.mkdir()
    (d / "FB01.pdf").write_bytes(make_pdf(["Demurrage desk 02-123-4567. Demurrage is charged per day."]))
    index.build_index(d)
    fake_llm.script = [json.dumps(
        {"status": "answered", "answer": "<전화1>로는 안내하지 않고 02-123-4567로 문의합니다", "reason": "r", "source_ids": ["S1"]}
    )]
    r = client.post("/query", json={"question": "demurrage 결과를 010-1234-5678로 받을 수 있나요?", "retrieval_mode": "naive"})
    sent = fake_llm.seen[0][1]["content"]
    assert "010-1234-5678" not in sent and "<전화1>" in sent and "02-123-4567" in sent
    assert r.json()["answer"] == "010-1234-5678로는 안내하지 않고 02-123-4567로 문의합니다"


def test_가린_채_답하지_못하면_해제_재질문을_제안한다(pdf_dir, fake_llm):
    index.build_index(pdf_dir)
    fake_llm.script = [json.dumps({"status": "abstained", "answer": "a", "reason": "r", "source_ids": []})]
    r = client.post("/query", json={"question": "demurrage 010-1234-5678", "retrieval_mode": "naive"})
    assert r.json()["unmask_offer"] == masking.UNMASK_OFFER


@pytest.mark.parametrize(
    "question, script",
    [
        ("demurrage", [json.dumps({"status": "abstained", "answer": "a", "reason": "r", "source_ids": []})]),  # 가린 값 없음
        ("demurrage 010-1234-5678", [json.dumps({"status": "answered", "answer": "a", "reason": "r", "source_ids": ["S1"]})]),
        ("demurrage 010-1234-5678", [timeout_error()] * (1 + config.LLM_MAX_RETRIES)),  # 시스템 오류는 마스킹 탓이 아니다
    ],
)
def test_마스킹과_무관하면_제안하지_않는다(pdf_dir, fake_llm, question, script):
    index.build_index(pdf_dir)
    fake_llm.script = script
    r = client.post("/query", json={"question": question, "retrieval_mode": "naive"})
    assert r.json()["unmask_offer"] is None


def test_동의한_재질문은_원문을_보내고_다시_제안하지_않는다(pdf_dir, fake_llm):
    index.build_index(pdf_dir)
    fake_llm.script = [json.dumps({"status": "abstained", "answer": "a", "reason": "r", "source_ids": []})]
    r = client.post("/query", json={"question": "demurrage 010-1234-5678", "retrieval_mode": "naive", "unmask": True})
    assert "010-1234-5678" in fake_llm.seen[0][1]["content"]
    assert r.json()["unmask_offer"] is None
