"""docs/evaluation.md '해당 없음 / 평가 불가 / 오류' 표의 5행을 1:1로 고정한다 (Issue #32).

| 행 | 상황 | 기록 |
| 1 | 필요한 수치가 틀리거나 필수 사실·인용을 빠뜨림 | Judge 해당 항목 0 (해당 없음 아님) |
| 2 | 사실 주장 없이 조건만 되물음 | Faithfulness 해당 없음, 판단 항목은 채점 |
| 3 | 평가할 대상이 없는 Judge 항목 | 해당 없음. 단, 추가 확인·보류의 판단 항목은 평가 |
| 4 | 서비스 오류로 답변을 못 만듦 | 판단 0, 확인 못 하는 항목은 평가 불가 |
| 5 | 답변은 있지만 채점 호출·지표 계산 실패 | 해당 평가 평가 불가 + 사유. 0이나 1로 바꾸지 않음 |
"""

import json

import pytest

from src.judge.judge import JudgeParseError, parse_judge_output
from src.judge.rules import mean_ignoring_none
from src.judge.score import score_one
from tests.judge.helpers import fake_llm, make_run, make_truth


def judge_json(**scores):
    """칸별 (점수, 이유)로 채점관 응답 JSON을 만든다. 지정 안 한 칸은 1점."""
    base = {k: (1, "충족") for k in ("facts", "conditions", "evidence", "decision")}
    base.update(scores)
    return json.dumps({k: {"score": s, "reason": r} for k, (s, r) in base.items()}, ensure_ascii=False)


def test_1행_누락은_0이고_해당없음으로_빠지지_않는다():
    rec = score_one(make_run(), make_truth(), fake_llm(judge_json(facts=(0, "필수 사실 누락"))), use_ragas=False)
    assert rec.judge["facts"].score == 0
    assert not any(x.startswith("facts") for x in rec.not_applicable + rec.unscorable)
    assert mean_ignoring_none([1, 0]) == 0.5  # 0은 평균에 들어간다


def test_1행_null이면서_이유가_해당없음이_아니면_받지_않는다():
    # 누락을 null로 숨기려는 응답은 형식 오류로 거부된다 → 재시도 대상
    with pytest.raises(JudgeParseError):
        parse_judge_output(judge_json(facts=(None, "필수 사실을 빠뜨림")))


def test_2행_되묻기만_하면_Faithfulness는_해당없음_판단은_채점():
    pytest.importorskip("ragas")
    from tests.judge.test_ragas_eval import ragas_fake

    run = make_run(status="needs_clarification", answer="장비 종류를 알려 주세요.")
    reply = judge_json(facts=(None, "해당 없음: 사실 주장 없음"), evidence=(None, "해당 없음: 주장 없음"))

    def llm(messages):
        if "[평가 대상]" in messages[-1]["content"]:
            return fake_llm(reply)(messages)
        return ragas_fake(["장비 종류를 알려 주세요."])(messages)

    rec = score_one(run, make_truth(), llm, use_ragas=True)
    assert rec.faithfulness is None
    assert any(x.startswith("faithfulness: 사실 주장 없음") for x in rec.not_applicable)
    assert rec.judge["decision"].score in (0, 1)


def test_3행_대상없는_칸은_해당없음_판단칸은_null_불가():
    rec = score_one(make_run(), make_truth(), fake_llm(judge_json(evidence=(None, "해당 없음: 인용할 주장 없음"))), use_ragas=False)
    assert rec.judge["evidence"].score is None
    assert "evidence: 해당 없음: 인용할 주장 없음" in rec.not_applicable
    with pytest.raises(JudgeParseError):
        parse_judge_output(judge_json(decision=(None, "해당 없음: 판단 불필요")))


def test_4행_서비스오류는_판단0_나머지_평가불가_AI호출없음():
    llm = fake_llm(judge_json())
    rec = score_one(make_run(status="error", error="model_timeout"), make_truth(), llm)
    assert rec.judge["decision"].score == 0
    assert all(rec.judge[k].score is None for k in ("facts", "conditions", "evidence"))
    assert rec.faithfulness is None and len(llm.calls) == 0


def test_5행_채점호출이_실패하면_평가불가와_사유_0으로_안바꿈():
    def broken(messages):
        raise TimeoutError

    rec = score_one(make_run(), make_truth(), broken, use_ragas=False)
    assert rec.judge is None  # 점수를 지어내지 않음
    reasons = [x for x in rec.unscorable if not x.startswith("faithfulness")]
    assert len(reasons) == 4 and all("채점 호출 실패" in x for x in reasons)
