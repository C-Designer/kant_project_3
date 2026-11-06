"""비교표 생성: RunRecord + GroundTruth + EvalRecord -> detail/summary CSV와 comparison.md.

- 질문 x 방식 한 행(detail)과 방식별 평균(summary)을 만든다.
- 평균은 None/NA를 분모에서 빼고 0점은 포함한다. 평균 옆에 평가 대상 수(`*_n`)를 둔다.
- 평가(RAGAS·Judge) 호출 토큰은 서비스 토큰과 별도 열(`eval_*`).
- CSV에서 측정 못 한 값은 빈 칸이다(0으로 쓰지 않는다).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.contracts import EvalRecord, GroundTruth, RunRecord
from .ops_metrics import summarize_ops
from .retrieval_metrics import hit_recall

JUDGE_ITEMS = ("facts", "conditions", "evidence", "decision")
QUALITY_METRICS = (
    "hit_at_k",
    "recall_at_k",
    "faithfulness",
    "judge_facts",
    "judge_conditions",
    "judge_evidence",
    "judge_decision",
)
_INT_COLS = ["hit_at_k", "judge_facts", "judge_conditions", "judge_evidence", "judge_decision",
             "latency_ms", "input_tokens", "output_tokens", "eval_input_tokens", "eval_output_tokens", "k"]
_FLOAT_COLS = ["recall_at_k", "faithfulness"]


# 빈칸(해당 없음·평가 불가) 이유는 judge와 합의한 "항목: 이유" 형식이다. 항목은 아래 다섯 개 중 하나.
REASON_ITEMS = ("faithfulness",) + JUDGE_ITEMS
UNCLASSIFIED = "unclassified"  # 형식이 어긋난 이유. 버리지 않고 이 칸에 센다
_ITEM_LABELS = {
    "faithfulness": "충실도",
    "facts": "사실",
    "conditions": "조건",
    "evidence": "근거",
    "decision": "판단",
    UNCLASSIFIED: "미분류",
}

MODE_ORDER = ("naive", "hybrid", "hybrid_rerank")  # 발제 순서. 표에서 이 순서로 보여 준다.


def reason_item(reason: str) -> str:
    """"항목: 이유"에서 항목을 읽는다. 첫 콜론 기준. 알 수 없는 항목이거나 형식이 아니면 미분류."""
    item, sep, _ = reason.partition(":")
    item = item.strip()
    return item if sep and item in REASON_ITEMS else UNCLASSIFIED


def _items_of(reasons: list[str]) -> str:
    """이유 목록에 나온 항목을 정해진 순서로, 중복 없이 쉼표로 잇는다."""
    found = {reason_item(r) for r in reasons}
    return ",".join(i for i in (*REASON_ITEMS, UNCLASSIFIED) if i in found)


def _mode_rank(mode: str) -> int:
    return MODE_ORDER.index(mode) if mode in MODE_ORDER else len(MODE_ORDER)


def build_detail(
    runs: Iterable[RunRecord],
    truths: dict[str, GroundTruth],
    evals: Iterable[EvalRecord],
    k: int,
) -> pd.DataFrame:
    """질문 x 방식 한 행. 채점 결과가 없는 실행은 평가 열이 NA로 남는다."""
    eval_by_key = {(e.question_id, e.retrieval_mode): e for e in evals}
    rows = []
    for r in runs:
        truth = truths[r.question_id]
        score = hit_recall(truth.evidence_book_ids, r.retrieved_book_ids, k)
        e = eval_by_key.get((r.question_id, r.retrieval_mode))
        judge = (e.judge or {}) if e else {}
        row = {
            "question_id": r.question_id,
            "retrieval_mode": r.retrieval_mode,
            "request_id": r.request_id,
            "status": r.status,
            "expected_action": truth.expected_action,
            "k": k,
            "hit_at_k": score.hit,
            "recall_at_k": score.recall,
            "retrieval_not_applicable": score.not_applicable,
            "faithfulness": e.faithfulness if e else None,
            "latency_ms": r.latency_ms,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "error": r.error,
            "eval_input_tokens": e.eval_tokens.input if e and e.eval_tokens else None,
            "eval_output_tokens": e.eval_tokens.output if e and e.eval_tokens else None,
            "not_applicable": "; ".join(e.not_applicable) if e else None,
            "unscorable": "; ".join(e.unscorable) if e else None,
            "not_applicable_items": _items_of(e.not_applicable) if e else None,  # 어느 항목이 해당 없음인지
            "unscorable_items": _items_of(e.unscorable) if e else None,
        }
        for name in JUDGE_ITEMS:
            item = judge.get(name)
            row[f"judge_{name}"] = item.score if item else None
        rows.append(row)

    df = pd.DataFrame(rows)
    for c in _INT_COLS:
        df[c] = df[c].astype("Int64")
    for c in _FLOAT_COLS:
        df[c] = df[c].astype("Float64")
    df["_mode_order"] = df["retrieval_mode"].map(_mode_rank)
    df = df.sort_values(["question_id", "_mode_order"], kind="stable").drop(columns="_mode_order")
    return df.reset_index(drop=True)


def _count_nonempty(series: pd.Series) -> int:
    return int(series.fillna("").astype(str).str.strip().ne("").sum())


def _count_item(series: pd.Series, item: str) -> int:
    """항목이 한 번이라도 나온 레코드 수(한 레코드에 같은 항목이 여러 번이어도 1)."""
    return int(series.fillna("").astype(str).apply(lambda v: item in v.split(",")).sum())


def build_summary(detail: pd.DataFrame, runs: Iterable[RunRecord]) -> pd.DataFrame:
    """방식별 평균(+평가 대상 수), 해당 없음·평가 불가·오류 건수, 운영 지표."""
    ops = summarize_ops(runs)
    rows = []
    for mode, g in sorted(detail.groupby("retrieval_mode"), key=lambda kv: _mode_rank(kv[0])):
        o = ops[mode]
        row: dict = {"retrieval_mode": mode, "k": int(g["k"].iloc[0]), "questions": len(g)}
        for m in QUALITY_METRICS:
            col = g[m]
            row[f"{m}_mean"] = col.mean() if col.notna().any() else pd.NA
            row[f"{m}_n"] = int(col.notna().sum())
        row.update(
            not_applicable_records=_count_nonempty(g["not_applicable"]),
            unscorable_records=_count_nonempty(g["unscorable"]),
            retrieval_not_applicable=_count_nonempty(g["retrieval_not_applicable"]),
            **{f"not_applicable_{i}": _count_item(g["not_applicable_items"], i) for i in (*REASON_ITEMS, UNCLASSIFIED)},
            **{f"unscorable_{i}": _count_item(g["unscorable_items"], i) for i in (*REASON_ITEMS, UNCLASSIFIED)},
            total=o.total,
            ok_count=o.ok_count,
            error_count=o.error_count,
            error_rate_pct=o.error_rate_pct,
            ok_latency_mean_ms=o.ok_latency_mean_ms,
            ok_latency_known=o.ok_latency_known,
            error_latency_mean_ms=o.error_latency_mean_ms,
            input_tokens_sum=o.input_tokens_sum,
            input_tokens_known=o.input_tokens_known,
            output_tokens_sum=o.output_tokens_sum,
            output_tokens_known=o.output_tokens_known,
            eval_input_tokens_sum=g["eval_input_tokens"].sum() if g["eval_input_tokens"].notna().any() else pd.NA,
            eval_output_tokens_sum=g["eval_output_tokens"].sum() if g["eval_output_tokens"].notna().any() else pd.NA,
        )
        rows.append(row)
    return pd.DataFrame(rows)


def filter_general(runs: Iterable[RunRecord], general_ids: set[str]) -> tuple[list[RunRecord], int]:
    """일반 평가 질문 범위의 실행만 남긴다. 보안 비교·모의 오류 시험 등은 일반 평균·오류율에 섞지 않는다."""
    runs = list(runs)
    kept = [r for r in runs if r.question_id in general_ids]
    return kept, len(runs) - len(kept)


_NOT_FOR_REPORT_SUFFIXES = ("_URL", "_KEY", "_TOKEN", "_SECRET", "_PASSWORD")


def load_frozen_config() -> dict:
    """`src/config.py`의 동결값(대문자 상수)을 읽는다. 파일이 없으면 빈 dict."""
    try:
        cfg = importlib.import_module("src.config")
    except ImportError:
        return {}
    simple = (int, float, str, bool, list, tuple, dict, type(None))
    return {
        name: getattr(cfg, name)
        for name in dir(cfg)
        if name.isupper()
        and not name.startswith("_")
        and not name.endswith(_NOT_FOR_REPORT_SUFFIXES)  # 서버 주소·키는 비교표에 싣지 않는다
        and isinstance(getattr(cfg, name), simple)
    }


def _fmt(v, digits: int = 3) -> str:
    if v is None or pd.isna(v):
        return "N/A"
    if isinstance(v, float) or (hasattr(v, "dtype") and getattr(v.dtype, "kind", "") == "f"):
        return f"{float(v):.{digits}f}"
    return str(v)


def _fmt_setting(v) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}={x}" for k, x in v.items())
    return "N/A" if v is None else str(v)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def render_markdown(
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    k: int,
    settings: dict | None = None,
    excluded: int = 0,
) -> str:
    def with_n(row, m):
        return f"{_fmt(row[f'{m}_mean'])} (n={row[f'{m}_n']})"

    quality = _table(
        ["방식", f"Hit@{k}", f"Recall@{k}", "Faithfulness", "사실", "조건", "근거", "판단", "해당 없음", "평가 불가", "오류"],
        [
            [
                r["retrieval_mode"],
                with_n(r, "hit_at_k"),
                with_n(r, "recall_at_k"),
                with_n(r, "faithfulness"),
                with_n(r, "judge_facts"),
                with_n(r, "judge_conditions"),
                with_n(r, "judge_evidence"),
                with_n(r, "judge_decision"),
                str(r["not_applicable_records"]),
                str(r["unscorable_records"]),
                str(r["error_count"]),
            ]
            for r in summary.to_dict("records")
        ],
    )
    ops = _table(
        ["방식", "정상 평균 응답(ms)", "정상 건수", "오류율(%)", "오류 건수", "입력 토큰", "출력 토큰", "평가 호출 토큰(입력/출력, 별도)"],
        [
            [
                r.retrieval_mode,
                f"{_fmt(r.ok_latency_mean_ms, 1)} (시간 확인 {r.ok_latency_known})",
                str(r.ok_count),
                _fmt(r.error_rate_pct, 1),
                f"{r.error_count}/{r.total}",
                f"{_fmt(r.input_tokens_sum)} (확인 {r.input_tokens_known}건)",
                f"{_fmt(r.output_tokens_sum)} (확인 {r.output_tokens_known}건)",
                f"{_fmt(r.eval_input_tokens_sum)} / {_fmt(r.eval_output_tokens_sum)}",
            ]
            for r in summary.itertuples()
        ],
    )
    items = (*REASON_ITEMS, UNCLASSIFIED)
    blanks = _table(
        ["방식"] + [_ITEM_LABELS[i] for i in items],
        [
            [r["retrieval_mode"]] + [f"{r[f'not_applicable_{i}']} / {r[f'unscorable_{i}']}" for i in items]
            for r in summary.to_dict("records")
        ],
    )
    per_q = _table(
        ["질문", "방식", "상태", f"Hit@{k}", f"Recall@{k}", "Faith.", "사실", "조건", "근거", "판단"],
        [
            [
                r.question_id,
                r.retrieval_mode,
                r.status,
                _fmt(r.hit_at_k),
                _fmt(r.recall_at_k),
                _fmt(r.faithfulness),
                _fmt(r.judge_facts),
                _fmt(r.judge_conditions),
                _fmt(r.judge_evidence),
                _fmt(r.judge_decision),
            ]
            for r in detail.itertuples()
        ],
    )
    modes = ", ".join(sorted(detail["retrieval_mode"].unique(), key=_mode_rank))
    condition_rows = [
        ["k (답변 생성 직전 상위 청크 수)", str(k)],
        ["비교 방식", modes],
        ["일반 평가 질문 수", str(detail["question_id"].nunique())],
        ["집계 제외", f"{excluded}건 (보안 비교·모의 오류 등 일반 평가 범위 밖)"],
    ] + [[str(key), _fmt_setting(val)] for key, val in (settings or {}).items()]
    conditions = _table(["항목", "값"], condition_rows)
    return "\n".join(
        [
            "# 비교표",
            "",
            "## 실행 조건",
            "",
            conditions,
            "",
            f"평균은 해당 없음·평가 불가(N/A)를 제외하고 0점은 포함한다. 괄호는 평가 대상 수.",
            "",
            "## 품질 (방식별 평균)",
            "",
            quality,
            "",
            "## 빈칸 이유 (항목별 레코드 수, 해당 없음 / 평가 불가)",
            "",
            blanks,
            "",
            "## 운영 지표 (서비스 호출 기준)",
            "",
            ops,
            "",
            "## 질문별",
            "",
            per_q,
            "",
        ]
    )


def write_report(
    runs: list[RunRecord],
    truths: dict[str, GroundTruth],
    evals: list[EvalRecord],
    k: int,
    out_dir: Path | str,
    *,
    general_ids: set[str] | None = None,
    settings: dict | None = None,
) -> dict[str, Path]:
    """general_ids를 주면 그 질문들의 실행만 집계한다(나머지는 `집계 제외`로 표에 건수만 남긴다)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    excluded = 0
    if general_ids is not None:
        runs, excluded = filter_general(runs, general_ids)
    detail = build_detail(runs, truths, evals, k)
    summary = build_summary(detail, runs)
    paths = {
        "detail": out_dir / "comparison_detail.csv",
        "summary": out_dir / "comparison_summary.csv",
        "md": out_dir / "comparison.md",
    }
    detail.to_csv(paths["detail"], index=False, encoding="utf-8")
    summary.to_csv(paths["summary"], index=False, encoding="utf-8")
    paths["md"].write_text(render_markdown(detail, summary, k, settings, excluded), encoding="utf-8")
    return paths


