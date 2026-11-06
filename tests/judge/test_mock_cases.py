"""채점관 시험지가 의도대로 만들어지는지 (실제 평가 JSON 필요, 없으면 건너뜀)."""

from pathlib import Path

import pytest

from src.judge.mock_cases import build_all

DEV = Path("data/shipping/evaluation/development.json")
pytestmark = pytest.mark.skipif(not DEV.exists(), reason="data/shipping/evaluation 없음")


def test_시험지_종류별로_만들어진다():
    cases = build_all([DEV])
    kinds = {c.kind for c in cases}
    assert {"good", "forbidden", "wrong_abstain", "no_context", "error", "time_swap"} <= kinds


def test_time_swap은_시각만_바꾼다():
    case = next(c for c in build_all([DEV]) if c.case_id == "S-DEV-05:time_swap")
    assert "오후 3시" in case.run.answer and "낮 12시" not in case.run.answer


def test_no_context는_문맥과_인용이_비어있다():
    for c in build_all([DEV]):
        if c.kind == "no_context":
            assert c.run.final_context == [] and c.run.citations == []
