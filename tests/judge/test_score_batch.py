"""여러 답안을 한꺼번에 채점할 때의 약속: 순서·결과는 하나씩 할 때와 같고, 한 건의 실패가 전체를 멈추지 않는다."""

import re
import time

import pytest

from src.contracts import TokenUsage
from src.judge import judge as judge_mod
from src.judge import score as score_mod
from src.judge.rules import add_optional, sum_usage
from src.judge.score import _read_partial, reusable_prefix, score
from tests.judge.helpers import fake_llm, make_run, make_truth
from tests.judge.test_evaluation_table import judge_json


def _runs(n: int):
    return [make_run().model_copy(update={"question_id": f"Q{i}", "request_id": f"r{i}", "question": f"문항{i}"}) for i in range(n)]


def _truths(n: int):
    return {f"Q{i}": make_truth().model_copy(update={"question_id": f"Q{i}"}) for i in range(n)}


def _slow_in_reverse(reply: str, n: int):
    """앞 번호일수록 오래 걸리는 가짜 AI: 끝나는 순서가 뒤집혀도 결과 순서가 유지되는지 본다."""
    def call(messages):
        i = int(re.search(r"문항(\d+)", messages[-1]["content"]).group(1))
        time.sleep((n - i) * 0.005)
        return fake_llm(reply)(messages)
    return call


# --- 토큰 합산 규칙 (한 곳에 모음) ---------------------------------------------


def test_토큰_더하기는_한쪽이라도_모르면_None이다_0으로_메우지_않는다():
    assert add_optional(3, 4) == 7
    assert add_optional(None, 4) is None
    assert add_optional(3, None) is None
    assert add_optional(0, 0) == 0  # 진짜 0은 0이다


def test_사용량_합계는_하나도_없으면_None이고_모르는_값이_섞이면_그_칸만_None():
    assert sum_usage() is None
    assert sum_usage(None, None) is None
    assert sum_usage(TokenUsage(input=1, output=2), TokenUsage(input=3, output=4)) == TokenUsage(input=4, output=6)
    assert sum_usage(TokenUsage(input=1, output=2), TokenUsage(input=None, output=4)) == TokenUsage(input=None, output=6)


# --- 순서와 결과가 같다 -----------------------------------------------------------


def test_여럿이_동시에_채점해도_결과와_순서가_하나씩_할_때와_같다():
    runs, truths = _runs(12), _truths(12)
    reply = judge_json(facts=(0, "누락"))
    seq = score(runs, truths, fake_llm(reply), use_ragas=False, workers=1)
    par = score(runs, truths, _slow_in_reverse(reply, 12), use_ragas=False, workers=4)
    assert [r.model_dump() for r in seq] == [r.model_dump() for r in par]
    assert [r.question_id for r in par] == [f"Q{i}" for i in range(12)]


def test_점수_기록과_중간저장_호출도_runs_순서대로_이루어진다(monkeypatch):
    runs, truths = _runs(8), _truths(8)
    recorded, saved = [], []
    monkeypatch.setattr(score_mod, "record_score", lambda rid, name, value, comment=None: recorded.append((rid, name)))
    score(runs, truths, fake_llm(judge_json()), use_ragas=False, workers=4, on_record=lambda rec: saved.append(rec.question_id))
    assert saved == [f"Q{i}" for i in range(8)]
    assert [rid for rid, _ in recorded][::5] == [f"r{i}" for i in range(8)]  # 답안마다 기록 5건(Faithfulness + Judge 4항목)


# --- 한 건의 실패가 전체를 멈추지 않는다 -----------------------------------------------


@pytest.mark.parametrize("workers", [1, 3])
def test_한_건에서_예상_못한_오류가_나도_그_건만_평가불가가_된다(monkeypatch, workers):
    real = score_mod.judge_one

    def flaky(run, truth, llm):
        if run.question_id == "Q2":
            raise RuntimeError("예상 못 한 고장")
        return real(run, truth, llm)

    monkeypatch.setattr(score_mod, "judge_one", flaky)
    recs = score(_runs(5), _truths(5), fake_llm(judge_json()), use_ragas=False, workers=workers)
    assert len(recs) == 5
    bad = recs[2]
    assert bad.judge is None and bad.faithfulness is None  # 0이나 1로 바꾸지 않는다
    assert len(bad.unscorable) == 5 and all("예상 못 한 오류: RuntimeError" in u for u in bad.unscorable)
    assert all(r.judge is not None for i, r in enumerate(recs) if i != 2)  # 나머지는 정상 채점


