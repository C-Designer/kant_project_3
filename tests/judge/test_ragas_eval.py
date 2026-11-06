"""RAGAS 결과를 None/해당 없음/평가 불가로 바르게 옮기는지. 실제 AI 대신 가짜 AI를 쓴다."""

import json

import pytest

pytest.importorskip("ragas")

from src.judge.ragas_eval import faithfulness  # noqa: E402
from tests.judge.helpers import fake_llm, make_run  # noqa: E402


def ragas_fake(statements, verdict=1):
    """RAGAS의 두 단계(주장 뽑기 → 주장별 확인)에 맞춰 답하는 가짜 AI."""
    def call(messages):
        prompt = messages[0]["content"]
        if "verdict" in prompt:  # 2단계: 주장마다 문맥에 있나 판정
            out = {"statements": [{"statement": s, "reason": "문맥에 있음", "verdict": verdict} for s in statements]}
        else:  # 1단계: 답변에서 주장 뽑기
            out = {"statements": statements}
        return fake_llm(json.dumps(out, ensure_ascii=False))(messages)
    return call


def test_주장이_모두_문맥에_있으면_1점():
    score, tokens, na, us = faithfulness(make_run(), ragas_fake(["SI 마감은 11월 4일 낮 12시다."]))
    assert score == 1.0 and na is None and us is None
    assert tokens.input and tokens.input > 0  # 사용량이 기록계(가짜)를 거쳐 잡힌다


def test_주장이_문맥에_없으면_0점():
    score, *_ = faithfulness(make_run(), ragas_fake(["SI 마감은 오후 3시다."], verdict=0))
    assert score == 0.0


def test_주장을_하나도_못뽑으면_해당없음_None():
    score, _, na, us = faithfulness(make_run(answer="어느 예약인지 알려 주세요."), ragas_fake([]))
    assert score is None and na and us is None


def test_AI_호출이_실패하면_평가불가_None():
    def broken(messages):
        raise TimeoutError
    score, _, na, us = faithfulness(make_run(), broken)
    assert score is None and na is None and us.startswith("RAGAS 계산 실패")


# --- 보류·되묻기 문장 처리 규칙 ---------------------------------------------

from src.judge.ragas_eval import is_meta_statement  # noqa: E402


@pytest.mark.parametrize("s", [
    "제공된 자료만으로는 선하증권의 발행 완료 여부를 확인할 수 없습니다.",  # 11/5 실제 시험에서 0점 원인
    "따라서 답변을 보류합니다.",
    "이 자료에는 무료기간·보관료·요율이 없어 계산할 수 없습니다.",
    "장비 종류와 신규 접수일을 알려 주세요.",
    "현재 안내만으로는 실제 출항 완료를 판단할 수 없습니다.",
    # 아래 둘은 11/5 실제 시험에서 RAGAS가 바꿔 쓴 문장 (처음 규칙이 놓친 것)
    "제공된 안내자료에는 무료기간, 보관료, 요율 또는 관련 계약 조건이 없습니다.",
    "마감 시간을 확인하려면 업무 종류와 대상 예약을 알려 주어야 합니다.",
    "제공된 안내 자료에는 무료기간, 보관료, 요율 또는 관련 계약 조건이 포함되어 있지 않습니다.",
])
def test_보류_자료부족_되묻기_문장은_뺀다(s):
    assert is_meta_statement(s)


@pytest.mark.parametrize("s", [
    "이 안내는 부산–LA 일반 건화물 20GP와 40GP에 적용됩니다.",  # 자료를 언급해도 부족·없음이 아니면 유지
    "SI는 docs@gaonroute.example로 제출합니다.",
    "11월 6일 예정 출항의 SI 마감은 11월 4일 낮 12시입니다.",
    "예약 확정 확인서만으로 반입이 허가되지는 않습니다.",
    "작성자에게 정정 자료를 요청해야 합니다.",
    "이 안내는 냉동 컨테이너에는 적용되지 않습니다.",  # '않다'여도 문서 내용이면 유지
])
def test_문서_내용_문장은_남긴다(s):
    assert not is_meta_statement(s)


def test_보류문장만_있으면_해당없음_그리고_확인단계를_부르지_않는다():
    calls = []
    def call(messages):
        calls.append(messages)
        return ragas_fake(["제공된 자료만으로는 확인할 수 없습니다.", "답변을 보류합니다."])(messages)
    score, _, na, us = faithfulness(make_run(status="abstained", answer="자료로 확인할 수 없어 보류합니다."), call)
    assert score is None and us is None and "보류" in na
    assert len(calls) == 1  # 주장 뽑기 1번만, 주장별 확인은 안 함


def test_보류문장과_문서주장이_섞이면_문서주장만_채점():
    seen = []
    def call(messages):
        prompt = messages[0]["content"]
        if "verdict" in prompt:
            seen.append(prompt)
            out = {"statements": [{"statement": "SI 마감은 11월 4일 낮 12시다.", "reason": "있음", "verdict": 1}]}
        else:
            out = {"statements": ["답변을 보류합니다.", "SI 마감은 11월 4일 낮 12시다."]}
        return fake_llm(json.dumps(out, ensure_ascii=False))(messages)
    score, _, na, us = faithfulness(make_run(), call)
    assert score == 1.0
    assert "보류합니다" not in seen[0].split("statements")[-1]


def test_RAGAS에는_최종문맥_글만_들어가고_정답은_안들어간다(monkeypatch):
    """Issue #33: 참고 정답이 retrieved_contexts에 들어가지 않음을 코드로 확인."""
    import ragas

    captured = {}
    real = ragas.SingleTurnSample

    def spy(**kwargs):
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(ragas, "SingleTurnSample", spy)
    run = make_run()
    faithfulness(run, ragas_fake(["SI 마감은 11월 4일 낮 12시다."]))
    assert captured["retrieved_contexts"] == [c.text for c in run.final_context]
    assert captured["user_input"] == run.question and captured["response"] == run.answer
    # faithfulness() 함수는 정답지(GroundTruth)를 인자로 받지도 않는다
    import inspect
    from src.judge import ragas_eval
    assert list(inspect.signature(ragas_eval.faithfulness).parameters) == ["run", "llm"]
