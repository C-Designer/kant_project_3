import pandas as pd
import pytest

from src.contracts import EvalRecord, GroundTruth, JudgeItem, RunRecord, TokenUsage
from src.metrics.report import build_detail, build_summary, render_markdown, write_report

K = 2


def run(qid, mode, retrieved, status="answered", latency=100, inp=10, out=5, error=None):
    return RunRecord(
        question_id=qid,
        request_id=f"req-{qid}-{mode}",
        retrieval_mode=mode,
        question="q",
        status=status,
        answer="",
        reason="",
        citations=[],
        retrieved_book_ids=retrieved,
        final_context=[],
        latency_ms=latency,
        input_tokens=inp,
        output_tokens=out,
        error=error,
    )


def truth(qid, evidence):
    return GroundTruth(
        question_id=qid, evidence_book_ids=evidence, expected_action="answer", reference_answer="r", rubric={}
    )


def ev(qid, mode, faith=1.0, scores=(1, 1, 1, 1), eval_tokens=(50, 20), n_a=(), unscorable=()):
    names = ["facts", "conditions", "evidence", "decision"]
    return EvalRecord(
        question_id=qid,
        retrieval_mode=mode,
        faithfulness=faith,
        judge={n: JudgeItem(score=s, reason="r") for n, s in zip(names, scores)},
        eval_tokens=TokenUsage(input=eval_tokens[0], output=eval_tokens[1]),
        not_applicable=list(n_a),
        unscorable=list(unscorable),
    )


@pytest.fixture()
def data():
    runs = [
        run("Q1", "naive", ["M", "B"]),  # evidence A -> miss
        run("Q1", "hybrid", ["M", "A"]),  # hit
        run("Q2", "naive", ["A", "B"]),  # evidence A,B -> full
        run("Q2", "hybrid", ["A", "X"]),  # half
        run("Q3", "naive", [], status="error", latency=5000, error="model_timeout"),
        run("Q3", "hybrid", ["Z"], status="needs_clarification"),  # empty evidence -> N/A
    ]
    truths = {"Q1": truth("Q1", ["A"]), "Q2": truth("Q2", ["A", "B"]), "Q3": truth("Q3", [])}
    evals = [
        ev("Q1", "naive", faith=0.5, scores=(0, 0, 1, 1)),
        ev("Q1", "hybrid", faith=1.0, scores=(1, 1, 1, 1)),
        ev("Q2", "naive", faith=None, scores=(1, 1, 1, 1), n_a=["faithfulness: 사실 주장 없음"]),
        # Q2 hybrid, Q3 naive: 채점 결과 없음
        ev("Q3", "hybrid", faith=None, scores=(None, None, None, 1), n_a=["faithfulness: 되묻기"]),
    ]
    return runs, truths, evals


def test_detail_has_one_row_per_run_and_joins_eval(data):
    runs, truths, evals = data
    d = build_detail(runs, truths, evals, K)
    assert len(d) == 6
    row = d[(d.question_id == "Q1") & (d.retrieval_mode == "naive")].iloc[0]
    assert (row.hit_at_k, row.recall_at_k) == (0, 0.0)
    assert row.faithfulness == 0.5 and row.judge_facts == 0 and row.judge_evidence == 1


def test_run_without_eval_keeps_eval_columns_na_not_zero(data):
    runs, truths, evals = data
    d = build_detail(runs, truths, evals, K)
    row = d[(d.question_id == "Q2") & (d.retrieval_mode == "hybrid")].iloc[0]
    assert pd.isna(row.faithfulness) and pd.isna(row.judge_facts)


def test_empty_evidence_is_na_with_reason(data):
    runs, truths, evals = data
    d = build_detail(runs, truths, evals, K)
    row = d[(d.question_id == "Q3") & (d.retrieval_mode == "hybrid")].iloc[0]
    assert pd.isna(row.hit_at_k) and pd.isna(row.recall_at_k)
    assert row.retrieval_not_applicable


def test_summary_means_skip_na_but_keep_zero(data):
    runs, truths, evals = data
    s = build_summary(build_detail(runs, truths, evals, K), runs).set_index("retrieval_mode")
    # naive: Q1 hit 0, Q2 hit 1, Q3(error, evidence 없음) N/A -> 평균 0.5, 대상 2
    assert s.loc["naive", "hit_at_k_mean"] == 0.5 and s.loc["naive", "hit_at_k_n"] == 2
    # hybrid: Q1 hit 1, Q2 hit 1, Q3 N/A
    assert s.loc["hybrid", "hit_at_k_mean"] == 1.0
    assert s.loc["hybrid", "recall_at_k_mean"] == pytest.approx(0.75)
    # faithfulness naive: 0.5 (Q1) 하나만 대상 (Q2 None, Q3 채점 없음)
    assert s.loc["naive", "faithfulness_mean"] == 0.5 and s.loc["naive", "faithfulness_n"] == 1
    # judge facts naive: 0 (Q1), 1 (Q2) -> 0.5
    assert s.loc["naive", "judge_facts_mean"] == 0.5 and s.loc["naive", "judge_facts_n"] == 2


