import time

from src import config
from src.contracts import ChunkMeta, RetrievalMode, RetrievedChunk
from src.platform import tracing
from src.search import embed, keyword, rerank, store

RRF_K = 60  # RRF 상수. 순위가 1등이든 2등이든 점수 차이가 너무 벌어지지 않게 하는 값 (잠정, #15)
POOL = 20  # hybrid에서 E5·BM25 각각 상위 몇 개까지 후보로 보는지 (잠정, #15)


class IndexNotFound(RuntimeError):
    pass


def _meta(payload: dict) -> ChunkMeta:
    return ChunkMeta(**{f: payload[f] for f in ChunkMeta.model_fields})


def _dense(query: str, n: int) -> list[RetrievedChunk]:
    """E5 의미 검색. 점수(코사인) 높은 순으로 n개."""
    client = store.get_client()
    if not client.collection_exists(config.COLLECTION):
        raise IndexNotFound(f"컬렉션 {config.COLLECTION}이 없다. 먼저 색인한다")
    hits = client.query_points(
        config.COLLECTION, query=embed.embed_query(query), limit=n, with_payload=True
    ).points
    return [
        RetrievedChunk(text=h.payload["text"], score=h.score, metadata=_meta(h.payload))
        for h in sorted(hits, key=lambda h: h.score, reverse=True)[:n]
    ]


def _keyword(query: str, n: int) -> list[RetrievedChunk]:
    """BM25 키워드 검색. 점수 높은 순으로 n개."""
    index, chunks = keyword.load()
    return [
        RetrievedChunk(text=chunks[i][0], score=s, metadata=chunks[i][1])
        for i, s in index.top(query, n)
    ]


def _rrf(rankings: list[list[RetrievedChunk]], k: int) -> list[RetrievedChunk]:
    """여러 순위를 합친다. 점수는 버리고 순위만 쓴다: 합계 = sum(1 / (RRF_K + 순위))."""
    fused: dict[str, float] = {}
    by_id: dict[str, RetrievedChunk] = {}
    for ranking in rankings:
        for rank, c in enumerate(ranking, start=1):
            cid = c.metadata.chunk_id
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
            by_id[cid] = c
    # 점수가 같으면 chunk_id 순으로 두어 결과가 흔들리지 않게 한다
    top = sorted(fused, key=lambda cid: (-fused[cid], cid))[:k]
    return [RetrievedChunk(text=by_id[c].text, score=fused[c], metadata=by_id[c].metadata) for c in top]


def retrieve(query: str, mode: RetrievalMode, k: int) -> list[RetrievedChunk]:
    if mode not in ("naive", "hybrid", "hybrid_rerank"):
        raise ValueError(f"지원하지 않는 retrieval_mode: {mode}")

    with tracing.span("retrieve", input=query) as sp:
        t0 = time.perf_counter()
        if mode == "naive":
            chunks = _dense(query, k)
        elif mode == "hybrid":
            chunks = _rrf([_dense(query, POOL), _keyword(query, POOL)], k)
        else:  # hybrid_rerank: hybrid로 후보를 넉넉히 뽑고 리랭커가 다시 정렬해 k개만 남긴다
            candidates = _rrf(
                [_dense(query, POOL), _keyword(query, POOL)], rerank.RERANK_CANDIDATES
            )
            chunks = rerank.rerank(query, candidates, k)
        sp.update(
            metadata={
                "mode": mode,
                "k": k,
                "chunk_ids": [c.metadata.chunk_id for c in chunks],
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            }
        )
        return chunks
