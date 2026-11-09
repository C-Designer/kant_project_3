"""judge가 정답을 metrics 로더로 읽어도 채점에 쓰는 칸이 그대로 나오는지 고정한다 (로더가 바뀌면 여기서 알린다)."""

import json

from src.judge.score import load_ground_truths


def test_정답_로더가_채점에_쓰는_칸을_채운다(tmp_path):
    row = {
        "id": "Q1", "question": "질문", "reference_answer": "참고", "expected_action": "answer",
        "evidence_groups": [[{"book_id": "B2", "page": 1}, {"book_id": "B1", "page": 2}]],
        "required_facts": ["사실A"], "forbidden_claims": ["금지B"], "grading_notes": "설명",
    }
    (tmp_path / "development_questions.json").write_text(json.dumps([{"id": "Q1", "question": "질문"}]), encoding="utf-8")
    (tmp_path / "development.json").write_text(json.dumps([row], ensure_ascii=False), encoding="utf-8")
    t = load_ground_truths(tmp_path)["Q1"]
    assert (t.expected_action, t.reference_answer) == ("answer", "참고")
    assert set(t.evidence_book_ids) == {"B1", "B2"}
    assert (t.rubric["required_facts"], t.rubric["forbidden_claims"], t.rubric["grading_notes"]) == (["사실A"], ["금지B"], "설명")
    assert "reference_answer" not in t.rubric  # 정답 본문은 rubric에 중복으로 넣지 않는다
