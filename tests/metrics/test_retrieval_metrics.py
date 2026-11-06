import pytest

from src.metrics.retrieval_metrics import hit_recall


def test_hit_and_full_recall_when_single_evidence_found():
    s = hit_recall(["DEMO_NOTICE"], ["DEMO_MANUAL", "DEMO_NOTICE"], k=2)
    assert (s.hit, s.recall, s.not_applicable) == (1, 1.0, None)


def test_zero_when_evidence_not_retrieved():
    s = hit_recall(["DEMO_NOTICE"], ["DEMO_MANUAL", "DEMO_B"], k=2)
    assert (s.hit, s.recall) == (0, 0.0)


def test_partial_recall_when_one_of_two_found():
    s = hit_recall(["A", "B"], ["A", "X"], k=2)
    assert (s.hit, s.recall) == (1, 0.5)


def test_same_document_counted_once():
    s = hit_recall(["A", "B"], ["A", "A", "A"], k=3)
    assert s.recall == 0.5


def test_only_top_k_chunks_are_used():
    s = hit_recall(["A"], ["X", "Y", "A"], k=2)
    assert (s.hit, s.recall) == (0, 0.0)


def test_empty_retrieval_with_evidence_is_zero_not_excluded():
    s = hit_recall(["A"], [], k=2)
    assert (s.hit, s.recall, s.not_applicable) == (0, 0.0, None)


def test_empty_evidence_is_not_applicable_with_reason():
    s = hit_recall([], ["A", "B"], k=2)
    assert s.hit is None and s.recall is None
    assert s.not_applicable


def test_duplicate_evidence_ids_are_deduped():
    s = hit_recall(["A", "A", "B"], ["A"], k=2)
    assert s.recall == 0.5


def test_invalid_k_raises():
    with pytest.raises(ValueError):
        hit_recall(["A"], ["A"], k=0)
