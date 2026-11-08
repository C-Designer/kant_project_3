"""공용 서비스에 읽기 전용으로 접속한다. 키·응답 본문은 출력하지 않는다."""

import json

from src import config
from src.platform import tracing
from src.search import store


def check_connections() -> dict[str, str]:
    results = {}
    if not config.QDRANT_URL:
        results["qdrant"] = "not_configured: QDRANT_URL"
    else:
        try:
            client = store.get_client()
            results["qdrant"] = (
                "ok" if client.collection_exists(config.COLLECTION) else "collection_missing"
            )
        except Exception as exc:
            results["qdrant"] = f"failed: {type(exc).__name__}"
        finally:
            store.reset_client()

    required = ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    missing = [name for name in required if not config.env(name)]
    if missing:
        results["langfuse"] = "not_configured: " + ", ".join(missing)
    else:
        try:
            results["langfuse"] = "ok" if tracing.get_client().auth_check() else "auth_failed"
        except Exception as exc:
            results["langfuse"] = f"failed: {type(exc).__name__}"
    return results


if __name__ == "__main__":
    results = check_connections()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(value == "ok" for value in results.values()) else 1)
