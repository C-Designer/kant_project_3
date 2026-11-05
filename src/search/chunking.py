"""PDF를 청크로 자른다 (search 영역).

한 쪽 = 청크 하나. 출처 이름표(book_id, page, chunk_id)는
본문 글자가 아니라 파일명과 쪽 순서에서 코드가 붙인다.

Basic 해운 PDF 15개(360쪽)는 모든 쪽이 같은 구조다.
    1줄   "<book_id> | <담당 부서>"   머리말  -> book_id는 이름표로 따로 있어 뺀다. 담당 부서는 남긴다
    2줄   문서 제목                   -> 남긴다. 부서와 함께 "제목 (담당: 부서)" 한 줄로 맨 앞에 둔다
    3줄   소제목 (한 줄)              -> 남긴다, 본문과 줄을 나눈다
    4줄~  본문                        -> 줄 꺾임을 지운다
    끝줄  "<쪽> / <전체 쪽수>"        꼬리말  -> 뺀다
Intermediate·Advanced는 구조가 달라 아직 이 규칙을 쓰지 않는다.
"""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Chunk:
    text: str
    book_id: str  # 파일명에서 .pdf를 뺀 값
    file_name: str
    page: int  # 첫 쪽 = 1
    chunk_id: str  # "<book_id>-p<page>-c<n>"

# 역할 : pdf 에서 가져온 텍스트(\n 포함) -> 텍스트(\n 없음)
def _join_lines(text: str) -> str:
    """PDF 줄 꺾임 자리의 줄바꿈을 지운다.

    줄바꿈이 단어 중간("대\\n수")에서 생기면 단어가 갈라져 키워드 검색이 못 찾는다.
    지우면 단어 사이의 줄바꿈은 붙지만("예약을\\n신청"), 키워드 검색을 글자 단위로
    비교하면 붙은 단어도 찾을 수 있다. 맞는 선택인지는 Hit@k로 나중에 검증한다.
    """
    return text.replace("\n", "")


def _clean_page(
    raw: str,
    book_id: str,
    page_no: int,
    total: int,
    include_doc_context: bool = True,
) -> str:
    """한 쪽의 원문을 "제목 (담당: 부서) / 소제목 / 본문" 모양으로 정리한다.

    book_id 머리말과 꼬리말은 뺀다. 문서 제목과 담당 부서는 문서가 무엇에 관한 것인지
    알려 주므로(예: 정정 공지 문서) 청크 첫 줄에 남긴다. 다만 같은 문서의 쪽들이 서로
    비슷해져 상위 k가 한 문서로 채워지면 Recall@k가 떨어질 수 있다. 그래서
    include_doc_context=False로 끄고 Hit@k·Recall@k를 비교할 수 있게 둔다.

    구조가 예상과 다르면(머리말이나 꼬리말이 맞지 않으면) 글을 버리지 않고
    줄바꿈만 지운 원문을 돌려준다.
    """
    lines = raw.strip().split("\n")

    # basic 문서들 형식 체크
    is_expected = (
        len(lines) >= 5
        and lines[0].startswith(f"{book_id} | ")
        and lines[-1].strip() == f"{page_no} / {total}"
    )
    if not is_expected:
        return _join_lines(raw).strip()

    # 예시
    # lines[0]  = "SB01 | 예약지원팀"
    # lines[1]  = "가온루트해운 부산–LA 예약 업무 안내"
    # lines[2]  = "예약 신청에 필요한 내용"
    # lines[3]~ = 본문 줄들
    # lines[-1] = "2 / 24"          ← -1은 맨 마지막 줄

    department = lines[0].split(" | ", 1)[1]
    title = lines[1]
    subtitle = lines[2]
    body = _join_lines("\n".join(lines[3:-1]))
    if include_doc_context:
        return f"{title} (담당: {department})\n{subtitle}\n{body}".strip()
    return f"{subtitle}\n{body}".strip()


def chunk_pdf(pdf_path: Path, include_doc_context: bool = True) -> list[Chunk]:

    # 매개변수 : include_doc_context (bool)
    # True: 청크 첫 줄에 "문서 제목 (담당: 부서)"를 붙인다 (문서 주제를 검색에 반영)
    # False: 소제목과 본문만 남긴다 (Hit@k·Recall@k 비교용)
    """PDF 한 권을 쪽 단위 청크 목록으로 만든다.

    include_doc_context: True면 청크 첫 줄에 "문서 제목 (담당: 부서)"를 붙인다(기본).
    """
    # 파일 이름에서 확장자를 뺀 부분 (SB01.pdf -> SB01 : book_id)
    book_id = pdf_path.stem
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    chunks: list[Chunk] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = _clean_page(
            page.extract_text() or "", book_id, page_no, total, include_doc_context
        )
        if not text:  # 빈 쪽은 만들지 않는다
            continue
        chunks.append(
            Chunk(
                text=text,
                book_id=book_id,
                file_name=pdf_path.name,
                page=page_no,
                chunk_id=f"{book_id}-p{page_no}-c1",
            )
        )
    return chunks