def test_summary_counts_not_applicable_unscorable_and_errors(data):
    runs, truths, evals = data
    s = build_summary(build_detail(runs, truths, evals, K), runs).set_index("retrieval_mode")
    assert s.loc["naive", "error_count"] == 1
    assert s.loc["naive", "not_applicable_records"] == 1
    assert s.loc["hybrid", "not_applicable_records"] == 1
    assert s.loc["naive", "unscorable_records"] == 0


def test_summary_includes_ops_and_keeps_eval_tokens_separate(data):
    runs, truths, evals = data
    s = build_summary(build_detail(runs, truths, evals, K), runs).set_index("retrieval_mode")
    assert s.loc["naive", "ok_count"] == 2 and s.loc["naive", "ok_latency_mean_ms"] == 100
    assert s.loc["naive", "input_tokens_sum"] == 30 and s.loc["naive", "input_tokens_known"] == 3
    assert s.loc["naive", "eval_input_tokens_sum"] == 100  # 서비스 토큰과 별도 열
    assert s.loc["naive", "error_rate_pct"] == pytest.approx(100 / 3)


def test_write_report_creates_files_and_csv_keeps_na_empty(data, tmp_path):
    runs, truths, evals = data
    paths = write_report(runs, truths, evals, K, tmp_path)
    assert {p.name for p in paths.values()} == {"comparison_detail.csv", "comparison_summary.csv", "comparison.md"}
    detail = pd.read_csv(paths["detail"])
    row = detail[(detail.question_id == "Q3") & (detail.retrieval_mode == "hybrid")].iloc[0]
    assert pd.isna(row.hit_at_k)  # 0이 아니라 빈 칸
    md = paths["md"].read_text(encoding="utf-8")
    assert "naive" in md and "hybrid" in md and "Hit@2" in md


def test_render_markdown_marks_unknown_as_unavailable(data):
    runs, truths, evals = data
    md = render_markdown(build_detail(runs, truths, evals, K), build_summary(build_detail(runs, truths, evals, K), runs), K)
    assert "N/A" in md


# --- 일반 질문 범위만 집계 (이슈 #28: 보안·모의 오류가 일반 오류율에 섞이지 않음) -------------------

def test_runs_outside_general_ids_are_excluded_from_all_aggregates(data):
    runs, truths, evals = data
    truths = {**truths, "SPAIR01": truth("SPAIR01", ["A"]), "MOCK-ERR": truth("MOCK-ERR", ["A"])}
    extra = [
        run("SPAIR01", "naive", ["A"], status="error", error="x"),  # 보안 질문
        run("MOCK-ERR", "naive", [], status="error", error="mock"),  # 모의 오류 시험
    ]
    from src.metrics.report import filter_general

    kept, excluded = filter_general(runs + extra, {"Q1", "Q2", "Q3"})
    assert len(kept) == len(runs) and excluded == 2
    s = build_summary(build_detail(kept, truths, evals, K), kept).set_index("retrieval_mode")
    assert s.loc["naive", "total"] == 3 and s.loc["naive", "error_count"] == 1  # 보안·모의 오류가 안 섞임


def test_write_report_notes_excluded_count_and_scope(data, tmp_path):
    runs, truths, evals = data
    truths = {**truths, "SPAIR01": truth("SPAIR01", ["A"])}
    extra = [run("SPAIR01", "naive", ["A"], status="error", error="x")]
    paths = write_report(runs + extra, truths, evals, K, tmp_path, general_ids={"Q1", "Q2", "Q3"})
    md = paths["md"].read_text(encoding="utf-8")
    assert "집계 제외" in md and "1건" in md
    assert "SPAIR01" not in pd.read_csv(paths["detail"]).question_id.tolist()


# --- 표 상단 실행 조건·설정 기록 (이슈 #29) ----------------------------------------------------

def test_markdown_header_records_run_settings(data, tmp_path):
    runs, truths, evals = data
    settings = {"run_id": "20261110-090000", "질문 수": 3, "선택 시드": 20261105}
    paths = write_report(runs, truths, evals, K, tmp_path, settings=settings)
    md = paths["md"].read_text(encoding="utf-8")
    assert "## 실행 조건" in md
    assert md.index("## 실행 조건") < md.index("## 품질")  # 표 상단
    for needle in ("20261110-090000", "질문 수", "20261105", "k", "naive"):
        assert needle in md


