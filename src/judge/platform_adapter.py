"""judge가 platform을 쓰는 유일한 창구. judge의 다른 코드는 platform을 직접 부르지 않는다.

- AI 호출: 팀 `platform.llm.call(kind="eval")`. 평가 호출은 서비스 사용량과 섞이지 않는 별도 트레이스로 남는다.
- 점수 기록: 팀 `platform.tracing.record_score`.

개발용 스위치: 환경 변수 `JUDGE_LLM=local`이면 `src/judge/local_llm.py`(각자 PC에만 있는 파일, 커밋 안 됨)를 쓴다.
platform 호출이 막혀 있을 때 실제 채점 시험을 하기 위한 우회이고, 이 파일에는 SDK 직접 호출이 없다.
"""

from __future__ import annotations

import os
from typing import Literal

from src.platform import llm as _llm
from src.platform import tracing as _tracing
from src.platform.llm import LLMResult  # judge가 쓰는 호출 결과 모양: text, input_tokens, output_tokens, latency_ms

__all__ = ["LLMResult", "llm_call", "record_score"]


def llm_call(messages: list[dict[str, str]], *, kind: Literal["service", "eval"] = "eval") -> LLMResult:
    if os.environ.get("JUDGE_LLM") == "local":
        from src.judge import local_llm  # 개발용. 없으면 ImportError로 바로 알린다

        return local_llm.call(messages)
    return _llm.call(messages, kind=kind)


def record_score(request_id: str, name: str, value: float | None, comment: str | None = None) -> None:
    """점수를 Langfuse 트레이스에 붙인다. 기록 실패는 platform이 삼킨다(요청을 깨지 않음)."""
    _tracing.record_score(request_id, name, value, comment)
