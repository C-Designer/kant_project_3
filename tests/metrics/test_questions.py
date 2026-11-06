import json

import pytest

from src.contracts import GroundTruth
from src.metrics.loader import Question
from src.metrics.questions import select_questions, write_selection


def make(n_answer, n_clarify, n_abstain):
    questions, truths = [], {}
    i = 0
    for action, n in (("answer", n_answer), ("clarify", n_clarify), ("abstain", n_abstain)):
        for _ in range(n):
            i += 1
            qid = f"Q{i:02d}"
            src = ["development", "additional", "expansion_validation"][i % 3]
            questions.append(Question(id=qid, question=f"q{i}", source=src))
            truths[qid] = GroundTruth(
                question_id=qid, evidence_book_ids=["A"], expected_action=action, reference_answer="r", rubric={}
            )
    return questions, truths


QUOTA = {"answer": 9, "clarify": 3, "abstain": 3}


def test_selects_requested_count_per_action():
    qs, truths = make(57, 7, 8)
    sel = select_questions(qs, truths, QUOTA, seed=0)
    assert len(sel) == 15
    counts = {a: sum(1 for s in sel if truths[s.id].expected_action == a) for a in QUOTA}
    assert counts == QUOTA


def test_selection_is_deterministic_for_same_seed_and_differs_for_other_seed():
    qs, truths = make(57, 7, 8)
    a = [s.id for s in select_questions(qs, truths, QUOTA, seed=1)]
    b = [s.id for s in select_questions(qs, truths, QUOTA, seed=1)]
    c = [s.id for s in select_questions(qs, truths, QUOTA, seed=2)]
    assert a == b and a != c


def test_every_selection_has_a_reason():
    qs, truths = make(20, 5, 5)
    for s in select_questions(qs, truths, QUOTA, seed=0):
        assert s.reason


def test_quota_larger_than_pool_raises():
    qs, truths = make(20, 2, 5)
    with pytest.raises(ValueError, match="clarify"):
        select_questions(qs, truths, QUOTA, seed=0)


def test_selection_does_not_leak_ground_truth_fields():
    qs, truths = make(20, 5, 5)
    sel = select_questions(qs, truths, QUOTA, seed=0)
    dumped = sel[0].model_dump()
    assert set(dumped) == {"id", "question", "source", "expected_action", "reason"}  # 정답 근거·기준은 없음


def test_write_selection_outputs_ids_reasons_and_seed(tmp_path):
    qs, truths = make(20, 5, 5)
    sel = select_questions(qs, truths, QUOTA, seed=7)
    path = write_selection(sel, QUOTA, seed=7, out_path=tmp_path / "questions.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["seed"] == 7 and data["quota"] == QUOTA
    assert [q["id"] for q in data["questions"]] == [s.id for s in sel]
    assert all(q["reason"] for q in data["questions"])


def test_load_selection_returns_only_runnable_questions(tmp_path):
    from src.metrics.questions import load_selection

    qs, truths = make(20, 5, 5)
    sel = select_questions(qs, truths, QUOTA, seed=3)
    path = write_selection(sel, QUOTA, seed=3, out_path=tmp_path / "questions.json")
    loaded = load_selection(path)
    assert [q.id for q in loaded] == [s.id for s in sel]
    assert all(type(q) is Question for q in loaded)  # expected_action·reason이 실행 입력으로 새지 않는다


def test_write_selection_refuses_to_overwrite(tmp_path):
    qs, truths = make(20, 5, 5)
    sel = select_questions(qs, truths, QUOTA, seed=0)
    write_selection(sel, QUOTA, seed=0, out_path=tmp_path / "questions.json")
    with pytest.raises(FileExistsError):
        write_selection(sel, QUOTA, seed=0, out_path=tmp_path / "questions.json")


def test_selection_file_states_expected_action_distribution_and_pool(tmp_path):
    qs, truths = make(20, 5, 5)
    sel = select_questions(qs, truths, QUOTA, seed=0)
    path = write_selection(sel, QUOTA, seed=0, out_path=tmp_path / "questions.json", pool_size={"answer": 20, "clarify": 5, "abstain": 5})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["distribution"] == {"answer": 9, "clarify": 3, "abstain": 3}  # 실제로 고른 분포
    assert data["pool"] == {"answer": 20, "clarify": 5, "abstain": 5}  # 고를 수 있던 전체 분포
