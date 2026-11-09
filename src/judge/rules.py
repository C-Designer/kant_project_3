"""AI에게 묻지 않고 코드로 정하는 채점 규칙 (docs/evaluation.md "해당 없음 / 평가 불가 / 오류").

핵심 구분
- 0     = 채점했고 틀렸다. 평균에 넣는다.
- None  = 해당 없음(채점할 대상이 없음) 또는 평가 불가(채점을 못 했음). 평균에서 뺀다.
None을 0이나 1로 바꾸는 코드는 이 파일 어디에도 없어야 한다.
"""

from __future__ import annotations

from typing import Callable

from src.contracts import EvalRecord, JudgeItem, RunRecord, TokenUsage
from src.platform.llm import LLMResult  # 호출 결과 모양: text, input_tokens, output_tokens, latency_ms

# "메시지 목록을 주면 LLMResult를 돌려주는 함수". judge·RAGAS·score가 같은 정의를 쓴다.
LLMCall = Callable[[list[dict]], LLMResult]

JUDGE_ITEMS = ("facts", "conditions", "evidence", "decision")


def add_optional(a: int | None, b: int | None) -> int | None:
    """토큰 두 값을 더한다. 한쪽이라도 모르면(None) 합계도 모름(None). 0으로 메우지 않는다.

    토큰 합산 규칙은 이 함수 하나에만 있다 (채점관·RAGAS·답안별 합계가 모두 이것을 쓴다).
    """
    if a is None or b is None:
        return None
    return a + b


def sum_usage(*usages: TokenUsage | None) -> TokenUsage | None:
    """여러 호출의 사용량을 합친다. 합칠 사용량이 하나도 없으면 None(0이 아님)."""
    used = [u for u in usages if u is not None]
    if not used:
        return None
    total = TokenUsage(input=0, output=0)
    for u in used:
        total = TokenUsage(input=add_optional(total.input, u.input), output=add_optional(total.output, u.output))
    return total


def tag(item: str, reason: str) -> str:
    """빈칸 이유에 칸 이름을 붙인다. 예: tag("faithfulness", "사실 주장 없음") → "faithfulness: 사실 주장 없음"."""
    return f"{item}: {reason}"


def precheck(run: RunRecord) -> EvalRecord | None:
    """AI 채점 없이 결론이 나는 답안이면 채점 결과를 바로 돌려준다. 아니면 None.

    서비스 오류(status == "error")인 경우:
    - 판단(decision) = 0  → 답을 못 만들었으니 판단은 실패
    - 나머지 세 칸과 Faithfulness = 평가 불가 → 출력이 없어 확인할 수 없음
    """
    if run.status != "error":
        return None

    reason = f"서비스 오류로 답변 없음 ({run.error or '사유 미기록'})"
    judge = {item: JudgeItem(score=None, reason=f"평가 불가: {reason}") for item in JUDGE_ITEMS}
    judge["decision"] = JudgeItem(score=0, reason=f"서비스 오류로 답변·되묻기·보류 중 어느 것도 하지 못함")
    return EvalRecord(
        question_id=run.question_id,
        retrieval_mode=run.retrieval_mode,
        faithfulness=None,
        judge=judge,
        eval_tokens=None,  # 채점 호출을 안 했으니 사용량도 없음 (0이 아니라 None)
        not_applicable=[],
        unscorable=[tag("faithfulness", reason)] + [tag(i, reason) for i in JUDGE_ITEMS if i != "decision"],
    )


def mean_ignoring_none(values: list[float | int | None]) -> float | None:
    """None은 빼고 평균. 남는 값이 없으면 None (0으로 바꾸지 않음).

    예: [1, 1, 0, None] → (1+1+0)/3 = 0.667
    """
    kept = [v for v in values if v is not None]
    if not kept:
        return None
    return sum(kept) / len(kept)
