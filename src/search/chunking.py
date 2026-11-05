from pathlib import Path

from pypdf import PdfReader

from src.contracts import ChunkMeta, book_id_from_file_name


def extract_pages(pdf_path: Path | str) -> list[tuple[int, str]]:
    pages = []
    for i, page in enumerate(PdfReader(pdf_path).pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((i, text))
    return pages


def chunk_pages(
    file_name: str, pages: list[tuple[int, str]], *, size: int, overlap: int
) -> list[tuple[str, ChunkMeta]]:
    if overlap >= size:
        raise ValueError("overlap은 size보다 작아야 한다")
    book_id = book_id_from_file_name(file_name)
    out = []
    for page, text in pages:
        # shortcut: 글자 수 고정 분할이라 표·문장이 끊길 수 있음, 청킹 개선(#13) 때 교체
        starts = range(0, len(text), size - overlap)
        for n, s in enumerate(starts, start=1):
            piece = text[s : s + size]
            meta = ChunkMeta(
                book_id=book_id, file_name=file_name, page=page,
                chunk_id=f"{book_id}-p{page}-c{n}",
            )
            out.append((piece, meta))
            if s + size >= len(text):
                break
    return out
