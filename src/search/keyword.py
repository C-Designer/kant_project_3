"""키워드 검색 (BM25, search 영역).

dense 검색(E5)은 뜻이 비슷한 글을 찾고, 이 모듈은 같은 글자가 있는 청크를 찾는다.
`20GP`, `SB01` 같은 코드나 숫자는 뜻이 아니라 글자가 같아야 하므로 이쪽이 더 잘 찾는다.

한국어는 띄어쓰기 단위로 쪼개면 "예약을"과 "예약"이 서로 다른 단어가 된다.
그래서 글자 두 개씩 겹쳐 자른 조각(2-gram)을 단어로 쓴다. 예: "예약을" -> "예약", "약을".
BM25 인덱스는 Qdrant에 저장하지 않고 청크 글에서 메모리로 만든다 (ADR 미정, #14).
"""

import math
import re
from collections import Counter

from src import config
from src.contracts import ChunkMeta
from src.search import store

K1 = 1.5  # 같은 조각이 여러 번 나와도 점수가 무한히 커지지 않게 누르는 정도
B = 0.75  # 긴 청크의 점수를 깎는 정도 (0이면 길이를 무시)

_NOISE = re.compile(r"\s+")


def tokenize(text: str) -> list[str]:
    """공백을 지우고 소문자로 바꾼 뒤 글자 2개씩 겹쳐 자른다. 한 글자뿐이면 그 글자 하나."""
    s = _NOISE.sub("", text.lower())
    if len(s) < 2:
        return [s] if s else []
    return [s[i : i + 2] for i in range(len(s) - 1)]


class Bm25Index:
    def __init__(self, docs: list[str]):
        self.tfs = [Counter(tokenize(d)) for d in docs]  # 문서별 조각 개수
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.n = len(docs)
        self.avg_len = sum(self.lens) / self.n if self.n else 0.0
        df: Counter[str] = Counter()  # 그 조각이 든 문서 수
        for tf in self.tfs:
            df.update(tf.keys())
        # 드문 조각일수록 무게가 크다
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        """모든 문서의 점수. 질문의 조각이 하나도 없으면 0."""
        out = [0.0] * self.n
        q_tokens = set(tokenize(query))
        for i, tf in enumerate(self.tfs):
            norm = K1 * (1 - B + B * self.lens[i] / self.avg_len) if self.avg_len else K1
            s = 0.0
            for t in q_tokens:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (K1 + 1) / (f + norm)
            out[i] = s
        return out

    def top(self, query: str, k: int) -> list[tuple[int, float]]:
        """(문서 위치, 점수)를 점수 높은 순으로 k개. 점수 0인 문서는 뺀다."""
        sc = self.scores(query)
        ranked = sorted(range(self.n), key=lambda i: sc[i], reverse=True)[:k]
        return [(i, sc[i]) for i in ranked if sc[i] > 0]


_cache: tuple[Bm25Index, list[tuple[str, ChunkMeta]]] | None = None


def load() -> tuple[Bm25Index, list[tuple[str, ChunkMeta]]]:
    """Qdrant의 청크 글로 BM25를 만든다. 한 번 만들면 재사용한다. 색인을 다시 했으면 reset()."""
    global _cache
    if _cache is None:
        client = store.get_client()
        chunks: list[tuple[str, ChunkMeta]] = []
        offset = None
        while True:
            points, offset = store.call(
                client.scroll, config.COLLECTION, limit=256, offset=offset, with_payload=True, with_vectors=False
            )
            for p in points:
                meta = ChunkMeta(**{f: p.payload[f] for f in ChunkMeta.model_fields})
                chunks.append((p.payload["text"], meta))
            if offset is None:
                break
        chunks.sort(key=lambda c: c[1].chunk_id)  # 순서를 고정해 점수가 같을 때 결과가 흔들리지 않게
        _cache = (Bm25Index([t for t, _ in chunks]), chunks)
    return _cache


def reset() -> None:
    global _cache
    _cache = None
