from src.contracts import ChunkMeta, ContextChunk, RetrievedChunk
from src.platform import tracing


def count_tokens(text: str) -> int:
    # shortcut: 글자 수 근사(tiktoken은 어휘를 네트워크로 받음), 한도에 빠듯해지면 실제 토크나이저로 교체
    return len(text) // 2 + 1


def build_context(chunks: list[RetrievedChunk], *, token_limit: int) -> list[ContextChunk]:
    with tracing.span("build_context", input={"chunk_ids": [c.metadata.chunk_id for c in chunks], "token_limit": token_limit}) as sp:
        context: list[ContextChunk] = []
        used = 0
        dropped: list[str] = []
        for c in chunks:
            n = count_tokens(c.text)
            if dropped or (context and used + n > token_limit):
                dropped.append(c.metadata.chunk_id)
                continue
            text = c.text
            if not context and n > token_limit:  # 첫 조각이 한도보다 크면 잘라서라도 넣는다
                text = text[: max(1, 2 * (token_limit - 1))]
                n = count_tokens(text)
            context.append(ContextChunk(source_id=f"S{len(context) + 1}", text=text, metadata=c.metadata))
            used += n
        sp.update(output=[c.model_dump() for c in context], metadata={"dropped_chunk_ids": dropped, "tokens": used})
        return context


def source_map(context: list[ContextChunk]) -> dict[str, ChunkMeta]:
    return {c.source_id: c.metadata for c in context}
