import threading

from qdrant_client import QdrantClient

from src import config

_client: QdrantClient | None = None
_lock = threading.Lock()  # /query가 스레드풀에서 돌아 첫 요청이 동시에 클라이언트를 열 수 있다


def get_client() -> QdrantClient:
    # 로컬 모드는 폴더를 잠가서 프로세스당 클라이언트가 하나여야 한다
    global _client
    with _lock:
        if _client is None:
            if config.QDRANT_URL:
                _client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)
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
