import json
from datetime import datetime

import pytest

from src.contracts import RunRecord
from src.metrics.loader import Question
from src.metrics.run import DEFAULT_MODES, MODES, load_runs, make_run_id, mock_run_query, run_all

QUESTIONS = [Question(id=f"S-{i}", question=f"질문 {i}", source="development") for i in range(1, 4)]


def fake_run_query(calls=None, blank_id=True, fail_on=None):
    def run_query(question, mode, *, request_id=None):
        if calls is not None:
            calls.append((question, mode, request_id))
        if fail_on and (question, mode) == fail_on:
            raise RuntimeError("boom")
        return RunRecord(
            question_id="" if blank_id else "x",
            request_id=f"req-{abs(hash((question, mode))) % 10_000}",
            retrieval_mode=mode,
            question="",  # platform이 채우지 않은 경우도 방어
            status="answered",
            answer="",
            reason="",
            citations=[],
            retrieved_book_ids=["SB01"],
            final_context=[],
            latency_ms=120,
            input_tokens=100,
            output_tokens=10,
            error=None,
        )

    return run_query


def test_make_run_id_is_timestamp_with_optional_label():
    now = datetime(2026, 11, 10, 9, 5, 12)
    assert make_run_id(now) == "20261110-090512"
    assert make_run_id(now, label="final") == "20261110-090512-final"


def test_runs_every_question_in_every_mode_and_writes_one_line_each(tmp_path):
    run_dir = run_all(QUESTIONS, DEFAULT_MODES, fake_run_query(), tmp_path, run_id="r1")
    for mode in DEFAULT_MODES:
        lines = (run_dir / f"{mode}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        assert all(RunRecord.model_validate_json(line) for line in lines)


def test_question_id_text_and_mode_come_from_the_runner_not_run_query(tmp_path):
    run_dir = run_all(QUESTIONS, DEFAULT_MODES, fake_run_query(blank_id=True), tmp_path, run_id="r1")
    recs = load_runs(run_dir)
    assert {r.question_id for r in recs} == {"S-1", "S-2", "S-3"}
    assert {r.question for r in recs} == {"질문 1", "질문 2", "질문 3"}
    assert {r.retrieval_mode for r in recs} == set(DEFAULT_MODES)


def test_run_query_receives_only_question_text_and_mode(tmp_path):
    calls = []
    run_all(QUESTIONS, DEFAULT_MODES, fake_run_query(calls), tmp_path, run_id="r1")
    assert len(calls) == 9
    assert {c[0] for c in calls} == {"질문 1", "질문 2", "질문 3"}  # 정답·id·source는 넘기지 않는다
    assert {c[1] for c in calls} == set(DEFAULT_MODES)


def test_failed_call_is_recorded_as_error_and_run_continues(tmp_path):
    run_dir = run_all(
        QUESTIONS, DEFAULT_MODES, fake_run_query(fail_on=("질문 2", "hybrid")), tmp_path, run_id="r1"
    )
    recs = {(r.question_id, r.retrieval_mode): r for r in load_runs(run_dir)}
    assert len(recs) == 9  # 하나 실패해도 전체가 기록된다
    bad = recs[("S-2", "hybrid")]
    assert bad.status == "error" and "boom" in (bad.error or "")
    assert bad.latency_ms is not None  # 실패 요청 시간도 기록
    assert bad.input_tokens is None and bad.output_tokens is None  # 모르는 값은 0이 아니라 None
    assert recs[("S-3", "hybrid")].status == "answered"


def test_same_run_id_is_never_overwritten(tmp_path):
    run_dir = run_all(QUESTIONS, DEFAULT_MODES, fake_run_query(), tmp_path, run_id="r1")
    before = (run_dir / "naive.jsonl").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_all(QUESTIONS[:1], DEFAULT_MODES, fake_run_query(), tmp_path, run_id="r1")
    assert (run_dir / "naive.jsonl").read_text(encoding="utf-8") == before


def test_unknown_mode_is_rejected_before_anything_is_written(tmp_path):
    with pytest.raises(ValueError, match="bm25"):
        run_all(QUESTIONS, ("naive", "bm25"), fake_run_query(), tmp_path, run_id="r1")
    assert not (tmp_path / "r1").exists()


def test_run_meta_records_modes_and_question_ids(tmp_path):
    run_dir = run_all(QUESTIONS, DEFAULT_MODES, fake_run_query(), tmp_path, run_id="r1", label="smoke")
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["run_id"] == "r1" and meta["label"] == "smoke"
    assert meta["modes"] == list(DEFAULT_MODES) and meta["question_ids"] == ["S-1", "S-2", "S-3"]
    assert meta["started_at"] and meta["finished_at"]


def test_mock_run_query_returns_valid_records_for_all_modes():
    for mode in DEFAULT_MODES:
        r = mock_run_query("질문", mode)
        assert r.retrieval_mode == mode and r.status in {"answered", "needs_clarification", "abstained", "error"}


def test_run_meta_keeps_extra_settings(tmp_path):
    run_dir = run_all(QUESTIONS, DEFAULT_MODES, fake_run_query(), tmp_path, run_id="r1", extra={"selection_seed": 20261105})
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["selection_seed"] == 20261105


# --- run_meta에 실행 시점의 커밋·변경 여부를 남긴다 (이슈 #65: 동결 커밋 해시 기록) ----------------

def _git(cwd, *args):
    import subprocess

    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_git_state_records_commit_and_flags_uncommitted_changes(tmp_path):
    from src.metrics.run import git_state

    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "c")

    clean = git_state(tmp_path)
    assert len(clean["git_commit"]) == 40 and clean["git_dirty"] is False

    (tmp_path / "new.txt").write_text("x", encoding="utf-8")  # 추적되지 않는 파일(results/ 같은 것)은 변경으로 세지 않는다
    assert git_state(tmp_path)["git_dirty"] is False

    (tmp_path / "a.txt").write_text("2", encoding="utf-8")  # 추적 파일 수정은 변경이다
    assert git_state(tmp_path)["git_dirty"] is True


def test_git_state_is_none_when_git_is_unavailable(tmp_path):
    from src.metrics.run import git_state

    assert git_state(tmp_path) == {"git_commit": None, "git_dirty": None}  # git 저장소가 아님: 0이나 False로 지어내지 않는다


def test_every_contract_mode_can_be_run_and_loaded(tmp_path):
    # 새 방식(예: hybrid_rerank_subq)이 contracts에 들어오면 러너를 따로 고치지 않아도 실행·로딩된다
    run_dir = run_all(QUESTIONS, MODES, fake_run_query(), tmp_path, run_id="r_all")
    assert {r.retrieval_mode for r in load_runs(run_dir)} == set(MODES)
    assert set(DEFAULT_MODES) <= set(MODES)
