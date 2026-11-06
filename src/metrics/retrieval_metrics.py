"""검색 지표 Hit@k, Recall@k (발제 STEP 6, docs/evaluation.md).

- 정답 기준: 문항 evidence_groups의 모든 book_id를 모아 중복 제거한 목록.
- 상위 k개 청크의 book_id와 대조하고, 같은 문서는 한 번만 센다.
- 참고 목록이 비면 해당 없음(None + 이유). 검색 결과가 비어도 참고 문서가 있으면 0점.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalScore:
    hit: int | None
    recall: float | None
    not_applicable: str | None = None


def hit_recall(
    evidence_book_ids: list[str],
    retrieved_book_ids: list[str],
    k: int,
) -> RetrievalScore:
    """retrieved_book_ids는 순위순 청크별 book_id. 앞의 k개만 쓴다."""
    if k < 1:
        raise ValueError(f"k는 1 이상이어야 한다: {k}")

    evidence = set(evidence_book_ids)
    if not evidence:
        return RetrievalScore(None, None, "참고 근거 문서 목록이 비어 있다")

    found = evidence & set(retrieved_book_ids[:k])
    return RetrievalScore(
        hit=1 if found else 0,
        recall=len(found) / len(evidence),
    )
