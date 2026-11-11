import time
from itertools import zip_longest
from typing import get_args

from src import config
from src.contracts import ChunkMeta, RetrievalMode, RetrievedChunk
from src.platform import tracing
from src.search import embed, keyword, rerank, store, subq

RRF_K = 60  # RRF 상수. 순위가 1등이든 2등이든 점수 차이가 너무 벌어지지 않게 하는 값 (잠정, #15)
POOL = 20  # hybrid에서 E5·BM25 각각 상위 몇 개까지 후보로 보는지 (잠정, #15)


class IndexNotFound(RuntimeError):
    pass


def _meta(payload: dict) -> ChunkMeta:
    return ChunkMeta(**{f: payload[f] for f in ChunkMeta.model_fields})


def _dense(query: str, n: int) -> list[RetrievedChunk]:
    """E5 의미 검색. 점수(코사인) 높은 순으로 n개."""
    client = store.get_client()
    if not store.call(client.collection_exists, config.COLLECTION):
        raise IndexNotFound(f"컬렉션 {config.COLLECTION}이 없다. 먼저 색인한다")
    hits = store.call(
        client.query_points, config.COLLECTION, query=embed.embed_query(query), limit=n, with_payload=True
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


def _alternate(rankings: list[list[RetrievedChunk]], k: int) -> list[RetrievedChunk]:
    """순위 목록들의 1위, 2위, …를 번갈아 담는다. 이미 담은 청크는 건너뛰고 k개가 차면 멈춘다."""
    picked: dict[str, RetrievedChunk] = {}
    for tier in zip_longest(*rankings):
        for c in tier:
            if c is not None and c.metadata.chunk_id not in picked:
                picked[c.metadata.chunk_id] = c
                if len(picked) == k:
                    return list(picked.values())
    return list(picked.values())


def _subq_chunks(terms: list[str], k: int) -> list[RetrievedChunk]:
    """검색어마다 hybrid로 후보를 뽑아 RRF로 합치고, 그 후보 전체를 검색어마다 따로 리랭크한 순위를 번갈아 담는다."""
    n = config.SUBQ_CANDIDATES
    pool = _rrf([_rrf([_dense(t, n), _keyword(t, n)], n) for t in terms], n)
    return _alternate([rerank.rerank(t, pool, len(pool)) for t in terms], k)


def retrieve(query: str, mode: RetrievalMode, k: int) -> list[RetrievedChunk]:
    if mode not in get_args(RetrievalMode):
        raise ValueError(f"지원하지 않는 retrieval_mode: {mode}")

    with tracing.span("retrieve", input=query) as sp:
        t0 = time.perf_counter()
        extra = {}
        if mode == "naive":
            chunks = _dense(query, k)
        elif mode == "hybrid":
            chunks = _rrf([_dense(query, POOL), _keyword(query, POOL)], k)
        elif mode == "hybrid_rerank":  # hybrid로 후보를 넉넉히 뽑고 리랭커가 다시 정렬해 k개만 남긴다
            candidates = _rrf(
                [_dense(query, POOL), _keyword(query, POOL)], config.RERANK_CANDIDATES
            )
            chunks = rerank.rerank(query, candidates, k)
        else:  # hybrid_rerank_subq: 하위 질문별 리랭크 순위를 번갈아 담는다. 하위 질문이 2개 미만이면 원래 질문 하나
            subs = subq.decompose(query)
            chunks = _subq_chunks(subs if len(subs) >= 2 else [query], k)
            extra = {"sub_questions": subs}
        sp.update(
            output=[c.model_dump() for c in chunks],
            metadata={
                "mode": mode,
                "k": k,
                "chunk_ids": [c.metadata.chunk_id for c in chunks],
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                **extra,
            }
        )
        return chunks
