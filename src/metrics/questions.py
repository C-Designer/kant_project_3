"""질문 선택: 답변 / 추가 확인 / 보류 유형을 섞어 일반 평가 질문을 고르고 이유와 함께 기록한다.

- 유형별 개수(quota)는 팀이 정한다. 시드를 고정해 같은 입력이면 같은 선택이 나온다.
- 한 유형 안에서 근거 문서가 2개 이상인 질문(복수)의 비율을 전체 풀의 비율에 맞춘다. 단일 근거만 쏠리면 방식 간 차이가 안 드러난다.
- 파일별 최소 개수와 근거 문서 수의 최소 가짓수는 구조 조건으로만 건다. 검색 결과는 쓰지 않는다. 조건을 만족할 때까지 시도 번호를 올려 다시 뽑는다.
- expected_action은 선택 기록(왜 이 질문인가)에만 남긴다. 실행 입력은 `Question`(id, question)만 쓴다.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
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
    *,
    min_per_source: int = 0,
    min_docs: int = 0,
    max_attempts: int = 100_000,
) -> list[SelectedQuestion]:
    """quota = {"answer": 9, "clarify": 3, "abstain": 3} 처럼 유형별 개수.

    유형 안에서 복수 근거 질문 수 = round(개수 x 풀의 복수 근거 비율). 시도 `seed-번호`로 뽑아 보고,
    모든 평가 파일이 min_per_source개 이상이고 근거 문서가 min_docs가지 이상이면 채택한다.
    """
    pools: dict[str, list[Question]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q.id):  # 입력 순서와 무관하게 재현되도록
        pools[truths[q.id].expected_action].append(q)

    def is_multi(q: Question) -> bool:
        return len(truths[q.id].evidence_book_ids) >= 2

    plan: dict[str, tuple[list[Question], list[Question], int]] = {}  # 유형 -> (복수 풀, 단일 풀, 복수로 뽑을 개수)
    for action, n in quota.items():
        pool = pools.get(action, [])
        if n > len(pool):
            raise ValueError(f"{action} 유형은 {len(pool)}개뿐인데 {n}개를 요청했다")
        multi = [q for q in pool if is_multi(q)]
        single = [q for q in pool if not is_multi(q)]
        k = round(n * len(multi) / len(pool)) if n else 0
        k = max(n - len(single), min(k, len(multi)))  # 풀 크기를 넘지 않게
        plan[action] = (multi, single, k)

    sources = {q.source for q in questions}
    for attempt in range(1, max_attempts + 1):
        rng = random.Random(f"{seed}-{attempt}")
        picked: list[tuple[str, Question]] = []
        for action, (multi, single, k) in plan.items():
            picked += [(action, q) for q in rng.sample(multi, k) + rng.sample(single, quota[action] - k)]
        by_source = Counter(q.source for _, q in picked)
        docs = set().union(*(truths[q.id].evidence_book_ids for _, q in picked))
        if all(by_source[s] >= min_per_source for s in sources) and len(docs) >= min_docs:
            break
    else:
        raise ValueError(
            f"조건을 만족하는 선택을 찾지 못했다 (평가 파일별 최소 {min_per_source}개, 근거 문서 최소 {min_docs}가지, {max_attempts}회 시도)"
        )

    return sorted(
        (
            SelectedQuestion(
                id=q.id,
                question=q.question,
                source=q.source,
                expected_action=action,
                reason=f"{ACTION_LABEL.get(action, action)} 유형 {quota[action]}개 중 하나. "
                f"단일·복수 근거 비율을 풀에 맞춘 층화 무작위(seed={seed}-{attempt})",
            )
            for action, q in picked
        ),
        key=lambda s: s.id,
    )


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
    rule: dict | None = None,
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
        "rule": rule,  # 선택 조건(파일별 최소 개수 등). 같은 값으로 다시 뽑으면 같은 목록이 나온다
        "count": len(selected),
        "questions": [s.model_dump() for s in selected],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


DEFAULT_QUOTA = {"answer": 9, "clarify": 3, "abstain": 3}
DEFAULT_SEED = 20261105  # 킥오프일. 바꾸면 선택이 바뀌므로 확정 뒤에는 고정한다.
DEFAULT_MIN_PER_SOURCE = 4  # Basic 기준: 평가 파일 3개에서 각각 4개 이상
DEFAULT_MIN_DOCS = 13  # Basic 기준: 근거로 나오는 문서가 15개 중 13가지 이상


def main(argv: list[str] | None = None) -> None:
    import argparse

    from .loader import load_evaluation

    p = argparse.ArgumentParser(description="일반 평가 질문 선택 -> results/questions.json")
    p.add_argument("--eval-dir", type=Path, default=Path("data/shipping/evaluation"))
    p.add_argument("--answer", type=int, default=DEFAULT_QUOTA["answer"])
    p.add_argument("--clarify", type=int, default=DEFAULT_QUOTA["clarify"])
    p.add_argument("--abstain", type=int, default=DEFAULT_QUOTA["abstain"])
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--min-per-source", type=int, default=DEFAULT_MIN_PER_SOURCE, help="평가 파일마다 최소 몇 개")
    p.add_argument("--min-docs", type=int, default=DEFAULT_MIN_DOCS, help="근거 문서가 최소 몇 가지")
    p.add_argument("--out", type=Path, default=Path("results/questions.json"))
    args = p.parse_args(argv)

    quota = {"answer": args.answer, "clarify": args.clarify, "abstain": args.abstain}
    questions, truths = load_evaluation(args.eval_dir)
    selected = select_questions(
        questions, truths, quota, seed=args.seed, min_per_source=args.min_per_source, min_docs=args.min_docs
    )
    pool = {a: sum(1 for t in truths.values() if t.expected_action == a) for a in quota}
    rule = {"min_per_source": args.min_per_source, "min_docs": args.min_docs}
    path = write_selection(selected, quota, seed=args.seed, out_path=args.out, pool_size=pool, rule=rule)
    print(f"{len(selected)}개 선택: {path}")


if __name__ == "__main__":
    main()
