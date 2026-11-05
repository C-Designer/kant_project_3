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


def embed_passages(texts: list[str]) -> list[list[float]]:
    return _encode([f"passage: {t}" for t in texts])


def embed_query(text: str) -> list[float]:
    return _encode([f"query: {text}"])[0]
