import pytest
from pydantic import ValidationError

from src.answer.validate import ValidationFailed, parse_output
from src.contracts import ChunkMeta, ContextChunk, QueryRequest, book_id_from_file_name
from src.metrics.aggregate import mean_excluding_none
from src.platform import llm


def _ctx(*ids):
    return [
        ContextChunk(source_id=i, text="t", metadata=ChunkMeta(book_id="FB01", file_name="FB01.pdf", page=1, chunk_id=f"FB01-p1-c{n}"))
        for n, i in enumerate(ids, 1)
    ]


def test_평균은_None을_빼고_0으로_바꾸지_않는다():
    assert mean_excluding_none([1.0, None, 0.0]) == 0.5
    assert mean_excluding_none([None, None]) is None
    assert mean_excluding_none([]) is None


def test_source_ids는_문맥_id의_부분집합이어야_한다():
    ok = '{"status":"answered","answer":"a","reason":"r","source_ids":["S1"]}'
    assert parse_output(ok, _ctx("S1", "S2")).source_ids == ["S1"]
    bad = '{"status":"answered","answer":"a","reason":"r","source_ids":["S9"]}'
    with pytest.raises(ValidationFailed):
        parse_output(bad, _ctx("S1"))


def test_answered는_source_ids가_비면_거부():
    with pytest.raises(ValidationFailed):
        parse_output('{"status":"answered","answer":"a","reason":"r","source_ids":[]}', _ctx("S1"))


def test_코드펜스는_벗긴다():
    raw = '```json\n{"status":"abstained","answer":"","reason":"r","source_ids":[]}\n```'
    assert parse_output(raw, _ctx("S1")).status == "abstained"


def test_book_id는_파일명에서_pdf를_뺀_값():
    assert book_id_from_file_name("FB01.pdf") == "FB01"


@pytest.mark.parametrize("q", ["", "   ", "\n"])
def test_빈_질문은_거부(q):
    with pytest.raises(ValidationError):
        QueryRequest(question=q, retrieval_mode="naive")


def test_제공자가_사용량을_안_주면_None(fake_llm):
    fake_llm.script = ["x"]
    with llm.usage_scope() as u:
        r = llm.call([{"role": "user", "content": "q"}])
    assert (r.input_tokens, r.output_tokens) == (None, None)
    assert (u.input_tokens, u.output_tokens) == (None, None)
    assert r.latency_ms is not None


def test_평가_호출은_평가_모델이_없으면_거부(fake_llm, monkeypatch):
    monkeypatch.setattr("src.config.EVAL_MODEL", None)
    with pytest.raises(llm.LLMError):
        llm.call([{"role": "user", "content": "q"}], kind="eval")
    assert fake_llm.calls == 0
