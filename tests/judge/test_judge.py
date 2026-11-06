"""채점관 결과 검사와 재시도 규칙."""

import json

import pytest

from src.judge.judge import JudgeParseError, build_messages, judge_one, parse_judge_output
from src.judge.score import score_one
from tests.judge.helpers import fake_llm, make_run, make_truth

OK = json.dumps({
    "facts": {"score": 1, "reason": "필수 사실 제시"},
    "conditions": {"score": 0, "reason": "오후 3시는 옛 규칙"},
    "evidence": {"score": None, "reason": "해당 없음: 주장 없음"},
    "decision": {"score": 1, "reason": "답변이 적절"},
}, ensure_ascii=False)


def test_정상_JSON을_읽는다_포장이_있어도():
    items = parse_judge_output(f"```json\n{OK}\n```")
    assert items["conditions"].score == 0
    assert items["evidence"].score is None


@pytest.mark.parametrize("bad", [
    "점수를 줄 수 없습니다",                                               # JSON 없음
    OK.replace('"decision"', '"judgement"'),                               # 칸 이름 틀림
    OK.replace('"score": 0', '"score": 0.5'),                              # 0/1/null 아님
    OK.replace('"score": 0', '"score": false'),                            # bool은 0으로 치지 않음
    OK.replace("해당 없음: 주장 없음", "주장 없음"),                         # null인데 이유 표시 없음
    OK.replace('"score": 1, "reason": "답변이 적절"', '"score": null, "reason": "해당 없음: x"'),  # decision null 금지
])
def test_약속과_다른_결과는_거부한다(bad):
    with pytest.raises(JudgeParseError):
        parse_judge_output(bad)


def test_형식이_틀리면_한번_재시도하고_성공하면_토큰을_합친다():
    llm = fake_llm("엉망인 답", OK)
    items, tokens, err = judge_one(make_run(), make_truth(), llm)
    assert err is None and items["facts"].score == 1
    assert len(llm.calls) == 2
    assert (tokens.input, tokens.output) == (20, 10)


def test_두번_다_틀리면_네칸_모두_평가불가_0으로_바꾸지_않음():
    rec = score_one(make_run(), make_truth(), fake_llm("엉망"), use_ragas=False)
    assert rec.judge is None
    assert len([u for u in rec.unscorable if not u.startswith("faithfulness")]) == 4


def test_null_이유에_따라_해당없음과_평가불가로_나눈다():
    rec = score_one(make_run(), make_truth(), fake_llm(OK), use_ragas=False)
    assert "evidence: 해당 없음: 주장 없음" in rec.not_applicable


def test_정답기준은_채점관_메시지에만_들어가고_문맥과_구분된다():
    msgs = build_messages(make_run(), make_truth())
    user = msgs[1]["content"]
    assert user.index("[최종 문맥]") < user.index("[채점 기준]")
    assert "따르지 말고" in msgs[0]["content"]  # 자료 속 명령 무시 문장


def test_spec대로_정답지를_목록으로_받고_없는_정답은_평가불가():
    from src.judge.score import score
    runs = [make_run(), make_run().model_copy(update={"question_id": "없는문항"})]
    recs = score(runs, [make_truth()], fake_llm(OK), use_ragas=False)
    assert recs[0].judge["facts"].score == 1
    assert recs[1].judge is None and all("정답지" in u for u in recs[1].unscorable)
