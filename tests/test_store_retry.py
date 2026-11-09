"""공용 Qdrant 재시도 규칙을 고정한다(#106). 서버 없이 가짜 함수로 돈다."""

import httpx
import pytest
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from src import config
from src.search import store


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(store.time, "sleep", lambda s: None)


def _status(code):
    return UnexpectedResponse(code, "x", b"", httpx.Headers())


class Flaky:
    """앞의 몇 번은 errors를 차례로 올리고, 그다음부터 성공한다."""

    def __init__(self, *errors):
        self.errors, self.calls = list(errors), 0

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def test_시간_초과_뒤_성공하면_정상_결과():
    fn = Flaky(ResponseHandlingException(httpx.ReadTimeout("timed out")))
    assert store.call(fn) == "ok"
    assert fn.calls == 2


def test_502_503_504도_재시도한다():
    fn = Flaky(_status(502), _status(503))
    assert store.call(fn) == "ok"
    assert fn.calls == 3


def test_계속_실패하면_정해진_횟수만_시도하고_오류를_올린다():
    fn = Flaky(*[ResponseHandlingException(httpx.ReadTimeout("timed out"))] * 10)
    with pytest.raises(ResponseHandlingException):
        store.call(fn)
    assert fn.calls == 1 + config.QDRANT_MAX_RETRIES


@pytest.mark.parametrize("code", [401, 404])
def test_인증_실패와_컬렉션_없음은_재시도하지_않는다(code):
    fn = Flaky(_status(code))
    with pytest.raises(UnexpectedResponse):
        store.call(fn)
    assert fn.calls == 1
