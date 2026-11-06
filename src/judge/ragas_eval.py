"""RAGAS Faithfulness: "답안의 주장이 AI가 실제로 본 문맥에 있나?"

입력 (발제 그대로)
- user_input         = 질문
- response           = 생성 답변
- retrieved_contexts = 모델에 실제로 전달한 최종 문맥의 글 (정답을 덧붙이지 않는다)

결과 해석
- 0.0~1.0 숫자      : 정상 채점
- RAGAS가 NaN 반환   : 답변에서 사실 주장을 하나도 못 뽑음 → None + "해당 없음"
- 예외 발생          : 채점을 못 함 → None + "평가 불가"

RAGAS는 안에서 AI를 직접 부르기 때문에, 그 호출이 기록계를 거치도록
RecordedLLM(중간 연결 부품)을 끼워 넣는다.
"""

from __future__ import annotations

import asyncio
import math
import re
from typing import Callable

from src.contracts import RunRecord, TokenUsage
from src.judge.platform_adapter import LLMResult

LLMCall = Callable[[list[dict]], LLMResult]


def _make_recorded_llm(llm: LLMCall):
    """RAGAS가 요구하는 LLM 모양(BaseRagasLLM)으로 우리 호출 함수를 감싼다.

    RAGAS를 설치하지 않은 환경에서도 이 파일을 불러올 수 있도록 안에서 import 한다.
    """
    from langchain_core.outputs import Generation, LLMResult
    from ragas.llms.base import BaseRagasLLM

    class RecordedLLM(BaseRagasLLM):
        def __init__(self) -> None:
            super().__init__()
            self.usage = TokenUsage(input=0, output=0)

        def _call(self, prompt) -> LLMResult:
            res = llm([{"role": "user", "content": prompt.to_string()}])
            u = self.usage
            self.usage = TokenUsage(
                input=None if u.input is None or res.input_tokens is None else u.input + res.input_tokens,
                output=None if u.output is None or res.output_tokens is None else u.output + res.output_tokens,
            )
            return LLMResult(generations=[[Generation(text=res.text)]])

        def generate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None):
            return self._call(prompt)

        async def agenerate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None):
            return await asyncio.to_thread(self._call, prompt)

        def is_finished(self, response) -> bool:
            return True

    return RecordedLLM()


# ---------------------------------------------------------------------------
# 보류·되묻기 문장 처리 규칙
# ---------------------------------------------------------------------------
# 문제: "제공된 자료만으로는 확인할 수 없습니다"를 RAGAS가 사실 주장으로 보고 문맥에서
#       찾다가 못 찾아 0점을 준다. 그러면 올바른 보류도 0점이 된다.
# 규칙: RAGAS가 뽑은 주장 중 아래 세 종류는 "문서 내용"이 아니라 "서비스의 행동이나
#       자료에 대한 말"이므로 채점 대상에서 뺀다.
#   1) 자료가 부족·없음을 말하는 문장  예) "이 자료에는 요율이 없습니다"
#   2) 보류한다는 문장                  예) "답변을 보류합니다"
#   3) 사용자에게 정보를 달라는 문장    예) "장비 종류를 알려 주세요"
#   다 빼고 남는 주장이 없으면 → 해당 없음 (발제: 사실 주장이 없는 응답)
#   남는 주장이 있으면          → 그 주장만으로 채점 (발제: 보류라도 문서 내용을 설명했으면 적용)
# 주의: "이 안내는 일반 건화물 대상입니다"처럼 자료를 언급해도 부족·없음을 말하지 않으면 빼지 않는다.

