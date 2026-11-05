import json

import pytest

from src import config
from src.platform.query import run_query
from src.search import index
from tests.conftest import timeout_error


def _out(status="answered", ids=("S1",), answer="a"):
    return json.dumps({"status": status, "answer": answer, "reason": "r", "source_ids": list(ids)})


@pytest.fixture
def indexed(pdf_dir):
    rep = index.build_index(pdf_dir)
    assert rep["failed"] == [] and rep["chunks"] >= 2
    return rep


def test_naive_정상_답변과_출처는_코드가_만든다(indexed, fake_llm):
    # 모델이 파일명·쪽을 써도 무시된다: 출처는 source_ids로만 만든다
    fake_llm.script = [(_out(answer="free time 이후 일 단위로 부과 FB99.pdf p9"), 100, 20)]
    r = run_query("demurrage per day after free time", "naive")
    assert r.status == "answered" and r.error is None
    assert [(c.book_id, c.file_name) for c in r.citations] == [("FB01", "FB01.pdf")]
    assert r.citations[0].page == r.final_context[0].metadata.page
    assert r.retrieved_book_ids == ["FB01"]
    assert (r.input_tokens, r.output_tokens) == (100, 20)


def test_검색_결과가_없으면_LLM_없이_abstained(fake_llm):
    from src.search import store
    from qdrant_client.models import Distance, VectorParams

    store.get_client().create_collection(config.COLLECTION, vectors_config=VectorParams(size=64, distance=Distance.COSINE))
    r = run_query("anything", "naive")
    assert r.status == "abstained" and r.citations == []
    assert fake_llm.calls == 0
    assert r.input_tokens is None and r.output_tokens is None


def test_타임아웃은_error이고_확인된_사용량은_남는다(indexed, fake_llm):
    fake_llm.script = [("not json", 10, 5)] + [timeout_error()] * (1 + config.LLM_MAX_RETRIES)
    r = run_query("demurrage", "naive")
    assert r.status == "error" and r.reason == "model_timeout" and r.citations == []
    assert (r.input_tokens, r.output_tokens) == (10, 5)


def test_타임아웃만_나면_사용량은_None(indexed, fake_llm):
    fake_llm.script = [timeout_error()] * (1 + config.LLM_MAX_RETRIES)
    r = run_query("demurrage", "naive")
    assert r.reason == "model_timeout"
    assert (r.input_tokens, r.output_tokens) == (None, None)


def test_JSON이_두_번_깨지면_output_validation(indexed, fake_llm):
    fake_llm.script = ["not json", "still not json"]
    r = run_query("demurrage", "naive")
    assert (r.status, r.reason) == ("error", "output_validation")
    assert r.answer == "" and r.citations == []


def test_문맥_밖_source_ids는_답변으로_통과하지_못한다(indexed, fake_llm):
    fake_llm.script = [_out(ids=("S99",))] * 2
    r = run_query("demurrage", "naive")
    assert r.status != "answered" and r.reason == "output_validation"


@pytest.mark.parametrize("mode", ["hybrid", "hybrid_rerank"])
def test_미구현_방식은_mode_not_implemented(indexed, fake_llm, mode):
    r = run_query("demurrage", mode)
    assert (r.status, r.reason) == ("error", "mode_not_implemented")
    assert fake_llm.calls == 0


def test_색인이_없으면_index_missing(fake_llm):
    r = run_query("demurrage", "naive")
    assert (r.status, r.reason) == ("error", "index_missing")


def test_재생성_재시도_사용량은_합산된다(indexed, fake_llm):
    fake_llm.script = [("bad", 10, 5), (_out(), 20, 7)]
    r = run_query("demurrage", "naive")
    assert r.status == "answered"
    assert (r.input_tokens, r.output_tokens) == (30, 12)


def test_내부_오류는_원문을_노출하지_않는다(indexed, fake_llm, monkeypatch):
    from src.search import embed

    def boom(_):
        raise RuntimeError("secret-detail")

    monkeypatch.setattr(embed, "embed_query", boom)
    r = run_query("demurrage", "naive")
    assert r.reason == "internal_error" and "secret-detail" not in (r.error or "")
