import threading
import time

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from src import config

RETRY_STATUS = {502, 503, 504}  # 터널·서버가 잠깐 못 받는 응답. 401(인증)·404(컬렉션 없음)는 다시 해도 같으므로 뺀다
BACKOFF_SEC = 0.5  # 재시도 전 대기. 시도마다 두 배로 늘려 이미 느린 서버에 연속 호출을 퍼붓지 않는다

_client: QdrantClient | None = None
_lock = threading.Lock()  # /query가 스레드풀에서 돌아 첫 요청이 동시에 클라이언트를 열 수 있다


def get_client() -> QdrantClient:
    # 로컬 모드는 폴더를 잠가서 프로세스당 클라이언트가 하나여야 한다
    global _client
    with _lock:
        if _client is None:
            if config.QDRANT_URL:
                _client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=config.QDRANT_TIMEOUT_SEC)
            elif config.QDRANT_PATH is None:
                _client = QdrantClient(":memory:")
            else:
                config.QDRANT_PATH.mkdir(parents=True, exist_ok=True)
                _client = QdrantClient(path=str(config.QDRANT_PATH))
        return _client


def reset_client() -> None:
    global _client
    with _lock:
        if _client is not None:
            _client.close()
        _client = None


def call(fn, *args, **kwargs):
    """Qdrant 호출 하나를 실행한다. 시간 초과·연결 실패와 502·503·504일 때만 QDRANT_MAX_RETRIES번 다시 시도한다."""
    for attempt in range(config.QDRANT_MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except (ResponseHandlingException, UnexpectedResponse) as e:
            retryable = isinstance(e, ResponseHandlingException) or e.status_code in RETRY_STATUS
            if not retryable or attempt == config.QDRANT_MAX_RETRIES:
                raise
            time.sleep(BACKOFF_SEC * 2**attempt)