META_PATTERNS = [
    # 1) 자료·문서·안내·정보·문맥 + 부족/없음/확인 불가
    #    (사이 글자 수를 50까지 허용: "안내자료에는 무료기간, 보관료, 요율 또는 관련 계약 조건이 없습니다")
    r"(자료|문서|안내|정보|문맥|기록)[^.]{0,50}(없|부족|확인할 수 없|알 수 없|판단할 수 없|산출할 수 없|계산할 수 없|어렵)",
    #    "포함되어 있지 않습니다"처럼 '없다' 대신 '않다'로 바꿔 쓴 경우 (11/5 S-DEV-30 재시험에서 발견).
    #    "적용되지 않습니다" 같은 문서 내용까지 빼지 않도록 '담겨 있음'을 뜻하는 말로 한정한다.
    r"(자료|문서|안내|정보|문맥|기록)[^.]{0,50}((포함되어|포함돼|들어|담겨|나와|적혀|제공되어)\s*있지|제공하지|포함하지)\s*않",
    # 2) 보류
    r"(답변|응답|판단|확답)\S*\s*보류|보류합니다|보류해야",
    # 3) 사용자에게 요청
    #    RAGAS는 "알려 주세요"를 "알려 주어야 합니다"로 바꿔 쓰기도 해서 그 형태도 잡는다.
    r"(알려|확인해|보내|말씀해)\s*주(세요|십시오|시기|어야)",
]


def is_meta_statement(statement: str) -> bool:
    return any(re.search(p, statement) for p in META_PATTERNS)


def _make_metric(recorded):
    """RAGAS Faithfulness에 '보류·되묻기 문장 빼기'를 끼운 버전. 뺀 문장은 removed에 남긴다."""
    from ragas.metrics import Faithfulness

    class FaithfulnessWithoutMeta(Faithfulness):
        removed: list = []

        async def _create_statements(self, row, callbacks):
            out = await super()._create_statements(row, callbacks)
            kept = [s for s in out.statements if not is_meta_statement(s)]
            self.removed = [s for s in out.statements if is_meta_statement(s)]
            out.statements = kept
            return out

    return FaithfulnessWithoutMeta(llm=recorded)


def faithfulness(run: RunRecord, llm: LLMCall) -> tuple[float | None, TokenUsage | None, str | None, str | None]:
    """반환: (점수, 사용 토큰, 해당 없음 이유, 평가 불가 이유). 이유 둘 중 하나만 채워지거나 둘 다 None."""
    if not run.answer.strip():
        return None, None, "답변 글이 비어 있음", None
    # 문맥이 비어도 바로 "해당 없음"으로 빼지 않는다.
    # 답변에 주장이 있으면 뒷받침이 없으니 0점이 맞고, 주장이 없을 때만 해당 없음이다.
    # 그 구분은 RAGAS의 주장 추출에 맡기고, 빈 목록 대신 "문맥 없음" 표시 한 줄을 넘긴다.
    contexts = [c.text for c in run.final_context] or ["(검색 자료 없음)"]

    try:
        from ragas import SingleTurnSample
    except ImportError as e:
        return None, None, None, f"RAGAS 미설치: {e}"

    from ragas.run_config import RunConfig

    recorded = _make_recorded_llm(llm)
    # 재시도·timeout은 기록계(platform.llm.call)가 맡는다. RAGAS 자체 재시도(기본 10회)는 끈다.
    recorded.set_run_config(RunConfig(max_retries=1, max_wait=1))
    metric = _make_metric(recorded)
    sample = SingleTurnSample(
        user_input=run.question,
        response=run.answer,
        retrieved_contexts=contexts,
    )
    try:
        score = asyncio.run(metric.single_turn_ascore(sample))
    except Exception as e:
        return None, recorded.usage, None, f"RAGAS 계산 실패: {type(e).__name__}: {e}"

    if score is None or (isinstance(score, float) and math.isnan(score)):
        if metric.removed:
            return None, recorded.usage, f"사실 주장 없음 (보류·자료 부족·되묻기 문장만 있음: {' / '.join(metric.removed)})", None
        return None, recorded.usage, "사실 주장 없음 (RAGAS가 주장을 추출하지 못함)", None
    return float(score), recorded.usage, None, None
