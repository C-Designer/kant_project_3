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


# --- 근거 문서 수(단일/복수)를 풀 비율에 맞추고, 파일·문서 분포 조건을 구조만으로 거른다 -----------------

def make_mixed():
    """유형별 20/6/6문항. 일부는 근거 문서가 2개(복수), 나머지는 1개(단일). 평가 파일은 돌아가며 섞는다."""
    questions, truths = [], {}
    sources = ["development", "additional", "expansion_validation"]
    i = 0
    for action, n in (("answer", 20), ("clarify", 6), ("abstain", 6)):
        for j in range(n):
            i += 1
            qid = f"Q{i:02d}"
            multi = j % 5 != 0  # 유형 안에서 5개 중 4개가 복수 근거
            evidence = [f"D{i % 8}", f"D{(i + 1) % 8}"] if multi else [f"D{i % 8}"]
            questions.append(Question(id=qid, question=f"q{i}", source=sources[i % 3]))
            truths[qid] = GroundTruth(
                question_id=qid, evidence_book_ids=evidence, expected_action=action, reference_answer="r", rubric={}
            )
    return questions, truths


def n_multi(sel, truths, action):
    return sum(1 for s in sel if truths[s.id].expected_action == action and len(truths[s.id].evidence_book_ids) >= 2)


def test_multi_evidence_share_follows_the_pool():
    qs, truths = make_mixed()
    sel = select_questions(qs, truths, QUOTA, seed=0)
    # answer 풀: 20문항 중 16개가 복수 -> 9 x 16/20 = 7.2 -> 7개
    assert n_multi(sel, truths, "answer") == 7


def test_min_per_source_is_enforced():
    qs, truths = make_mixed()
    sel = select_questions(qs, truths, QUOTA, seed=0, min_per_source=4)
    counts = {s: sum(1 for x in sel if x.source == s) for s in {q.source for q in qs}}
    assert min(counts.values()) >= 4


def test_min_docs_is_enforced():
    qs, truths = make_mixed()
    sel = select_questions(qs, truths, QUOTA, seed=0, min_docs=7)
    docs = set().union(*(truths[s.id].evidence_book_ids for s in sel))
    assert len(docs) >= 7


def test_constraints_that_cannot_be_met_raise():
    qs, truths = make_mixed()
    with pytest.raises(ValueError, match="조건"):
        select_questions(qs, truths, QUOTA, seed=0, min_docs=99, max_attempts=50)


def test_constrained_selection_is_deterministic():
    qs, truths = make_mixed()
    a = [s.id for s in select_questions(qs, truths, QUOTA, seed=3, min_per_source=4, min_docs=7)]
    b = [s.id for s in select_questions(qs, truths, QUOTA, seed=3, min_per_source=4, min_docs=7)]
    assert a == b
