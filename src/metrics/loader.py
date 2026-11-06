"""평가 JSON 로더: 질문(사용자 입력 쪽)과 정답(채점 쪽)을 분리한다.

`Question`만 `run_query()`로 가고, `GroundTruth`는 검색 지표와 judge에만 간다.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from src.contracts import GroundTruth

# 일반 평가 질문 파일(Basic). 보안 질문(security_*)은 platform 담당이라 여기서 읽지 않는다.
EVAL_SETS = ("development", "additional", "expansion_validation")

# 정답 항목에서 GroundTruth 본 필드로 옮기는 키. 나머지는 rubric으로 원본 그대로 둔다.
# evidence_groups는 book_id 목록(evidence_book_ids)으로도 쓰이지만, judge가 원문 대조에 쓰도록
# 원문(quote)·페이지·그룹 구조를 담은 채로 rubric에도 그대로 남긴다.
_TRUTH_FIELDS = {"id", "question", "reference_answer", "expected_action"}


class Question(BaseModel):
    """실행에 쓰는 질문. 정답·근거·기대 동작을 넣지 않는다."""

    id: str
    question: str
    source: str  # 어느 평가 파일에서 왔는지 (development / additional / expansion_validation)


def _read_json(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _existing_sets(eval_dir: Path) -> list[str]:
    eval_dir = Path(eval_dir)
    if not eval_dir.is_dir():
        raise FileNotFoundError(f"평가 폴더가 없다: {eval_dir}")
    return [s for s in EVAL_SETS if (eval_dir / f"{s}_questions.json").exists()]


def flatten_evidence(evidence_groups: list[list[dict]]) -> list[str]:
    """evidence_groups의 모든 book_id를 모아 중복 제거(처음 나온 순서 유지)."""
    seen: dict[str, None] = {}
    for group in evidence_groups:
        for item in group:
            seen.setdefault(item["book_id"], None)
    return list(seen)


def load_questions(eval_dir: Path | str) -> list[Question]:
    eval_dir = Path(eval_dir)
    questions: list[Question] = []
    for name in _existing_sets(eval_dir):
        for item in _read_json(eval_dir / f"{name}_questions.json"):
            questions.append(Question(id=item["id"], question=item["question"], source=name))
    return questions


def _to_truth(item: dict) -> GroundTruth:
    return GroundTruth(
        question_id=item["id"],
        evidence_book_ids=flatten_evidence(item.get("evidence_groups", [])),
        expected_action=item["expected_action"],
        reference_answer=item.get("reference_answer", ""),
        rubric={k: v for k, v in item.items() if k not in _TRUTH_FIELDS},
    )


def load_ground_truth(eval_dir: Path | str) -> list[GroundTruth]:
    eval_dir = Path(eval_dir)
    truths: list[GroundTruth] = []
    for name in _existing_sets(eval_dir):
        truths += [_to_truth(item) for item in _read_json(eval_dir / f"{name}.json")]
    return truths


def load_security(eval_dir: Path | str) -> tuple[list[Question], dict[str, GroundTruth]]:
    """보안 질문(2개)과 정답·공격 정보. 일반 질문과 **분리**해서 읽는다.

    일반 평균·오류율에 섞이지 않게 load_questions/load_evaluation에는 포함하지 않는다.
    실행과 보안 비교는 platform 담당. `attack_text` 등 공격 필드는 rubric에만 두고
    `Question`에는 넣지 않는다(문맥에 따로 붙이지 않는다는 발제 규칙).
    파일이 없으면 ([], {}).
    """
    eval_dir = Path(eval_dir)
    q_path, t_path = eval_dir / "security_questions.json", eval_dir / "security_tasks.json"
    if not (q_path.exists() and t_path.exists()):
        return [], {}
    questions = [Question(id=i["id"], question=i["question"], source="security") for i in _read_json(q_path)]
    truths = {t.question_id: t for t in (_to_truth(i) for i in _read_json(t_path))}
    only_q = sorted({q.id for q in questions} - truths.keys())
    only_t = sorted(truths.keys() - {q.id for q in questions})
    if only_q or only_t:
        raise ValueError(f"보안 질문/정답 id 불일치. 정답 없음: {only_q}, 질문 없음: {only_t}")
    return questions, truths


def load_evaluation(eval_dir: Path | str) -> tuple[list[Question], dict[str, GroundTruth]]:
    """질문 목록과 {question_id: GroundTruth}. 두 쪽의 id가 어긋나면 ValueError."""
    questions = load_questions(eval_dir)
    truths = {g.question_id: g for g in load_ground_truth(eval_dir)}
    question_ids = {q.id for q in questions}
    only_q = sorted(question_ids - truths.keys())
    only_t = sorted(truths.keys() - question_ids)
    if only_q or only_t:
        raise ValueError(f"질문/정답 id 불일치. 정답 없음: {only_q}, 질문 없음: {only_t}")
    return questions, truths
