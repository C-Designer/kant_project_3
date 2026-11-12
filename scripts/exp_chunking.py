"""EXP-0002: 쪽 안에서만 글자 수 overlap을 적용한다."""

from src.contracts import ChunkMeta, book_id_from_file_name
from src.search.chunking import _split_body, chunk_pages as _original_chunk_pages


def chunk_pages(
    file_name: str, pages: list[tuple[int, str]], *, size: int, overlap: int
) -> list[tuple[str, ChunkMeta]]:
    """머리 줄은 유지하고 본문 앞에 이전 본문 끝을 붙인다. size는 머리·겹침 포함.

    이전 본문이 overlap보다 짧으면 그 본문 전체만 붙인다. 다른 쪽에서는 가져오지 않는다.
    """
    if overlap == 0:
        return _original_chunk_pages(file_name, pages, size=size, overlap=0)
    if not 0 < overlap < size:
        raise ValueError("0 < overlap < size여야 한다")
    if len({page for page, _ in pages}) != len(pages):
        raise ValueError("쪽 번호가 중복되면 chunk_id가 겹친다")
    book_id = book_id_from_file_name(file_name)
    out: list[tuple[str, ChunkMeta]] = []
    for page, text in pages:
        pieces = [text]
        if len(text) > size:
            *head_lines, body = text.split("\n")
            head = "".join(line + "\n" for line in head_lines)
            room = size - len(head) - overlap
            if room <= 0:
                raise ValueError("머리 줄과 overlap 뒤에 본문 공간이 없다")
            bodies = _split_body(body, room)
            pieces = []
            previous = ""
            for part in bodies:
                current = previous[-overlap:] + part
                pieces.append(head + current)
                previous = current
        for n, piece in enumerate(pieces, start=1):
            out.append((piece, ChunkMeta(
                book_id=book_id, file_name=file_name, page=page,
                chunk_id=f"{book_id}-p{page}-c{n}",
            )))
    return out


if __name__ == "__main__":
    pages = [(p, f"제목 {p}\n소제목\n" + "".join(
        f"{p}쪽 {i:03}번째 예약 내용을 확인합니다." for i in range(60)
    )) for p in (1, 2)]
    assert chunk_pages("SB01.pdf", pages, size=600, overlap=0) == (
        _original_chunk_pages("SB01.pdf", pages, size=600, overlap=0)
    )
    chunks = chunk_pages("SB01.pdf", pages, size=600, overlap=100)
    assert len({m.chunk_id for _, m in chunks}) == len(chunks)
    for page, original in pages:
        same_page = [(t, m) for t, m in chunks if m.page == page]
        bodies = [t.rsplit("\n", 1)[-1] for t, _ in same_page]
        assert len(bodies) > 1
        assert all(a[-100:] == b[:100] for a, b in zip(bodies, bodies[1:]))
        assert bodies[0] + "".join(b[100:] for b in bodies[1:]) == original.rsplit("\n", 1)[-1]
        assert all(len(t) <= 600 and m.book_id == "SB01" and m.file_name == "SB01.pdf"
                   and m.chunk_id == f"SB01-p{page}-c{n}"
                   for n, (t, m) in enumerate(same_page, 1))
    assert chunk_pages("SB01.pdf", [(1, "짧은 쪽")], size=600, overlap=100)[0][0] == "짧은 쪽"
    # 머리 줄 없는 쪽에서도 실제 청크의 끝과 시작이 일치해야 한다.
    plain = chunk_pages("SB01.pdf", [(1, pages[0][1].rsplit("\n", 1)[-1])], size=600, overlap=100)
    assert all(a[-100:] == b[:100] for (a, _), (b, _) in zip(plain, plain[1:]))
    for size, overlap, sample in [(100, 100, pages), (600, -1, pages),
                                  (600, 100, [pages[0], pages[0]]),
                                  (10, 5, [(1, "긴 머리말입니다\n본문입니다")])]:
        try:
            chunk_pages("SB01.pdf", sample, size=size, overlap=overlap)
        except ValueError:
            pass
        else:
            raise AssertionError("잘못된 한도를 거부해야 한다")
    print("exp_chunking self-check: PASS")
