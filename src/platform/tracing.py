"""Langfuse 트레이스 진입점. 추적 오류는 요청을 절대 깨지 않는다."""

import contextvars
import logging
from contextlib import ExitStack, contextmanager

from langfuse import Langfuse, propagate_attributes

from src.answer import masking

log = logging.getLogger(__name__)

_hide_pii: contextvars.ContextVar[bool] = contextvars.ContextVar("hide_pii", default=False)


def _mask(*, data, **kwargs):
    # hide_pii() 안에서만 동작한다. Langfuse에 기록되는 값만 바꾸고 모델에 가는 값은 그대로다
    return masking.hide(data) if _hide_pii.get() else data


@contextmanager
def hide_pii():
    """사용자가 마스킹 해제에 동의한 요청: 원문은 모델에 가고, 기록에서는 다시 가린다."""
    token = _hide_pii.set(True)
    try:
        yield
    finally:
        _hide_pii.reset(token)


def get_client():
    # 키가 없으면 Langfuse가 스스로 no-op 클라이언트가 된다.
    # 공개 키마다 처음 만든 클라이언트의 mask가 프로세스 전체에 쓰여서, 클라이언트 생성을 여기 한 곳에 둔다
    return Langfuse(mask=_mask)


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
def _observe(name: str, as_type: str = "span", trace_context=None, user_id: str | None = None,
             tags: list[str] | None = None, **kwargs):
    stack = ExitStack()
    try:
        if user_id or tags:
            # 루트보다 먼저 열어야 루트와 하위 스팬 모두에 붙는다
            stack.enter_context(propagate_attributes(user_id=user_id, tags=tags))
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


def request_trace(request_id: str, question: str, user_id: str | None, channel: str):
    try:
        ctx = {"trace_id": trace_id_for(request_id)}
    except Exception:
        log.warning("trace id 생성 실패", exc_info=True)
        ctx = None
    return _observe("query", trace_context=ctx, input=question, user_id=user_id, tags=[channel],
                    metadata={"request_id": request_id})


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
