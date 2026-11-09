"""LLM-as-a-Judge 4항목 채점: 지시문 만들기 → AI 호출 → 결과 검사.

흐름
1. build_messages(): 채점 지시문 + 답안 + 문맥 + 정답 기준을 섹션으로 나눠 메시지를 만든다.
2. AI를 부른다 (score.llm_call → platform.llm.call(kind="eval")).
3. parse_judge_output(): 돌아온 글이 약속한 JSON 모양인지 검사한다.
4. 모양이 틀리면 한 번 더 부르고, 그래도 틀리면 네 칸 모두 "평가 불가"로 둔다.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.contracts import GroundTruth, JudgeItem, RunRecord, TokenUsage
from src.judge.rules import JUDGE_ITEMS, LLMCall, sum_usage

PROMPT_VERSION = "judge_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"
MAX_ATTEMPTS = 2  # 처음 1번 + 재시도 1번


class JudgeParseError(ValueError):
    """AI가 약속한 JSON 모양으로 답하지 않았을 때."""


# ---------------------------------------------------------------------------
# 1. 메시지 만들기
# ---------------------------------------------------------------------------


def _format_context(run: RunRecord) -> str:
    if not run.final_context:
        return "(최종 문맥 없음: 모델에 전달된 검색 자료가 없습니다)"
    lines = []
    for c in run.final_context:
        lines.append(f"[{c.source_id}] {c.metadata.book_id} {c.metadata.page}쪽\n{c.text}")
    return "\n\n".join(lines)


def _format_citations(run: RunRecord) -> str:
    if not run.citations:
        return "(인용 없음)"
    return ", ".join(f"{c.source_id}={c.book_id} {c.page}쪽" for c in run.citations)


@lru_cache(maxsize=1)
def _load_prompt() -> str:
    """채점 지시문은 프로그램이 도는 동안 한 번만 읽는다 (실행 도중 파일이 바뀌어 방식마다 다른 지시문이 쓰이는 것도 막는다)."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_messages(run: RunRecord, truth: GroundTruth) -> list[dict]:
    rubric = truth.rubric
    user = f"""[평가 대상]
질문: {run.question}
상태: {run.status}
답변: {run.answer}
판단 이유: {run.reason}
인용: {_format_citations(run)}

[최종 문맥]  ← 서비스가 답변을 만들 때 실제로 본 자료입니다
{_format_context(run)}

[채점 기준]  ← 서비스는 이 내용을 보지 못했습니다
기대 동작: {truth.expected_action}
참고 답변: {truth.reference_answer}
필수 사실: {json.dumps(rubric.get("required_facts", []), ensure_ascii=False)}
금지 주장: {json.dumps(rubric.get("forbidden_claims", []), ensure_ascii=False)}
채점 설명: {rubric.get("grading_notes", "")}
"""
    return [
        {"role": "system", "content": _load_prompt()},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# 2. 결과 검사
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict:
    """```json ... ``` 같은 포장이 있어도 가장 바깥 { ... } 를 꺼낸다."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise JudgeParseError("JSON 객체를 찾지 못함")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise JudgeParseError(f"JSON 해석 실패: {e}") from e


def parse_judge_output(text: str) -> dict[str, JudgeItem]:
    data = _extract_json(text)
    result: dict[str, JudgeItem] = {}
    for item in JUDGE_ITEMS:
        if item not in data or not isinstance(data[item], dict):
            raise JudgeParseError(f"'{item}' 항목 없음")
        score = data[item].get("score")
        reason = str(data[item].get("reason", "")).strip()
        if score not in (0, 1, None) or isinstance(score, bool):
            raise JudgeParseError(f"'{item}' 점수가 0/1/null이 아님: {score!r}")
        if not reason:
            raise JudgeParseError(f"'{item}' 이유가 비어 있음")
        if score is None and not reason.startswith(("해당 없음", "평가 불가")):
            raise JudgeParseError(f"'{item}' null인데 이유가 '해당 없음/평가 불가'로 시작하지 않음")
        result[item] = JudgeItem(score=score, reason=reason)
    if result["decision"].score is None:
        raise JudgeParseError("decision은 null이 될 수 없음")
    return result


# ---------------------------------------------------------------------------
# 3. 한 답안 채점
# ---------------------------------------------------------------------------


def judge_one(run: RunRecord, truth: GroundTruth, llm: LLMCall) -> tuple[dict[str, JudgeItem] | None, TokenUsage, str | None]:
    """반환: (네 칸 결과 또는 None, 사용 토큰, 실패 사유 또는 None)."""
    messages = build_messages(run, truth)
    tokens = TokenUsage(input=0, output=0)
    last_error = None
    for _ in range(MAX_ATTEMPTS):
        try:
            res = llm(messages)
        except Exception as e:  # 호출 자체 실패 (timeout 등)
            last_error = f"채점 호출 실패: {type(e).__name__}"
            tokens = TokenUsage(input=None, output=None)  # 실패한 호출의 사용량은 알 수 없음
            continue
        tokens = sum_usage(tokens, TokenUsage(input=res.input_tokens, output=res.output_tokens))
        try:
            return parse_judge_output(res.text), tokens, None
        except JudgeParseError as e:
            last_error = f"채점 결과 형식 오류: {e}"
    return None, tokens, last_error
