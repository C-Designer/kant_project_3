"""EXP-0002 실행에 한해 동결 config 값을 주입한다."""

import json
import os
from pathlib import Path

from src import config


def apply() -> dict:
    if config.QDRANT_URL is not None:
        raise RuntimeError("공용 Qdrant는 쓰지 않는다")

    env_to_config = {
        "EXP_CHUNK_SIZE": ("CHUNK_SIZE", int),
        "EXP_CHUNK_OVERLAP": ("CHUNK_OVERLAP", int),
        "EXP_TOPK": ("K", int),
        "EXP_CONTEXT_TOKENS": ("CONTEXT_TOKEN_LIMIT", int),
        "EXP_RERANK_CANDIDATES": ("RERANK_CANDIDATES", int),
    }
    values = {}
    for env_name, (config_name, cast) in env_to_config.items():
        raw = os.environ.get(env_name)
        if raw is not None:
            values[config_name] = cast(raw)

    index_dir = os.environ.get("EXP_INDEX_DIR")
    if index_dir:
        config.QDRANT_PATH = Path(index_dir)
        metadata_path = config.QDRANT_PATH / "index_meta.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            for key, env_name in (("chunk_size", "EXP_CHUNK_SIZE"), ("chunk_overlap", "EXP_CHUNK_OVERLAP")):
                expected = int(os.environ[env_name]) if os.environ.get(env_name) is not None else getattr(config, env_to_config[env_name][0])
                if metadata.get(key) != expected:
                    raise RuntimeError(f"색인 설정 불일치: {key}")

    for name, value in values.items():
        setattr(config, name, value)
    overlap = config.CHUNK_OVERLAP
    if overlap > 0:
        from src.search import chunking
        from scripts import exp_chunking
        chunking.chunk_pages = exp_chunking.chunk_pages

    return {
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
        "topk": config.K,
        "context_tokens": config.CONTEXT_TOKEN_LIMIT,
        "rerank_candidates": config.RERANK_CANDIDATES,
        "index_dir": str(config.QDRANT_PATH) if config.QDRANT_PATH is not None else None,
        "label": os.environ.get("EXP_LABEL") or "baseline",
    }


if __name__ == "__main__":
    old = {name: getattr(config, name) for name in ("CHUNK_SIZE", "CHUNK_OVERLAP", "K", "CONTEXT_TOKEN_LIMIT", "RERANK_CANDIDATES", "QDRANT_PATH", "QDRANT_URL")}
    env_names = ("EXP_CHUNK_SIZE", "EXP_CHUNK_OVERLAP", "EXP_TOPK", "EXP_CONTEXT_TOKENS", "EXP_RERANK_CANDIDATES", "EXP_INDEX_DIR", "EXP_LABEL")
    saved_env = {name: os.environ.get(name) for name in env_names}
    try:
        os.environ.update(EXP_CHUNK_SIZE="600", EXP_CHUNK_OVERLAP="0", EXP_TOPK="3", EXP_CONTEXT_TOKENS="1000", EXP_RERANK_CANDIDATES="10")
        config.QDRANT_URL = None
        got = apply()
        assert (got["chunk_size"], got["topk"], got["context_tokens"], got["rerank_candidates"]) == (600, 3, 1000, 10)
        config.QDRANT_URL = "local-test"
        try:
            apply()
            raise AssertionError("공용 URL을 거부하지 않음")
        except RuntimeError as exc:
            assert str(exc) == "공용 Qdrant는 쓰지 않는다"
        config.QDRANT_URL = None
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "index_meta.json").write_text('{"chunk_size": 900, "chunk_overlap": 0}', encoding="utf-8")
            os.environ["EXP_INDEX_DIR"] = tmp
            try:
                apply()
                raise AssertionError("불일치 메타데이터를 거부하지 않음")
            except RuntimeError as exc:
                assert "설정 불일치" in str(exc)
    finally:
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        for name, value in old.items():
            setattr(config, name, value)
