"""질문 선택: 답변 / 추가 확인 / 보류 유형을 섞어 일반 평가 질문을 고르고 이유와 함께 기록한다.

- 유형별 개수(quota)는 팀이 정한다. 시드를 고정해 같은 입력이면 같은 선택이 나온다.
- 한 유형 안에서는 평가 파일(development / additional / expansion_validation)이 고르게 섞이게 돌아가며 뽑는다.
- expected_action은 선택 기록(왜 이 질문인가)에만 남긴다. 실행 입력은 `Question`(id, question)만 쓴다.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from src.contracts import GroundTruth
from .loader import Question

ACTION_LABEL = {"answer": "답변 가능", "clarify": "추가 확인 필요", "abstain": "보류 필요"}


class SelectedQuestion(Question):
    expected_action: str
    reason: str


def select_questions(
    questions: list[Question],
    truths: dict[str, GroundTruth],
    quota: dict[str, int],
    seed: int,
) -> list[SelectedQuestion]:
    """quota = {"answer": 9, "clarify": 3, "abstain": 3} 처럼 유형별 개수.(추가확인/답변 가능/추가 확인)"""
    rng = random.Random(seed)
    pools: dict[str, list[Question]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q.id):  # 입력 순서와 무관하게 재현되도록
        pools[truths[q.id].expected_action].append(q)

    selected: list[SelectedQuestion] = []
    for action, n in quota.items():
        pool = pools.get(action, [])
        if n > len(pool):
            raise ValueError(f"{action} 유형은 {len(pool)}개뿐인데 {n}개를 요청했다")
        by_source: dict[str, list[Question]] = defaultdict(list)
        for q in pool:
            by_source[q.source].append(q)
        for items in by_source.values():
            rng.shuffle(items)
        sources = sorted(by_source)
        rng.shuffle(sources)

        picked: list[Question] = []
        while len(picked) < n:  # 출처 파일을 돌아가며 한 개씩
            for s in sources:
                if by_source[s] and len(picked) < n:
                    picked.append(by_source[s].pop())
        for q in picked:
            selected.append(
                SelectedQuestion(
                    id=q.id,
                    question=q.question,
                    source=q.source,
                    expected_action=action,
                    reason=f"{ACTION_LABEL.get(action, action)} 유형 {n}개 중 하나. "
                    f"출처 {q.source}를 고르게 섞는 층화 무작위(seed={seed})",
                )
            )
    return sorted(selected, key=lambda s: s.id)


def load_selection(path: Path | str) -> list[Question]:
    """results/questions.json에서 실행용 `Question`만 읽는다(expected_action·reason은 버린다)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Question(id=q["id"], question=q["question"], source=q["source"]) for q in data["questions"]]


def write_selection(
    selected: list[SelectedQuestion],
    quota: dict[str, int],
    seed: int,
    out_path: Path | str,
    pool_size: dict[str, int] | None = None,
) -> Path:
    """results/questions.json. 이미 있으면 덮어쓰지 않는다."""
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"이미 있다. 지우거나 다른 경로를 써라: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": seed,
        "quota": quota,
        "distribution": {a: sum(1 for s in selected if s.expected_action == a) for a in quota},  # 실제로 고른 expected_action 분포
        "pool": pool_size,  # 고를 수 있던 전체 분포(쏠림 설명용). 모르면 null
        "count": len(selected),
        "questions": [s.model_dump() for s in selected],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


DEFAULT_QUOTA = {"answer": 9, "clarify": 3, "abstain": 3}
DEFAULT_SEED = 20261105  # 킥오프일. 바꾸면 선택이 바뀌므로 확정 뒤에는 고정한다.


def main(argv: list[str] | None = None) -> None:
    import argparse

    from .loader import load_evaluation

    p = argparse.ArgumentParser(description="일반 평가 질문 선택 -> results/questions.json")
    p.add_argument("--eval-dir", type=Path, default=Path("data/shipping/evaluation"))
    p.add_argument("--answer", type=int, default=DEFAULT_QUOTA["answer"])
    p.add_argument("--clarify", type=int, default=DEFAULT_QUOTA["clarify"])
    p.add_argument("--abstain", type=int, default=DEFAULT_QUOTA["abstain"])
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--out", type=Path, default=Path("results/questions.json"))
    args = p.parse_args(argv)

    quota = {"answer": args.answer, "clarify": args.clarify, "abstain": args.abstain}
    questions, truths = load_evaluation(args.eval_dir)
    selected = select_questions(questions, truths, quota, seed=args.seed)
    pool = {a: sum(1 for t in truths.values() if t.expected_action == a) for a in quota}
    path = write_selection(selected, quota, seed=args.seed, out_path=args.out, pool_size=pool)
    print(f"{len(selected)}개 선택: {path}")


if __name__ == "__main__":
    main()
