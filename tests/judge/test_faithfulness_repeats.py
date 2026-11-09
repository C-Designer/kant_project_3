"""Faithfulness를 여러 번 채점해 평균내는 규칙: 값이 나온 회차만 평균, 빈칸을 0이나 1로 바꾸지 않는다."""

import pytest

from src import config
from src.contracts import TokenUsage
from src.judge import score as score_mod
from src.judge.score import score_one
from tests.judge.helpers import fake_llm, make_run, make_truth
from tests.judge.test_evaluation_table import judge_json

TOK = TokenUsage(input=10, output=5)


def _patch(monkeypatch, *results, repeats=None):
    """ragas_eval.faithfulness가 차례로 돌려줄 (점수, 토큰, 해당 없음 이유, 평가 불가 이유)를 정한다."""
    replies = list(results)
    monkeypatch.setattr(config, "FAITHFULNESS_REPEATS", repeats or len(replies))
    monkeypatch.setattr(score_mod.ragas_eval, "faithfulness", lambda run, llm: replies.pop(0))


def _score():
    return score_one(make_run(), make_truth(), fake_llm(judge_json()))


def test_값이_나온_회차를_평균하고_회차별_점수와_토큰_합계를_남긴다(monkeypatch):
    _patch(monkeypatch, (1.0, TOK, None, None), (0.0, TOK, None, None), (1.0, TOK, None, None))
    rec = _score()
    assert rec.faithfulness == pytest.approx(2 / 3)
    assert [r.score for r in rec.faithfulness_runs] == [1.0, 0.0, 1.0]
    assert all(r.reason is None for r in rec.faithfulness_runs)  # 값이 있는 회차에는 사유가 없다
    assert rec.eval_tokens.input >= 30  # 3회분 + 채점관 호출


def test_일부_회차가_실패하면_성공한_값만_평균하고_실패한_회차의_사유가_남는다_0으로_바꾸지_않는다(monkeypatch):
    _patch(monkeypatch, (1.0, TOK, None, None), (None, TOK, None, "RAGAS 계산 실패: X"), (0.5, TOK, None, None))
    rec = _score()
    assert rec.faithfulness == pytest.approx(0.75)
    assert [r.score for r in rec.faithfulness_runs] == [1.0, None, 0.5]
    assert [r.reason for r in rec.faithfulness_runs] == [None, "평가 불가: RAGAS 계산 실패: X", None]  # 디버깅용 사유
    assert not any(u.startswith("faithfulness") for u in rec.unscorable)  # 값이 있으니 빈칸이 아니다


def test_전부_실패하면_평가불가와_사유가_남는다(monkeypatch):
    _patch(monkeypatch, *[(None, TOK, None, "RAGAS 계산 실패: X")] * 3)
    rec = _score()
    assert rec.faithfulness is None and [r.score for r in rec.faithfulness_runs] == [None, None, None]
    assert "faithfulness: RAGAS 계산 실패: X" in rec.unscorable


def test_값이_없고_해당없음과_평가불가가_섞이면_해당없음을_우선한다(monkeypatch):
    _patch(monkeypatch, (None, TOK, None, "RAGAS 계산 실패: X"), (None, TOK, "사실 주장 없음", None), (None, TOK, "사실 주장 없음", None))
    rec = _score()
    assert rec.faithfulness is None
    assert "faithfulness: 사실 주장 없음" in rec.not_applicable
    assert [r.reason for r in rec.faithfulness_runs] == ["평가 불가: RAGAS 계산 실패: X", "해당 없음: 사실 주장 없음", "해당 없음: 사실 주장 없음"]
    assert not any(u.startswith("faithfulness") for u in rec.unscorable)


def test_반복이_1회면_한_번만_채점하고_예전과_같은_값이다(monkeypatch):
    _patch(monkeypatch, (0.75, TOK, None, None), repeats=1)
    rec = _score()
    assert rec.faithfulness == 0.75 and [r.score for r in rec.faithfulness_runs] == [0.75]


def test_RAGAS를_끄면_회차별_점수도_없다(monkeypatch):
    monkeypatch.setattr(config, "FAITHFULNESS_REPEATS", 3)
    rec = score_one(make_run(), make_truth(), fake_llm(judge_json()), use_ragas=False)
    assert rec.faithfulness is None and rec.faithfulness_runs is None


def test_어떤_회차만_사용량을_모르면_합계는_모른다고_둔다_빼고_더하지_않는다(monkeypatch):
    _patch(monkeypatch, (1.0, TOK, None, None), (None, None, None, "RAGAS 계산 실패: X"), (1.0, TOK, None, None))
    rec = score_one(make_run(), make_truth(), fake_llm(judge_json()))
    assert rec.eval_tokens.input is None and rec.eval_tokens.output is None
