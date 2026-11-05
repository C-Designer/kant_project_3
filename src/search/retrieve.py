import time

from src import config
from src.contracts import ChunkMeta, RetrievalMode, RetrievedChunk
from src.platform import tracing
from src.search import embed, store


class IndexNotFound(RuntimeError):
    pass


def retrieve(query: str, mode: RetrievalMode, k: int) -> list[RetrievedChunk]:
    if mode in ("hybrid", "hybrid_rerank"):
        raise NotImplementedError("search 담당 구현 예정 (#15/#16)")
    if mode != "naive":
        raise ValueError(f"지원하지 않는 retrieval_mode: {mode}")

    with tracing.span("retrieve", input=query) as sp:
        t0 = time.perf_counter()
        client = store.get_client()
        if not client.collection_exists(config.COLLECTION):
            raise IndexNotFound(f"컬렉션 {config.COLLECTION}이 없다. 먼저 색인한다")
        hits = client.query_points(
            config.COLLECTION, query=embed.embed_query(query), limit=k, with_payload=True
        ).points
        chunks = [
            RetrievedChunk(
                text=h.payload["text"],
                score=h.score,
                metadata=ChunkMeta(**{f: h.payload[f] for f in ChunkMeta.model_fields}),
            )
            for h in sorted(hits, key=lambda h: h.score, reverse=True)[:k]
        ]
        sp.update(
            metadata={
                "mode": mode,
                "k": k,
                "chunk_ids": [c.metadata.chunk_id for c in chunks],
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            }
        )
        return chunks
