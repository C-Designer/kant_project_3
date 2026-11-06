import pytest

from src.contracts import RunRecord
from src.metrics.ops_metrics import summarize_ops


def rec(qid, mode="naive", status="answered", latency=None, inp=None, out=None, error=None):
    return RunRecord(
        question_id=qid,
        request_id=f"req-{qid}-{mode}",
        retrieval_mode=mode,
        question="q",
        status=status,
        answer="",
        reason="",
        citations=[],
        retrieved_book_ids=[],
        final_context=[],
        latency_ms=latency,
        input_tokens=inp,
        output_tokens=out,
        error=error,
    )


def test_ok_latency_mean_and_count_exclude_errors():
    s = summarize_ops(
        [
            rec("1", latency=100),
            rec("2", latency=300),
            rec("3", status="error", latency=5000, error="model_timeout"),
        ]
    )["naive"]
    assert s.ok_count == 2
    assert s.ok_latency_mean_ms == 200
    assert s.ok_latency_known == 2


def test_failed_request_latency_is_recorded_separately():
    s = summarize_ops([rec("1", status="error", latency=5000, error="x"), rec("2", latency=100)])["naive"]
    assert s.error_latency_mean_ms == 5000


def test_error_rate_and_counts():
    records = [rec(str(i)) for i in range(9)] + [rec("e", status="error", error="x")]
    s = summarize_ops(records)["naive"]
    assert (s.total, s.error_count) == (10, 1)
    assert s.error_rate_pct == pytest.approx(10.0)


def test_clarification_and_abstention_are_not_errors():
    s = summarize_ops([rec("1", status="needs_clarification"), rec("2", status="abstained")])["naive"]
    assert s.error_count == 0 and s.error_rate_pct == 0.0
    assert s.ok_count == 2


def test_none_latency_is_excluded_from_denominator_not_zero():
    s = summarize_ops([rec("1", latency=100), rec("2", latency=None), rec("3", latency=300)])["naive"]
    assert s.ok_count == 3  # 정상 요청 수는 그대로
    assert s.ok_latency_known == 2  # 시간을 잰 요청만 평균에 포함
    assert s.ok_latency_mean_ms == 200


def test_all_latency_unknown_gives_none_not_zero():
    s = summarize_ops([rec("1"), rec("2")])["naive"]
    assert s.ok_latency_mean_ms is None


def test_token_sums_with_known_counts_and_none_skipped():
    s = summarize_ops([rec("1", inp=100, out=10), rec("2", inp=None, out=None), rec("3", inp=50, out=5)])["naive"]
    assert (s.input_tokens_sum, s.input_tokens_known) == (150, 2)
    assert (s.output_tokens_sum, s.output_tokens_known) == (15, 2)


def test_tokens_unknown_everywhere_is_none_not_zero():
    s = summarize_ops([rec("1"), rec("2")])["naive"]
    assert s.input_tokens_sum is None and s.input_tokens_known == 0
    assert s.output_tokens_sum is None and s.output_tokens_known == 0


def test_failed_requests_usage_is_included_in_token_sum():
    s = summarize_ops([rec("1", inp=100, out=10), rec("2", status="error", inp=40, out=0, error="x")])["naive"]
    assert s.input_tokens_sum == 140


def test_grouped_by_retrieval_mode():
    out = summarize_ops([rec("1", mode="naive", latency=100), rec("1", mode="hybrid", latency=200)])
    assert set(out) == {"naive", "hybrid"}
    assert out["hybrid"].ok_latency_mean_ms == 200


def test_empty_input_returns_empty_dict():
    assert summarize_ops([]) == {}
