"""questions -> run(--mock) -> report 를 명령줄 진입점으로 끝까지 이어 본다."""

import json

import pandas as pd
import pytest

from src.metrics import questions as questions_cli
from src.metrics import report as report_cli
from src.metrics import run as run_cli


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


def test_full_pipeline_with_mock(tmp_path, eval_dir):
    results = tmp_path / "results"
    qfile = results / "questions.json"

    questions_cli.main(
        ["--eval-dir", str(eval_dir), "--answer", "2", "--clarify", "1", "--abstain", "1", "--seed", "1", "--out", str(qfile)]
    )
    assert json.loads(qfile.read_text(encoding="utf-8"))["count"] == 4

    run_cli.main(["--questions", str(qfile), "--mock", "--results-dir", str(results), "--label", "t"])
    (run_dir,) = (results / "runs").iterdir()
    assert {p.name for p in run_dir.glob("*.jsonl")} == {"naive.jsonl", "hybrid.jsonl", "hybrid_rerank.jsonl"}

    report_cli.main(["--run", run_dir.name, "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(results)])
    detail = pd.read_csv(run_dir / "comparison_detail.csv")
    assert len(detail) == 12  # 4문항 x 3방식
    assert (run_dir / "comparison_summary.csv").exists() and (run_dir / "comparison.md").exists()
    # judge 결과(eval.jsonl)가 아직 없어도 비교표는 만들어지고 평가 열은 빈 칸이다
    assert detail["faithfulness"].isna().all()


def test_report_reads_eval_jsonl_when_present(tmp_path, eval_dir):
    results = tmp_path / "results"
    qfile = results / "questions.json"
    questions_cli.main(
        ["--eval-dir", str(eval_dir), "--answer", "2", "--clarify", "1", "--abstain", "1", "--seed", "1", "--out", str(qfile)]
    )
    run_cli.main(["--questions", str(qfile), "--mock", "--results-dir", str(results)])
    (run_dir,) = (results / "runs").iterdir()
    first = json.loads((run_dir / "naive.jsonl").read_text(encoding="utf-8").splitlines()[0])
    ev = {"question_id": first["question_id"], "retrieval_mode": "naive", "faithfulness": 0.75,
          "judge": None, "eval_tokens": None, "not_applicable": [], "unscorable": []}
    (run_dir / "eval.jsonl").write_text(json.dumps(ev, ensure_ascii=False) + "\n", encoding="utf-8")

    report_cli.main(["--run", run_dir.name, "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(results)])
    detail = pd.read_csv(run_dir / "comparison_detail.csv")
    assert detail["faithfulness"].notna().sum() == 1


def test_report_fails_clearly_for_missing_run(tmp_path, eval_dir):
    with pytest.raises(SystemExit, match="없"):
        report_cli.main(["--run", "nope", "--eval-dir", str(eval_dir), "--k", "3", "--results-dir", str(tmp_path)])
