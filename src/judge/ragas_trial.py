"""RAGAS Faithfulness 실제 시험: 한국어 답안에서 주장을 제대로 뽑고, 기대한 방향의 점수가 나오는지.

종류별 기대
- good (답변 문항)        : 주장이 문맥에 있으니 높아야 함 (1에 가깝게)
- time_swap              : 바꾼 시각이 문맥과 다르니 good보다 낮아야 함
- no_context             : 대조할 자료가 없으니 0에 가까워야 함
- good (되묻기 문항)      : 사실 주장이 없으면 None(해당 없음)이어야 함
- wrong_abstain          : "확인할 수 없다"는 말뿐이라 None 또는 낮은 값

실행 예 (실제 AI 필요)
  python -m src.judge.ragas_trial --cases data/judge_mock/cases.jsonl

출력 → data/judge_mock/ragas_trial.md (점수, 토큰, RAGAS가 뽑은 주장 목록)
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from src.judge import ragas_eval
from src.judge.platform_adapter import llm_call
from src.judge.mock_cases import MockCase

PLAN = [("good", "answered", 2), ("time_swap", None, 2), ("no_context", None, 2), ("good", "needs_clarification", 1), ("wrong_abstain", None, 1)]


def main() -> None:
    p = argparse.ArgumentParser(description="RAGAS Faithfulness 실제 시험")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--seed", type=int, default=2)
    p.add_argument("--ids", nargs="*", default=None, help="특정 답안만. 예: S-DEV-30:good S-DEV-11:wrong_abstain")
    p.add_argument("--out", type=Path, default=Path("data/judge_mock/ragas_trial.md"))
    args = p.parse_args()

    cases = [MockCase.model_validate_json(l) for l in args.cases.read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = random.Random(args.seed)
    sample: list[MockCase] = []
    if args.ids:
        sample = [c for c in cases if c.case_id in args.ids]
    else:
        for kind, status, n in PLAN:
            pool = [c for c in cases if c.kind == kind and (status is None or c.run.status == status)]
            sample += rng.sample(pool, min(n, len(pool)))

    lines = ["# RAGAS Faithfulness 실제 시험", "", "| 답안 | 점수 | 해당 없음 / 평가 불가 | 토큰(입력/출력) |", "|---|---|---|---|"]
    details = ["", "## RAGAS가 뽑은 주장", ""]
    for case in sample:
        log: list[str] = []

        def recording_llm(messages):
            res = llm_call(messages, kind="eval")
            log.append(res.text)
            return res

        score, tokens, na, us = ragas_eval.faithfulness(case.run, recording_llm)
        shown = "None" if score is None else f"{score:.2f}"
        tok = f"{tokens.input}/{tokens.output}" if tokens else "-"
        lines.append(f"| {case.case_id} | {shown} | {na or us or ''} | {tok} |")

        details.append(f"### {case.case_id}")
        details.append(f"- 답변: {case.run.answer}")
        statements = []
        if log:
            try:
                statements = json.loads(log[0][log[0].index("{"): log[0].rindex("}") + 1]).get("statements", [])
            except (ValueError, json.JSONDecodeError):
                statements = ["(첫 단계 출력 해석 실패)"]
        details += [f"  - 주장: {s}" for s in statements] or ["  - 주장: (없음)"]
        details.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines + details) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n상세 → {args.out}")


if __name__ == "__main__":
    main()
