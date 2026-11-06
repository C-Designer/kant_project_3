"""원문 대조 시트: 어떤 사례를 고르는지, 시트에 무엇이 들어가는지 확인한다 (AI 호출 없음)."""

from pathlib import Path

import pytest

from src.contracts import EvalRecord, JudgeItem
from src.judge.review_sheet import build_pairs, build_sheet, pdf_page_text, select_candidates
from tests.judge.helpers import make_run, make_truth

DOCS = Path("data/shipping/documents")


def ev(qid="Q1", mode="naive", faith=1.0, facts=1, cond=1, evid=1, dec=1, na=(), us=()):
    scores = {"facts": facts, "conditions": cond, "evidence": evid, "decision": dec}
    return EvalRecord(question_id=qid, retrieval_mode=mode, faithfulness=faith,
                      judge={k: JudgeItem(score=v, reason=f"{k} 이유") for k, v in scores.items()},
                      eval_tokens=None, not_applicable=list(na), unscorable=list(us))


def run(qid="Q1", mode="naive", status="answered"):
    return make_run(status=status).model_copy(update={"question_id": qid, "retrieval_mode": mode})


def truths_for(*qids, action="answer"):
    return {q: make_truth().model_copy(update={"question_id": q, "expected_action": action}) for q in qids}


def pairs_of(*items):
    return build_pairs([r for r, _ in items], [e for _, e in items])


def labels(cands):
    return [c.label for c in cands]


def test_기대동작과_같은데_판단이_0점이면_과하게_깎였나로_고른다():
    pairs = pairs_of((run(), ev(dec=0)))
    assert any("과하게 깎였나" in l for l in labels(select_candidates(pairs, truths_for("Q1"))))


def test_기대동작과_다른데_판단이_1점이면_채점이_놓쳤나로_고른다():
    pairs = pairs_of((run(status="abstained"), ev(dec=1)))  # 기대는 answer인데 서비스는 보류
    assert any("놓쳤나" in l for l in labels(select_candidates(pairs, truths_for("Q1"))))


def test_서비스_오류_답안은_동작_불일치_후보에서_뺀다():
    pairs = pairs_of((run(status="error"), ev(dec=0)))
    assert not any("판단" in l for l in labels(select_candidates(pairs, truths_for("Q1"))))


def test_Faithfulness는_낮은데_4칸이_모두_1점이면_고른다():
    pairs = pairs_of((run(), ev(faith=0.4)))
    assert any("두 채점이 어긋남" in l for l in labels(select_candidates(pairs, truths_for("Q1"))))


def test_Faithfulness는_높은데_조건이_0점이면_고른다():
    pairs = pairs_of((run(), ev(faith=0.9, cond=0)))
    assert any("문맥에는 충실하나 틀림" in l for l in labels(select_candidates(pairs, truths_for("Q1"))))


def test_같은_질문에서_방식끼리_갈리면_방식을_묶어_한_사례로_고른다():
    pairs = pairs_of((run(mode="naive"), ev(mode="naive", cond=1)), (run(mode="hybrid"), ev(mode="hybrid", cond=0)))
    cands = select_candidates(pairs, truths_for("Q1"))
    assert len(cands) == 1 and "방식끼리" in cands[0].label and cands[0].modes == ["naive", "hybrid"]


def test_방식_하나만_먼저_골라졌어도_방식_비교_사례로_합쳐지고_이유가_남는다():
    # hybrid는 '높은 Faithfulness + 조건 0'으로도 걸리지만, 비교를 위해 naive와 함께 한 사례로 묶인다
    pairs = pairs_of((run(mode="naive"), ev(mode="naive", cond=1)), (run(mode="hybrid"), ev(mode="hybrid", faith=0.9, cond=0)))
    cands = select_candidates(pairs, truths_for("Q1"))
    assert len(cands) == 1 and cands[0].modes == ["naive", "hybrid"]
    assert "문맥에는 충실하나 틀림" in cands[0].label


def test_같은_답안은_여러_기준에_걸려도_한_번만_나온다():
    pairs = pairs_of((run(), ev(faith=0.4, dec=0)))  # 기준 1과 2에 모두 해당
    cands = select_candidates(pairs, truths_for("Q1"))
    assert len(cands) == 1


def test_해당없음_평가불가가_있으면_빈칸_규칙_확인용으로_고른다():
    pairs = pairs_of((run(), ev(na=["faithfulness: 사실 주장 없음"])))
    assert any("빈칸 규칙" in l for l in labels(select_candidates(pairs, truths_for("Q1"))))


def test_최대_개수를_넘기지_않는다():
    items = [(run(qid=f"Q{i}"), ev(qid=f"Q{i}", dec=0)) for i in range(10)]
    cands = select_candidates(pairs_of(*items), truths_for(*[f"Q{i}" for i in range(10)]), max_n=3)
    assert len(cands) == 3


def test_고를_사례가_없으면_빈_목록():
    assert select_candidates(pairs_of((run(), ev())), truths_for("Q1")) == []


def test_시트에는_질문_채점_이유_인용_원문_사람판정칸이_들어간다(tmp_path):
    pairs = pairs_of((run(), ev(dec=0)))
    sheet = build_sheet(pairs, truths_for("Q1"), tmp_path)  # PDF가 없는 폴더
    for needle in ("## 사례 1", "11월 6일 출항 SI 마감은?", "SB11.pdf", "(PDF 없음", "| 판단 (decision) | 0 |", "자동 채점이 맞나", "원래 점수 → 수정 점수"):
        assert needle in sheet, needle


def test_고를_사례가_없으면_안내문이_나온다(tmp_path):
    assert "고를 만한 사례가 없다" in build_sheet(pairs_of((run(), ev())), truths_for("Q1"), tmp_path)


@pytest.mark.skipif(not (DOCS / "SB11.pdf").exists(), reason="data/shipping/documents 없음")
def test_실제_PDF의_쪽_원문을_읽는다():
    text = pdf_page_text("SB11", 1, DOCS)
    assert "SI" in text and "12" in text
    assert "쪽 범위 밖" in pdf_page_text("SB11", 999, DOCS)