def main(argv: list[str] | None = None) -> None:
    import argparse

    from .loader import load_evaluation
    from .run import load_runs

    p = argparse.ArgumentParser(description="실행 결과(+judge 채점)로 비교표 생성")
    p.add_argument("--run", required=True, help="run_id")
    p.add_argument("--k", required=True, type=int, help="답변 생성 직전 선택한 상위 청크 수(세 방식 동일)")
    p.add_argument("--eval-dir", type=Path, default=Path("data/shipping/evaluation"))
    p.add_argument("--results-dir", type=Path, default=Path("results"))
    args = p.parse_args(argv)

    run_dir = args.results_dir / "runs" / args.run
    if not run_dir.is_dir():
        raise SystemExit(f"실행 결과 폴더가 없다: {run_dir}")

    runs = load_runs(run_dir)
    _, truths = load_evaluation(args.eval_dir)
    meta_path = run_dir / "run_meta.json"  # 이 실행이 다룬 일반 질문 범위
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    general_ids = set(meta["question_ids"]) if meta.get("question_ids") else None
    eval_path = run_dir / "eval.jsonl"  # judge가 만든다. 아직 없으면 평가 열은 빈 칸
    evals = (
        [EvalRecord.model_validate_json(line) for line in eval_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if eval_path.exists()
        else []
    )
    settings = {
        "run_id": args.run,
        "실행 시작": meta.get("started_at"),
        "질문 선택 시드": meta.get("selection_seed"),
        "유형별 질문 수": meta.get("quota"),
        **{f"config.{name}": val for name, val in load_frozen_config().items()},
    }
    if not load_frozen_config():
        settings["config.py 동결값"] = "없음 (아직 동결 전이거나 파일 없음)"
    paths = write_report(runs, truths, evals, args.k, run_dir, general_ids=general_ids, settings=settings)
    print(f"비교표 생성: {paths['md']}" + ("" if evals else "  (eval.jsonl 없음: 평가 열은 빈 칸)"))


if __name__ == "__main__":
    main()
