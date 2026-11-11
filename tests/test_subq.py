from contextlib import contextmanager
from types import SimpleNamespace

from src import config
from src.contracts import ChunkMeta, RetrievedChunk
from src.platform.llm import LLMError
from src.search import retrieve, subq


def chunk(cid: str) -> RetrievedChunk:
    return RetrievedChunk(text=cid, score=0.5, metadata=ChunkMeta(book_id="T", file_name="T.pdf", page=1, chunk_id=cid))


def ids(chunks) -> list[str]:
    return [c.metadata.chunk_id for c in chunks]


def test_alternate_takes_each_rank_in_turn_and_skips_duplicates():
    first, second = [chunk(c) for c in "ABCD"], [chunk(c) for c in "AEFG"]
    assert ids(retrieve._alternate([first, second], 5)) == ["A", "B", "E", "C", "F"]  # 둘째 목록의 A는 건너뛴다
    assert ids(retrieve._alternate([first, second], 99)) == ["A", "B", "E", "C", "F", "D", "G"]  # 후보가 모자라면 있는 만큼
    assert retrieve._alternate([], 5) == []


def test_decompose_caps_count_and_falls_back_to_empty(monkeypatch):
    reply = lambda text: (lambda *a, **kw: SimpleNamespace(text=text))
    monkeypatch.setattr(subq.llm, "call", reply('앞말 ["a", "b", "c", "d", "e"] 뒷말'))
    assert subq.decompose("q") == ["a", "b", "c", "d"][: config.SUBQ_MAX]
    monkeypatch.setattr(subq.llm, "call", reply("배열이 없다"))
    assert subq.decompose("q") == []
    monkeypatch.setattr(subq.llm, "call", reply("[깨진 JSON"))
    assert subq.decompose("q") == []

    def boom(*a, **kw):
        raise LLMError("시간 초과", "model_timeout")

    monkeypatch.setattr(subq.llm, "call", boom)
    assert subq.decompose("q") == []


def test_subq_mode_reranks_pool_per_sub_question(monkeypatch):
    recorded = {}

    @contextmanager
    def span(name, **kwargs):
        yield SimpleNamespace(update=lambda **values: recorded.update(values))

    pool = {c: chunk(c) for c in "ABCDE"}
    order = {"q1": "ABCDE", "q2": "EDCBA", "원문": "ABCDE"}  # 검색어마다 리랭크 순위가 다르다
    monkeypatch.setattr(retrieve.tracing, "span", span)
    monkeypatch.setattr(retrieve, "_dense", lambda q, n: list(pool.values()))
    monkeypatch.setattr(retrieve, "_keyword", lambda q, n: [])
    monkeypatch.setattr(retrieve.rerank, "rerank", lambda q, cands, k: [pool[c] for c in order[q]][:k])

    monkeypatch.setattr(retrieve.subq, "decompose", lambda q: ["q1", "q2"])
    assert ids(retrieve.retrieve("원문", "hybrid_rerank_subq", 3)) == ["A", "E", "B"]
    assert recorded["metadata"]["sub_questions"] == ["q1", "q2"]

    monkeypatch.setattr(retrieve.subq, "decompose", lambda q: ["하나뿐"])  # 2개 미만이면 원래 질문 하나로
    assert ids(retrieve.retrieve("원문", "hybrid_rerank_subq", 3)) == ["A", "B", "C"]
