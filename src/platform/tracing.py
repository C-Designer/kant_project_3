"""Langfuse 트레이스 진입점. 추적 오류는 요청을 절대 깨지 않는다."""

import logging
from contextlib import ExitStack, contextmanager

from langfuse import get_client as _lf_client

log = logging.getLogger(__name__)


def get_client():
    # 키가 없으면 Langfuse가 스스로 no-op 클라이언트가 된다
    return _lf_client()


def trace_id_for(request_id: str) -> str:
    return get_client().create_trace_id(seed=request_id)


class _Handle:
    """관측 객체를 감싸 update 실패를 삼킨다. obs가 None이면 아무 일도 하지 않는다."""

    def __init__(self, obs=None):
        self._obs = obs

    def update(self, **kwargs) -> None:
        if self._obs is None:
            return
        try:
            self._obs.update(**kwargs)
        except Exception:
            log.warning("tracing update 실패", exc_info=True)


@contextmanager
def _observe(name: str, as_type: str = "span", trace_context=None, **kwargs):
    stack = ExitStack()
    try:
        obs = stack.enter_context(
            get_client().start_as_current_observation(
                name=name, as_type=as_type, trace_context=trace_context, **kwargs
            )
        )
    except Exception:
        log.warning("tracing 시작 실패: %s", name, exc_info=True)
        obs = None
    try:
        yield _Handle(obs)
    finally:
        try:
            stack.close()
        except Exception:
            log.warning("tracing 종료 실패: %s", name, exc_info=True)


def span(name: str, *, input=None, as_type: str = "span", **kwargs):
    return _observe(name, as_type, input=input, **kwargs)


def request_trace(request_id: str, question: str):
    try:
        ctx = {"trace_id": trace_id_for(request_id)}
    except Exception:
        log.warning("trace id 생성 실패", exc_info=True)
        ctx = None
    return _observe("query", trace_context=ctx, input=question, metadata={"request_id": request_id})


def record_score(request_id: str, name: str, value, comment: str | None = None) -> None:
    try:
        get_client().create_score(
            trace_id=trace_id_for(request_id), name=name, value=value, comment=comment
        )
    except Exception:
        log.warning("score 기록 실패", exc_info=True)


def flush() -> None:
    try:
        get_client().flush()
    except Exception:
        log.warning("flush 실패", exc_info=True)
