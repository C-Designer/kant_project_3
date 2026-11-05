import argparse
import json
import uuid
from pathlib import Path

from qdrant_client.models import (
    Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, VectorParams,
)

from src import config
from src.search import chunking, embed, store

BATCH = 64


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def build_index(
    documents_dir: Path | str | None = None, *, only: str | None = None, recreate: bool = True
) -> dict:
    # evaluation/ 같은 하위 폴더를 읽지 않도록 glob은 바로 아래만 본다
    docs = Path(documents_dir or config.DOCUMENTS_DIR)
    pdfs = sorted(p for p in docs.glob("*.pdf") if only is None or p.name == only)
    client = store.get_client()
    exists = client.collection_exists(config.COLLECTION)
    report = {"documents": 0, "pages": 0, "chunks": 0, "failed": []}
    first_vec = True

    for pdf in pdfs:
        try:
            pages = chunking.extract_pages(pdf)
            chunks = chunking.chunk_pages(
                pdf.name, pages, size=config.CHUNK_SIZE, overlap=config.CHUNK_OVERLAP
            )
            if not chunks:
                raise ValueError("추출된 텍스트가 없음")
            vectors = []
            for i in range(0, len(chunks), BATCH):
                vectors += embed.embed_passages([t for t, _ in chunks[i : i + BATCH]])
        except Exception as e:  # 한 파일 실패가 나머지를 막지 않는다
            report["failed"].append({"file": pdf.name, "reason": f"{type(e).__name__}: {e}"})
            continue

        if first_vec:
            if recreate and exists:
                client.delete_collection(config.COLLECTION)
                exists = False
            if not exists:
                client.create_collection(
                    config.COLLECTION,
                    vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
                )
            first_vec = False
        if not recreate:  # 같은 파일 재색인 시 중복 방지
            client.delete(
                config.COLLECTION,
                FilterSelector(filter=Filter(must=[FieldCondition(key="file_name", match=MatchValue(value=pdf.name))])),
            )
        points = [
            PointStruct(
                id=point_id(m.chunk_id), vector=v, payload={"text": t, **m.model_dump()}
            )
            for (t, m), v in zip(chunks, vectors)
        ]
        client.upsert(config.COLLECTION, points)
        report["documents"] += 1
        report["pages"] += len(pages)
        report["chunks"] += len(chunks)
    return report


def write_report(report: dict) -> None:
    path = config.INGEST_REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="이 파일 하나만 색인 (예: FB01.pdf)")
    args = ap.parse_args()
    rep = build_index(only=args.only, recreate=args.only is None)
    write_report(rep)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
