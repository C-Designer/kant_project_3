"""모든 LLM 호출의 단일 경로. timeout·재시도·토큰·시간 측정과 Langfuse generation 기록."""

import contextvars
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import openai

from src import config
from src.platform import tracing


@dataclass
class LLMResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None


class LLMError(Exception):
    def __init__(self, message, reason: str, input_tokens=None, output_tokens=None, latency_ms=None):
        super().__init__(message)
        self.reason = reason  # "model_timeout" | "model_error"
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms


class _Usage:
    """알려진 값만 더한다. 한 번도 못 받았으면 None으로 남는다."""

    def __init__(self):
        self.input_tokens = self.output_tokens = self.latency_ms = None

    def add(self, input_tokens=None, output_tokens=None, latency_ms=None) -> None:
        for k, v in (("input_tokens", input_tokens), ("output_tokens", output_tokens), ("latency_ms", latency_ms)):
            if v is not None:
                setattr(self, k, (getattr(self, k) or 0) + v)


_scope: contextvars.ContextVar[_Usage | None] = contextvars.ContextVar("llm_usage", default=None)


@contextmanager
def usage_scope():
    usage = _Usage()
    token = _scope.set(usage)
    try:
        yield usage
    finally:
        _scope.reset(token)


def _build_model(model_name: str):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_name,
        temperature=config.GENERATION_TEMPERATURE,
        timeout=config.LLM_TIMEOUT_SEC,
        max_retries=0,  # 재시도는 call()이 직접 해서 사용량을 합산한다
        api_key=config.env("OPENAI_API_KEY"),
        base_url=config.env("OPENAI_BASE_URL"),
    )


def call(messages: list[dict[str, str]], *, kind: Literal["service", "eval"] = "service") -> LLMResult:
    if kind == "eval":
        if config.EVAL_MODEL is None:
            raise LLMError("평가 모델이 정해지지 않았다", "model_error")
        model_name = config.EVAL_MODEL
        # 서비스 트레이스에 섞이지 않게 새 trace로 연다
        obs = tracing._observe(
            "eval_generate", "generation",
            trace_context={"trace_id": tracing.get_client().create_trace_id()},
            input=messages, model=model_name, user_id=config.TRACE_USER, tags=["eval"],
        )
    else:
        model_name = config.GENERATION_MODEL
        obs = tracing.span("generate", input=messages, as_type="generation", model=model_name)

    in_tok = out_tok = None
    start = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - start) * 1000)

    def finish(**kw):
        scope = _scope.get()
        if kind == "service" and scope is not None:
            scope.add(kw.get("input_tokens"), kw.get("output_tokens"), kw["latency_ms"])

    with obs as gen:
        try:
            model = _build_model(model_name)
        except Exception as e:
            ms = elapsed()
            finish(latency_ms=ms)
            gen.update(level="ERROR", status_message="model_error")
            raise LLMError("모델 초기화 실패", "model_error", latency_ms=ms) from e

        last_reason = "model_error"
        for _ in range(1 + config.LLM_MAX_RETRIES):
            try:
                msg = model.invoke(messages)
            except Exception as e:
                last_reason = "model_timeout" if isinstance(e, openai.APITimeoutError) else "model_error"
                continue
            u = getattr(msg, "usage_metadata", None) or {}
            for_in, for_out = u.get("input_tokens"), u.get("output_tokens")
            in_tok = (in_tok or 0) + for_in if for_in is not None else in_tok
            out_tok = (out_tok or 0) + for_out if for_out is not None else out_tok
            ms = elapsed()
            finish(input_tokens=in_tok, output_tokens=out_tok, latency_ms=ms)
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            gen.update(
                output=text,
                usage_details={k: v for k, v in (("input", in_tok), ("output", out_tok)) if v is not None},
            )
            return LLMResult(text, in_tok, out_tok, ms)

        ms = elapsed()
        finish(input_tokens=in_tok, output_tokens=out_tok, latency_ms=ms)
        gen.update(level="ERROR", status_message=last_reason)
        raise LLMError(f"LLM 호출 실패 ({last_reason})", last_reason, in_tok, out_tok, ms)