def test_RAGAS_준비가_실패해도_Faithfulness만_평가불가고_채점관_4항목은_계속된다(monkeypatch):
    pytest.importorskip("ragas")
    from src.judge import ragas_eval

    monkeypatch.setattr(ragas_eval, "_make_metric", lambda recorded: (_ for _ in ()).throw(RuntimeError("준비 실패")))
    recs = score(_runs(1), _truths(1), fake_llm(judge_json()), use_ragas=True)
    rec = recs[0]
    assert rec.faithfulness is None and any(u.startswith("faithfulness: RAGAS 계산 실패") for u in rec.unscorable)
    assert rec.judge is not None and rec.judge["facts"].score == 1


# --- 이어하기 ------------------------------------------------------------------------


def test_이미_채점한_건은_AI를_다시_부르지_않고_그_결과를_그대로_쓴다():
    runs, truths = _runs(4), _truths(4)
    first = score(runs, truths, fake_llm(judge_json()), use_ragas=False)
    llm = fake_llm(judge_json(facts=(0, "다시 채점되면 이 값이 나온다")))
    saved = []
    recs = score(runs, truths, llm, use_ragas=False, workers=2, on_record=lambda r: saved.append(r.question_id), done=first[:2])
    assert len(llm.calls) == 2  # Q2, Q3만 새로 채점
    assert recs[0] == first[0] and recs[1] == first[1]  # 이미 있는 앞쪽 건은 그대로
    assert recs[2].judge["facts"].score == 0 and recs[3].judge["facts"].score == 0
    assert saved == ["Q2", "Q3"]  # 중간 저장은 새로 한 건만


def test_같은_질문과_방식이_여러_번_나와도_이어하기가_엉키지_않는다():
    runs = [make_run().model_copy(update={"answer": f"답{i}"}) for i in range(4)]  # 질문 ID·방식이 모두 같다
    truths = {"Q1": make_truth()}
    first = score(runs, truths, fake_llm(judge_json()), use_ragas=False)
    llm = fake_llm(judge_json())
    recs = score(runs, truths, llm, use_ragas=False, done=first[:3])
    assert len(llm.calls) == 1  # 앞의 3건은 그대로, 마지막 1건만 새로 채점


def test_저장된_결과가_runs와_어긋나는_지점부터는_다시_채점한다():
    runs, truths = _runs(4), _truths(4)
    first = score(runs, truths, fake_llm(judge_json()), use_ragas=False)
    tampered = [first[0], first[2], first[3]]  # 두 번째가 다른 질문의 결과
    assert reusable_prefix(runs, tampered) == [first[0]]
    llm = fake_llm(judge_json())
    score(runs, truths, llm, use_ragas=False, done=tampered)
    assert len(llm.calls) == 3


def test_중간저장_파일을_읽을_때_끊겨서_반쯤_쓰인_줄은_버린다(tmp_path):
    recs = score(_runs(2), _truths(2), fake_llm(judge_json()), use_ragas=False)
    f = tmp_path / "eval.jsonl.partial"
    f.write_text(recs[0].model_dump_json() + "\n" + recs[1].model_dump_json()[:40], encoding="utf-8")
    done = _read_partial(f, _runs(2))
    assert [r.question_id for r in done] == ["Q0"]
    assert _read_partial(tmp_path / "없는파일", _runs(2)) == []


# --- 채점 지시문은 한 번만 읽는다 ----------------------------------------------------------


def test_채점_지시문_파일은_여러번_만들어도_한_번만_읽는다():
    judge_mod._load_prompt.cache_clear()
    for _ in range(3):
        judge_mod.build_messages(make_run(), make_truth())
    assert judge_mod._load_prompt.cache_info().misses == 1