def test_load_frozen_config_reads_uppercase_values_when_config_exists(monkeypatch):
    import sys
    import types

    from src.metrics.report import load_frozen_config

    fake = types.SimpleNamespace(K=5, CONTEXT_TOKEN_LIMIT=3000, GENERATION_MODEL="gpt-6-luna", _private=1, helper=lambda: 1)
    monkeypatch.setitem(sys.modules, "src.config", fake)
    assert load_frozen_config() == {"K": 5, "CONTEXT_TOKEN_LIMIT": 3000, "GENERATION_MODEL": "gpt-6-luna"}


def test_load_frozen_config_is_empty_when_config_missing(monkeypatch):
    import sys

    from src.metrics.report import load_frozen_config

    monkeypatch.setitem(sys.modules, "src.config", None)  # import 불가 상태
    assert load_frozen_config() == {}


def test_frozen_config_reads_settings_but_never_urls_or_keys(monkeypatch):
    import types

    from src.metrics import report

    fake = types.SimpleNamespace(K=5, GENERATION_MODEL="m", QDRANT_URL="http://internal:6333", OPENAI_API_KEY="sk-x", ROOT=object())
    monkeypatch.setattr(report.importlib, "import_module", lambda name: fake)
    cfg = report.load_frozen_config()
    assert cfg == {"K": 5, "GENERATION_MODEL": "m"}  # 주소·키·경로 객체는 제외


# --- 빈칸 이유는 "항목: 이유" 형식 (judge와 합의). 항목별로 센다 --------------------------------

def test_reason_item_is_read_from_prefix():
    from src.metrics.report import reason_item

    assert reason_item("faithfulness: 사실 주장 없음") == "faithfulness"
    assert reason_item("evidence : 호출 실패(timeout)") == "evidence"  # 콜론 앞뒤 공백 허용
    assert reason_item("decision: 이유에 : 가 또 있어도 첫 콜론 기준") == "decision"


def test_reason_without_valid_item_is_unclassified_not_dropped():
    from src.metrics.report import reason_item

    assert reason_item("이유만 있음") == "unclassified"
    assert reason_item("모르는항목: 이유") == "unclassified"
    assert reason_item("") == "unclassified"


def test_detail_lists_which_items_are_blank():
    runs = [run("Q1", "naive", ["A"])]
    evals = [
        ev(
            "Q1",
            "naive",
            n_a=["faithfulness: 되묻기라 사실 주장 없음", "faithfulness: 중복 사유"],
            unscorable=["evidence: 호출 실패", "이유만 있음"],
        )
    ]
    d = build_detail(runs, {"Q1": truth("Q1", ["A"])}, evals, K).iloc[0]
    assert d.not_applicable_items == "faithfulness"  # 같은 항목은 한 번만
    assert d.unscorable_items == "evidence,unclassified"  # 정해진 순서, 형식 어긋난 건 미분류
    assert d.not_applicable == "faithfulness: 되묻기라 사실 주장 없음; faithfulness: 중복 사유"  # 원문 이유는 그대로


def test_detail_items_are_blank_when_no_eval_result():
    d = build_detail([run("Q1", "naive", ["A"])], {"Q1": truth("Q1", ["A"])}, [], K).iloc[0]
    assert pd.isna(d.not_applicable_items) and pd.isna(d.unscorable_items)  # 채점 없음은 0이 아니라 빈 칸


def test_summary_counts_records_per_item():
    runs = [run(f"Q{i}", "naive", ["A"]) for i in (1, 2, 3, 4)]
    truths = {f"Q{i}": truth(f"Q{i}", ["A"]) for i in (1, 2, 3, 4)}
    evals = [
        ev("Q1", "naive", n_a=["faithfulness: 되묻기"]),
        ev("Q2", "naive", n_a=["faithfulness: 되묻기", "faithfulness: 또"], unscorable=["evidence: 실패"]),
        ev("Q3", "naive", unscorable=["evidence: 실패", "decision: 실패"]),
        ev("Q4", "naive"),
    ]
    s = build_summary(build_detail(runs, truths, evals, K), runs).iloc[0]
    assert s.not_applicable_faithfulness == 2  # 레코드 수(한 레코드에 같은 항목이 두 번이어도 1)
    assert s.unscorable_evidence == 2 and s.unscorable_decision == 1
    assert s.unscorable_facts == 0 and s.not_applicable_decision == 0
    assert s.not_applicable_records == 2 and s.unscorable_records == 2  # 기존 레코드 단위 집계는 유지


def test_markdown_shows_blank_reasons_by_item(data):
    runs, truths, evals = data
    d = build_detail(runs, truths, evals, K)
    md = render_markdown(d, build_summary(d, runs), K)
    assert "빈칸 이유" in md and "충실도" in md and "미분류" in md
