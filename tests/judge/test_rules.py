"""발제 규칙 고정: 0과 None(빈칸)을 섞지 않는다."""

from src.judge.rules import mean_ignoring_none, precheck, summarize
from tests.judge.helpers import make_run


def test_평균에서_None은_빼고_0은_넣는다():
    assert mean_ignoring_none([1, 1, 0, None]) == 2 / 3


def test_모두_None이면_평균도_None이다_0이_아니다():
    assert mean_ignoring_none([None, None]) is None
    assert mean_ignoring_none([]) is None


def test_요약에_평가대상수와_빈칸수가_나온다():
    assert summarize([1, 0, None]) == {"mean": 0.5, "n_scored": 2, "n_null": 1}


def test_정상_답안은_사전판정하지_않는다():
    assert precheck(make_run(status="answered")) is None


def test_서비스오류면_판단은_0_나머지는_평가불가():
    rec = precheck(make_run(status="error", error="model_timeout"))
    assert rec is not None
    assert rec.judge["decision"].score == 0
    for item in ("facts", "conditions", "evidence"):
        assert rec.judge[item].score is None
        assert rec.judge[item].reason.startswith("평가 불가")
    assert rec.faithfulness is None
    assert rec.eval_tokens is None  # 호출을 안 했으니 0이 아니라 None
    assert any(u.startswith("faithfulness:") for u in rec.unscorable)
    assert rec.not_applicable == []
