from sentence_transformers import SentenceTransformer

from src import config

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _model


def _encode(texts: list[str]) -> list[list[float]]:
    return _get_model().encode(texts, normalize_embeddings=True).tolist()


def _prefixes() -> tuple[str, str]:
    """(문서 접두어, 질문 접두어). E5 계열(KoE5 포함)은 붙이고, bge 계열 등은 붙이지 않는다."""
    if "e5" in config.EMBEDDING_MODEL.lower():
        return "passage: ", "query: "
    return "", ""


def embed_passages(texts: list[str]) -> list[list[float]]:
    prefix = _prefixes()[0]
    return _encode([f"{prefix}{t}" for t in texts])


def embed_query(text: str) -> list[float]:
    prefix = _prefixes()[1]
    return _encode([f"{prefix}{text}"])[0]
