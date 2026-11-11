"""questions -> run -> report 를 명령줄 진입점으로 끝까지 이어 본다. (진짜 run_query 자리에는 연습 결과를 넣는다)"""

import csv
import json

import pytest

from src.metrics import questions as questions_cli
from src.metrics import report as report_cli
from src.metrics import run as run_cli


@pytest.fixture()
def stand_in_real_run(monkeypatch):
    """--mock 없이 돌리되 진짜 run_query 자리에 연습 결과를 넣는다. report는 mock 실행을 거부하므로 필요하다."""

    def fake(question, mode, *, request_id=None):
        r = run_cli.mock_run_query(question, mode)
        return r.model_copy(update={"request_id": "stand-in-" + r.request_id[5:]})

    monkeypatch.setattr(run_cli, "_real_run_query", lambda: fake)


@pytest.fixture()
def eval_dir(tmp_path):
    d = tmp_path / "evaluation"
    d.mkdir()
    qs, gts = [], []
    for i, action in enumerate(["answer"] * 4 + ["clarify", "abstain"], start=1):
        qid = f"S-DEV-{i:02d}"
        qs.append({"id": qid, "question": f"질문 {i}"})
        groups = [] if action != "answer" else [[{"book_id": f"SB{i:02d}", "page": 1, "quote": f"원문 {i}"}]]
        gts.append(
            {"id": qid, "question": f"질문 {i}", "reference_answer": "r", "expected_action": action,
             "evidence_groups": groups, "required_facts": [], "forbidden_claims": [], "grading_notes": ""}
        )
    (d / "development_questions.json").write_text(json.dumps(qs, ensure_ascii=False), encoding="utf-8")
    (d / "development.json").write_text(json.dumps(gts, ensure_ascii=False), encoding="utf-8")
    return d


def test_full_pipeline(tmp_path, eval_dir, stand_in_real_run):
    results = tmp_path / "results"
    qfile = results / "questions.json"

    questions_cli.main(
        ["--eval-dir", str(eval_dir), "--answer", "2", "--clarify", "1", "--abstain", "1", "--seed", "1", "--min-per-source", "0", "--min-docs", "0", "--out", str(qfile)]
    )
    assert json.loads(qfile.read_text(encoding="utf-8"))["count"] == 4

    run_cli.main(["--questions", str(qfile), "--results-dir", str(results), "--label", "t"])
    (run_dir,) = (results / "runs").iterdir()
    assert {p.name for p in run_dir.glob("*.jsonl")} == {"naive.jsonl", "hybrid.jsonl", "hybrid_rerank.jsonl"}

    report_cli.main(["--run", run_dir.name, "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(results)])
    detail = list(csv.DictReader((run_dir / "comparison_detail.csv").read_text(encoding="utf-8").splitlines()))
    assert len(detail) == 12  # 4문항 x 3방식
    assert (run_dir / "comparison_summary.csv").exists() and (run_dir / "comparison.md").exists()
    # judge 결과(eval.jsonl)가 아직 없어도 비교표는 만들어지고 평가 열은 빈 칸이다
    assert all(r["faithfulness"] == "" for r in detail)


def test_report_reads_eval_jsonl_when_present(tmp_path, eval_dir, stand_in_real_run):
    results = tmp_path / "results"
    qfile = results / "questions.json"
    questions_cli.main(
        ["--eval-dir", str(eval_dir), "--answer", "2", "--clarify", "1", "--abstain", "1", "--seed", "1", "--min-per-source", "0", "--min-docs", "0", "--out", str(qfile)]
    )
    run_cli.main(["--questions", str(qfile), "--results-dir", str(results)])
    (run_dir,) = (results / "runs").iterdir()
    first = json.loads((run_dir / "naive.jsonl").read_text(encoding="utf-8").splitlines()[0])
    ev = {"question_id": first["question_id"], "retrieval_mode": "naive", "faithfulness": 0.75,
          "judge": None, "eval_tokens": None, "not_applicable": [], "unscorable": []}
    (run_dir / "eval.jsonl").write_text(json.dumps(ev, ensure_ascii=False) + "\n", encoding="utf-8")

    report_cli.main(["--run", run_dir.name, "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(results)])
    detail = list(csv.DictReader((run_dir / "comparison_detail.csv").read_text(encoding="utf-8").splitlines()))
    assert sum(1 for r in detail if r["faithfulness"] != "") == 1


def test_report_fails_clearly_for_missing_run(tmp_path, eval_dir):
    with pytest.raises(SystemExit, match="없"):
        report_cli.main(["--run", "nope", "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(tmp_path)])


def test_run_meta_marks_mock_and_records_commit(tmp_path, eval_dir):
    results = tmp_path / "results"
    qfile = results / "questions.json"
    questions_cli.main(
        ["--eval-dir", str(eval_dir), "--answer", "2", "--clarify", "1", "--abstain", "1", "--seed", "1", "--min-per-source", "0", "--min-docs", "0", "--out", str(qfile)]
    )
    run_cli.main(["--questions", str(qfile), "--mock", "--results-dir", str(results)])
    (run_dir,) = (results / "runs").iterdir()
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["mock"] is True
    assert "git_commit" in meta and "git_dirty" in meta


def test_report_refuses_a_mock_run(tmp_path, eval_dir):
    results = tmp_path / "results"
    qfile = results / "questions.json"
    questions_cli.main(
        ["--eval-dir", str(eval_dir), "--answer", "2", "--clarify", "1", "--abstain", "1", "--seed", "1", "--min-per-source", "0", "--min-docs", "0", "--out", str(qfile)]
    )
    run_cli.main(["--questions", str(qfile), "--mock", "--results-dir", str(results)])
    (run_dir,) = (results / "runs").iterdir()
    with pytest.raises(SystemExit, match="mock"):
        report_cli.main(["--run", run_dir.name, "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(results)])
    assert not (run_dir / "comparison.md").exists()  # 표를 만들지 않는다


def test_report_refuses_old_mock_run_without_the_flag(tmp_path, eval_dir):
    results = tmp_path / "results"
    qfile = results / "questions.json"
    questions_cli.main(
        ["--eval-dir", str(eval_dir), "--answer", "2", "--clarify", "1", "--abstain", "1", "--seed", "1", "--min-per-source", "0", "--min-docs", "0", "--out", str(qfile)]
    )
    run_cli.main(["--questions", str(qfile), "--mock", "--results-dir", str(results)])
    (run_dir,) = (results / "runs").iterdir()
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.pop("mock")  # 표시가 생기기 전에 만든 mock 실행
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(SystemExit, match="mock"):
        report_cli.main(["--run", run_dir.name, "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(results)])
