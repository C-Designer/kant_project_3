"""채점 흔들림(안정성) 측정: 같은 답안을 여러 번 채점해서 점수가 바뀌는지 본다.

gpt-6-luna는 무작위성(temperature)을 0으로 고정할 수 없어서, 같은 답안도
채점할 때마다 점수가 달라질 수 있다. 얼마나 자주 그런지 숫자로 확인한다.

실행 예 (실제 AI 필요)
  python -m src.judge.stability --cases data/judge_mock/cases.jsonl \
      --truths data/shipping/evaluation/development.json --per-kind 2 --repeat 3

출력: 칸별 "흔들린 답안 수 / 확인한 답안 수"와 흔들린 사례 → data/judge_mock/stability.md
"""

from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

from src.judge.platform_adapter import llm_call
from src.judge.judge import judge_one
from src.judge.mock_cases import MockCase
from src.judge.rules import JUDGE_ITEMS
from src.judge.score import load_ground_truths


def main() -> None:
    p = argparse.ArgumentParser(description="같은 답안 반복 채점으로 흔들림 측정")
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--truths", type=Path, nargs="+", required=True)
    p.add_argument("--per-kind", type=int, default=2, help="종류마다 몇 장 뽑을지 (서비스 오류 종류는 AI를 안 부르므로 제외)")
    p.add_argument("--repeat", type=int, default=3, help="한 답안을 몇 번 채점할지")
    p.add_argument("--seed", type=int, default=1, help="표본 시드. calibrate(시드 0)와 다른 답안이 뽑히게 기본 1")
    p.add_argument("--out", type=Path, default=Path("data/judge_mock/stability.md"))
    args = p.parse_args()

    cases = [MockCase.model_validate_json(l) for l in args.cases.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_kind: dict[str, list[MockCase]] = defaultdict(list)
    for c in cases:
        if c.kind != "error":
            by_kind[c.kind].append(c)
    rng = random.Random(args.seed)
    sample = [c for k in sorted(by_kind) for c in rng.sample(by_kind[k], min(args.per_kind, len(by_kind[k])))]
    truths = load_ground_truths(args.truths)
    llm = lambda messages: llm_call(messages, kind="eval")

    flips: dict[str, list[int]] = {item: [0, 0] for item in JUDGE_ITEMS}  # [흔들린 수, 확인한 수]
    rows, flipped = [], []
    for case in sample:
        scores: dict[str, list] = defaultdict(list)
        for _ in range(args.repeat):
            items, _, err = judge_one(case.run, truths[case.run.question_id], llm)
            for item in JUDGE_ITEMS:
                scores[item].append(items[item].score if items else "실패")
        cells = []
        for item in JUDGE_ITEMS:
            seen = scores[item]
            unstable = len(set(map(str, seen))) > 1
            flips[item][1] += 1
            flips[item][0] += unstable
            cells.append(("⚠ " if unstable else "") + "/".join("-" if s is None else str(s) for s in seen))
            if unstable:
                flipped.append(f"- `{case.case_id}` {item}: {seen}")
        rows.append(f"| {case.case_id} | " + " | ".join(cells) + " |")

    lines = [
        "# 채점 흔들림 측정",
        "",
        f"답안 {len(sample)}장 × {args.repeat}번 채점 (Judge 4항목). `-`는 빈칸(null), ⚠는 반복 사이에 점수가 바뀐 칸.",
        "",
        "| 칸 | 흔들린 답안 / 확인한 답안 |",
        "|---|---|",
    ] + [f"| {item} | {f} / {n} |" for item, (f, n) in flips.items()] + [
        "",
        "| 답안 | facts | conditions | evidence | decision |",
        "|---|---|---|---|---|",
    ] + rows + ["", "## 흔들린 칸", ""] + (flipped or ["(없음)"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[4:10]))
    print(f"\n상세 → {args.out}")


if __name__ == "__main__":
    main()
