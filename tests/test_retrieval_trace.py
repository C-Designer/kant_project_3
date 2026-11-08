from contextlib import contextmanager

from src.answer.context import build_context
from src.contracts import ChunkMeta, RetrievedChunk
from src.search import retrieve


def test_trace_keeps_retrieved_text_before_context_truncation(monkeypatch):
    recorded = {}

    @contextmanager
    def span(name, **kwargs):
        class Handle:
            def update(self, **values):
                recorded[name] = values

        yield Handle()

    chunks = [
        RetrievedChunk(
            text="abcdefgh",
            score=0.8,
            metadata=ChunkMeta(book_id="TEST", file_name="TEST.pdf", page=1, chunk_id="TEST-p1-c1"),
        )
    ]
    monkeypatch.setattr(retrieve.tracing, "span", span)
    monkeypatch.setattr(retrieve, "_dense", lambda query, n: chunks)

    found = retrieve.retrieve("question", "naive", 1)
    build_context(found, token_limit=3)

    assert recorded["retrieve"]["output"][0]["text"] == "abcdefgh"
    assert recorded["retrieve"]["output"][0]["metadata"]["page"] == 1
    assert recorded["build_context"]["output"][0]["text"] == "abcd"
