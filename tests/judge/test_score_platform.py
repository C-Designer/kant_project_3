"""score.py의 llm_call·record_score가 팀 platform을 그대로 부르는지 확인한다 (실제 AI는 부르지 않음)."""

from src.judge import score as score_mod
from src.judge.score import score_one
from src.platform import llm as platform_llm
from src.platform import tracing
from tests.judge.helpers import make_run, make_truth


def test_기본은_팀_platform의_llm_call을_eval로_부른다(monkeypatch):
    seen = {}

    def fake_call(messages, *, kind="service"):
        seen["kind"], seen["messages"] = kind, messages
        return platform_llm.LLMResult("ok", 11, 22, 33)

    monkeypatch.setattr(platform_llm, "call", fake_call)
    res = score_mod.llm_call([{"role": "user", "content": "hi"}])
    assert (res.text, res.input_tokens, res.output_tokens, res.latency_ms) == ("ok", 11, 22, 33)
    assert seen["kind"] == "eval"  # 서비스 사용량과 섞이지 않는 평가 호출


def test_점수_기록은_팀_tracing으로_그대로_넘어간다(monkeypatch):
    seen = []
    monkeypatch.setattr(tracing, "record_score", lambda *a: seen.append(a))
    score_mod.record_score("req-1", "judge_facts", 1, "이유")
    assert seen == [("req-1", "judge_facts", 1, "이유")]


def test_None_점수는_Langfuse로_보내지_않고_0은_보낸다(monkeypatch):
    seen = []
    monkeypatch.setattr(tracing, "record_score", lambda *a: seen.append(a))
    score_mod.record_score("req-1", "judge_facts", None, "해당 없음: 사실 주장 없음")
    assert seen == []  # 빈 값은 보내지 않는다 (0이나 1로 바꾸지도 않는다)
    score_mod.record_score("req-1", "judge_facts", 0, "수치가 틀림")
    assert seen == [("req-1", "judge_facts", 0, "수치가 틀림")]  # 0은 '틀렸다'는 진짜 점수라 보낸다


def test_서비스_오류_답안은_판단_0만_점수로_붙는다(monkeypatch):
    from src.judge.score import _record_scores
    from src.judge.rules import precheck

    seen = []
    monkeypatch.setattr(tracing, "record_score", lambda *a: seen.append(a))
    run = make_run(status="error", error="timeout")
    _record_scores(run, precheck(run))
    assert [(name, value) for _, name, value, _ in seen] == [("judge_decision", 0)]


def test_platform이_LLMError를_내면_평가불가로_남고_0이나_1로_바뀌지_않는다(monkeypatch):
    def failing(messages, *, kind="service"):
        raise platform_llm.LLMError("실패", "model_error")

    monkeypatch.setattr(platform_llm, "call", failing)
    rec = score_one(make_run(), make_truth(), score_mod.llm_call, use_ragas=False)
    assert rec.judge is None
    reasons = [u for u in rec.unscorable if not u.startswith("faithfulness")]
    assert len(reasons) == 4 and all("채점 호출 실패" in u for u in reasons)
