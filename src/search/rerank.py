"""리랭커 (search 영역, #16).

hybrid가 뽑은 후보를 질문과 한 쌍으로 묶어 cross-encoder가 다시 점수를 매기고 순서를 바꾼다.
E5는 질문과 청크를 따로 벡터로 만들어 비교하지만, 리랭커는 둘을 한꺼번에 읽어서 더 정확하다.
대신 쌍마다 모델을 한 번씩 돌려서 느리므로, 전체 청크가 아니라 후보 몇 개에만 쓴다.
"""

from src import config
from src.contracts import RetrievedChunk

MAX_LENGTH = 768  # 질문 + 청크 입력 한도(토큰). 청크가 최대 약 510토큰이라 잘리지 않게 넉넉히

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder  # 무거워서 쓸 때 불러온다

        _model = CrossEncoder(config.RERANKER_MODEL, max_length=MAX_LENGTH)
    return _model


def rerank(query: str, candidates: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
    """후보를 리랭커 점수 순으로 정렬해 상위 k개를 돌려준다. 점수는 0~1 (높을수록 관련 있음)."""
    if not candidates:
        return []
    scores = _get_model().predict([(query, c.text) for c in candidates], batch_size=8)
    ranked = sorted(zip(candidates, scores), key=lambda p: -float(p[1]))[:k]
    return [
        RetrievedChunk(text=c.text, score=float(s), metadata=c.metadata) for c, s in ranked
    ]
