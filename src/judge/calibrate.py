"""채점관 시험: 정답을 아는 가짜 답안을 채점시키고 몇 개나 맞혔는지 센다.

실행 예 (실제 AI 필요: OPENAI_API_KEY)
  python -m src.judge.calibrate --cases data/judge_mock/cases.jsonl \
      --truths data/shipping/evaluation/development.json --limit 30

출력: 종류(kind) × 칸(item)별 "맞힌 수 / 확인한 수"와 틀린 사례 목록 → data/judge_mock/calibration.md

흔들림 측정: --repeat 3 처럼 주면 같은 답안을 여러 번 채점해, 반복 사이에 점수가 바뀐 칸도 함께 적는다.
gpt-6-luna는 temperature를 고정할 수 없어 같은 답안도 점수가 달라질 수 있다.
shortcut: 표본은 시드 0 하나뿐이고 서비스 오류 종류도 포함한다. 시드를 바꿔 보고 싶으면 --seed를 만든다.
"""

from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

from src.judge.mock_cases import MockCase
from src.judge.score import llm_call, load_ground_truths, score_one


def compare(case: MockCase, rec) -> list[tuple[str, object, object]]:
    """(칸, 기대, 실제) 목록. 기대와 실제를 그대로 비교한다 (None도 None끼리만 일치)."""
    out = []
    for item, expected in case.expected.items():
        actual = rec.judge[item].score if rec.judge and item in rec.judge else "채점 실패"
        out.append((item, expected, actual))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="채점관 정확도 측정")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--truths", type=Path, nargs="+", required=True)
    p.add_argument("--limit", type=int, default=None, help="앞에서부터 N건만 (비용 절약)")
    p.add_argument("--kinds", nargs="*", default=None, help="특정 종류만. 예: good time_swap")
    p.add_argument("--per-kind", type=int, default=None, help="종류마다 N건씩 골고루 뽑기 (여러 문항에서 무작위, 고정 시드)")
    p.add_argument("--repeat", type=int, default=1, help="한 답안을 몇 번 채점할지. 2 이상이면 흔들린 칸도 적는다")
    p.add_argument("--out", type=Path, default=Path("data/judge_mock/calibration.md"))
    args = p.parse_args()

    cases = [MockCase.model_validate_json(l) for l in args.cases.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.kinds:
        cases = [c for c in cases if c.kind in args.kinds]
    if args.per_kind:
        rng = random.Random(0)  # 매번 같은 표본이 뽑히도록 시드 고정
        by_kind: dict[str, list[MockCase]] = defaultdict(list)
        for c in cases:
            by_kind[c.kind].append(c)
        cases = [c for kind in sorted(by_kind) for c in rng.sample(by_kind[kind], min(args.per_kind, len(by_kind[kind])))]
    cases = cases[: args.limit]
    truths = load_ground_truths(args.truths)
    llm = lambda messages: llm_call(messages, kind="eval")

    hits: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    misses: list[str] = []
    seen: dict[tuple[str, str], list] = defaultdict(list)  # (답안, 칸) → 반복마다의 점수
    for case in [c for c in cases for _ in range(args.repeat)]:  # 같은 답안을 repeat번 연달아
        rec = score_one(case.run, truths[case.run.question_id], llm, use_ragas=False)
        for item, expected, actual in compare(case, rec):
            seen[(case.case_id, item)].append(actual)
            cell = hits[(case.kind, item)]
            cell[1] += 1
            if expected == actual:
                cell[0] += 1
            else:
                reason = rec.judge[item].reason if rec.judge and item in rec.judge else "; ".join(rec.unscorable)
                misses.append(f"- `{case.case_id}` {item}: 기대 {expected}, 실제 {actual} — {reason}")

    lines = ["# 채점관 시험 결과", "", f"가짜 답안 {len(cases)}건 (Faithfulness 제외, Judge 4항목만)", "", "| 종류 | 칸 | 맞힘 / 확인 |", "|---|---|---|"]
    for (kind, item), (ok, total) in sorted(hits.items()):
        lines.append(f"| {kind} | {item} | {ok} / {total} |")
    lines += ["", "## 기대와 다른 사례", ""] + (misses or ["(없음)"])
    if args.repeat > 1:
        flipped = [f"- `{cid}` {item}: {v}" for (cid, item), v in seen.items() if len(set(map(str, v))) > 1]
        lines += ["", f"## 흔들린 칸 ({args.repeat}번 채점, 반복 사이에 점수가 바뀐 칸)", ""] + (flipped or ["(없음)"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:len(hits) + 6]))
    print(f"\n상세 → {args.out}")


if __name__ == "__main__":
    main()
