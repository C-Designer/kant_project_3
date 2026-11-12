"""EXP-0002 로컬 전용 색인. 실행: PYTHONPATH=. uv run python -m scripts.exp_index.

EXP_INDEX_DIR은 작업 폴더 안의 아직 없는 경로여야 한다. 모델은 로컬 캐시에서 CPU로 읽는다.
max_tokens/over_512는 passage 접두사·특수 토큰을 포함한, 잘리기 전 임베딩 입력 기준이다.
"""

import json
import os
from pathlib import Path

# config의 load_dotenv가 실험 밖 설정을 읽지 않게 한다.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def _index_dir(raw: str | None, root: Path, data: Path) -> Path:
    if not raw:
        raise RuntimeError("EXP_INDEX_DIR에 새 로컬 폴더를 지정해야 한다")
    path = Path(raw).resolve()
    if not path.is_relative_to(root.resolve()) or path.is_relative_to(data.resolve()):
        raise RuntimeError("색인은 작업 폴더 안, data 밖에만 만든다")
    if path.exists() or Path(raw).is_symlink():
        raise RuntimeError("EXP_INDEX_DIR은 아직 없는 새 폴더여야 한다")
    return path


def main() -> None:
    from src import config

    if config.QDRANT_URL is not None:
        raise RuntimeError("공용 Qdrant는 쓰지 않는다")
    destination = _index_dir(os.environ.get("EXP_INDEX_DIR"), config.ROOT, config.DATA_DIR)

    from scripts.exp_config import apply

    apply()
    if config.QDRANT_URL is not None:
        raise RuntimeError("공용 Qdrant는 쓰지 않는다")
    config.QDRANT_PATH = destination
    config.INGEST_REPORT_PATH = destination / "ingest-report.json"

    from sentence_transformers import SentenceTransformer
    from src.search import embed, index, store

    if not any(config.DOCUMENTS_DIR.glob("*.pdf")):
        raise RuntimeError("색인할 PDF가 없다")
    if store._client is not None:
        raise RuntimeError("이미 열린 Qdrant 클라이언트가 있다. 새 프로세스로 실행한다")
    embed._model = SentenceTransformer(config.EMBEDDING_MODEL, device="cpu", local_files_only=True)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        report = index.build_index()
        index.write_report(report)
        if report["failed"] or not report["chunks"]:
            raise RuntimeError("색인이 불완전하다. ingest-report.json을 확인한다")
        client = store.get_client()
        tokenizer = embed._model.tokenizer
        lengths = []
        offset = None
        while True:
            points, offset = client.scroll(config.COLLECTION, limit=index.BATCH,
                                           offset=offset, with_payload=True, with_vectors=False)
            inputs = [f"passage: {point.payload['text']}" for point in points]
            if inputs:
                lengths.extend(len(ids) for ids in tokenizer(
                    inputs, truncation=False, padding=False, add_special_tokens=True,
                )["input_ids"])
            if offset is None:
                break
        if len(lengths) != report["chunks"]:
            raise RuntimeError("색인 청크 수와 토큰 측정 대상 수가 다르다")
        meta = dict(chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP,
                    n_chunks=len(lengths), embedding_model=config.EMBEDDING_MODEL,
                    collection=config.COLLECTION, max_tokens=max(lengths),
                    over_512=sum(n > 512 for n in lengths))
        (destination / "index_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    finally:
        store.reset_client()


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(dir=Path(__file__).resolve().parent.parent) as temporary:
        root = Path(temporary)
        assert _index_dir(str(root / "new"), root, root / "data") == root / "new"
        for invalid in (None, str(root), str(root.parent / "outside"), str(root / "data" / "new")):
            try:
                _index_dir(invalid, root, root / "data")
            except RuntimeError:
                pass
            else:
                raise AssertionError("안전하지 않은 색인 경로를 거부해야 한다")
    print("exp_index self-check: PASS")
    main()
