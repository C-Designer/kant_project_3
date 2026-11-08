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

import re
from itertools import accumulate
from pathlib import Path

from pypdf import PdfReader

from src.contracts import ChunkMeta, book_id_from_file_name


# --- 청킹 실험용 스위치. compare_models.py가 바꿔 가며 비교한다. 기본값이 지금 동작이다. ---
# 비교가 끝나면 이긴 값만 남기고 나머지 선택지 코드는 지운다.
JOIN_WITH = ""  # 줄 꺾임을 지울 때 대신 넣는 글. "" = 그냥 지움, " " = 공백으로 바꿈
DOC_CONTEXT_FORMAT = "title_dept"  # 첫 줄 내용: "title_dept" 제목+부서 / "title" 제목만 / "dept" 부서만
SPLIT_MODE = "balanced"  # 긴 쪽 분할: "balanced" 균등 / "greedy" 앞에서부터 채우기
PARAGRAPH_MODE = "off"  # 문단 단위: "off" 안 씀 / "pack" 문단 경계에서 균등하게 묶음 / "one" 문단 하나 = 청크 하나
_PARA_SEP = " "  # 쪽 글 안에서 문단 사이를 표시하는 글자. 청크 글에는 남지 않는다


# 역할 : pdf 에서 가져온 텍스트(\n 포함) -> 텍스트(\n 없음)
def _join_lines(text: str) -> str:
    """PDF 줄 꺾임 자리의 줄바꿈을 지운다.

    줄바꿈이 단어 중간("대\\n수")에서 생기면 단어가 갈라져 키워드 검색이 못 찾는다.
    지우면 단어 사이의 줄바꿈은 붙지만("예약을\\n신청"), 키워드 검색을 글자 단위로
    비교하면 붙은 단어도 찾을 수 있다. 맞는 선택인지는 Hit@k로 나중에 검증한다.
    """
    return text.replace("\n", JOIN_WITH)


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
        first = {
            "title_dept": f"{title} (담당: {department})",
            "title": title,
            "dept": f"담당: {department}",
        }[DOC_CONTEXT_FORMAT]
        return f"{first}\n{subtitle}\n{body}".strip()
    return f"{subtitle}\n{body}".strip()


def _layout_paragraphs(layout_text: str, book_id: str, page_no: int, total: int) -> list[str] | None:
    """layout 모드로 뽑은 글에서 본문 문단 목록을 만든다. 문단 사이에는 빈 줄이 남는다.

    기본 모드는 이 빈 줄을 지워서 문단 경계를 알 수 없다. 구조가 예상과 다르면 None.
    """
    groups: list[list[str]] = []
    cur: list[str] = []
    for line in layout_text.split("\n"):
        s = line.strip()
        if s:
            cur.append(s)
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    # 머리말 / 제목 / 소제목 / 본문 문단들 / 꼬리말
    if len(groups) < 5 or len(groups[1]) != 1 or len(groups[2]) != 1:
        return None
    if groups[0] != [groups[0][0]] or not groups[0][0].startswith(f"{book_id} | "):
        return None
    if groups[-1] != [f"{page_no} / {total}"]:
        return None
    return [JOIN_WITH.join(g) for g in groups[3:-1]]


def _cut_body(body: str, paragraphs: list[str]) -> list[str] | None:
    """layout에서 얻은 문단 경계를 기본 모드로 뽑은 본문에 옮겨 문단 목록을 만든다.

    layout 모드는 줄 끝 공백을 지워서 글이 조금 다르므로, 글은 기본 모드 본문에서 가져오고
    layout에서는 "몇 번째 글자에서 문단이 끝나는지"만 빌린다. 공백을 뺀 글자가 같을 때만 쓴다.
    """
    if "".join(paragraphs).replace(" ", "") != body.replace(" ", ""):
        return None
    out: list[str] = []
    pos = 0
    for p in paragraphs:
        start, need = pos, len(p.replace(" ", ""))
        while need:  # 공백이 아닌 글자를 need개 지날 때까지 나아간다
            need -= body[pos] != " "
            pos += 1
        out.append(body[start:pos].strip())
    return out


def extract_pages(
    pdf_path: Path | str, include_doc_context: bool = True
) -> list[tuple[int, str]]:
    """PDF 한 권을 읽어 쪽마다 정리한 글을 [(쪽 번호, 글)]로 돌려준다. 첫 쪽 = 1.

    index.py가 부르는 뼈대의 형태다. 쪽 정리(_clean_page)가 여기서 일어난다.
    """
    # 매개변수 : include_doc_context (bool)
    # True: 청크 첫 줄에 "문서 제목 (담당: 부서)"를 붙인다 (문서 주제를 검색에 반영)
    # False: 소제목과 본문만 남긴다 (Hit@k·Recall@k 비교용)
    pdf_path = Path(pdf_path)
    # 파일 이름에서 확장자를 뺀 부분 (SB01.pdf -> SB01 : book_id)
    book_id = book_id_from_file_name(pdf_path.name)
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    pages: list[tuple[int, str]] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = _clean_page(
            page.extract_text() or "", book_id, page_no, total, include_doc_context
        )
        if text and PARAGRAPH_MODE != "off":
            paragraphs = _layout_paragraphs(
                page.extract_text(extraction_mode="layout") or "", book_id, page_no, total
            )
            *head, body = text.split("\n")
            cut = _cut_body(body, paragraphs) if paragraphs else None
            if cut:  # 경계를 옮길 수 있을 때만 쓴다. 아니면 글을 바꾸지 않는다.
                text = "\n".join([*head, _PARA_SEP.join(cut)])
        if text:  # 빈 쪽은 만들지 않는다
            pages.append((page_no, text))
    return pages


# E5 계열은 한 번에 512토큰까지만 읽고 넘는 뒷부분은 임베딩에 반영되지 않는다.
# Basic 청크는 글자 수 ÷ 토큰 수가 평균 1.93이라, 글자 수 상한을 두고 넘는 쪽만 나눈다.
# 토크나이저로 재서 정한 값이고, 모델이나 청킹이 바뀌면 다시 잰다.
MAX_CHUNK_CHARS = 900

# 한 쪽을 나눌 때 앞 조각의 끝 문장들을 다음 조각 앞에 겹쳐 붙일 글자 수 상한. 0이면 겹치지 않는다.
# 문장 단위로 붙이므로 실제 겹침은 이 값 이하다. 효과는 Hit@k·Recall@k로 검증 전이다 (잠정).
CHUNK_OVERLAP_CHARS = 0

# 문장 끝: "다." 또는 "요."로 끝나는 곳. 마침표가 든 이메일 주소(a@b.example) 안에서는 끊지 않는다.
_SENTENCE_END = re.compile(r"(?<=[다요]\.)")


def _sentences(body: str, limit: int) -> list[str]:
    """body를 문장 끝에서 끊은 목록. 한 문장이 limit보다 길면 글자 수로 강제로 자른다."""
    sentences: list[str] = []
    for sentence in _SENTENCE_END.split(body):
        while len(sentence) > limit:
            sentences.append(sentence[:limit])
            sentence = sentence[limit:]
        if sentence:
            sentences.append(sentence)
    return sentences


def _split_body(body: str, limit: int) -> list[str]:
    """body를 문장 끝에서 끊어 limit자 이하의 비슷한 크기 조각들로 나눈다. 글은 하나도 버리지 않는다."""
    return _pack(_sentences(body, limit), limit)


def _pack(sentences: list[str], limit: int) -> list[str]:
    """덩어리(문장이나 문단)를 이어 붙여 limit자 이하의 비슷한 크기 조각들로 묶는다.

    앞에서부터 꽉 채우면 마지막 조각이 아주 짧게 남는다. 그래서 조각 개수 n을 먼저 정하고,
    k번째 끊는 자리를 "전체 길이 × k/n"에 가장 가까운 덩어리 끝으로 고른다.
    """
    if SPLIT_MODE == "greedy":  # 앞에서부터 한도까지 채우고 넘으면 새 조각
        pieces, cur = [], ""
        for s in sentences:
            if cur and len(cur) + len(s) > limit:
                pieces.append(cur)
                cur = ""
            cur += s
        return pieces + [cur] if cur else pieces
    text = "".join(sentences)  # body와 같은 글
    ends = list(accumulate(len(s) for s in sentences))  # 각 문장이 끝나는 위치
    total = len(text)

    n = max(1, -(-total // limit))  # 조각 개수. 올림 나눗셈
    while True:
        cuts: list[int] = []
        prev = 0
        for k in range(1, n):
            candidates = [e for e in ends if prev < e < total]  # 앞 끊는 자리 뒤의 문장 끝들
            if not candidates:
                break
            ideal = total * k / n
            prev = min(candidates, key=lambda e: abs(e - ideal))
            cuts.append(prev)
        bounds = [0, *cuts, total]
        pieces = [text[a:b] for a, b in zip(bounds, bounds[1:])]
        if all(len(p) <= limit for p in pieces):
            return pieces
        n += 1  # 한도를 넘는 조각이 있으면 개수를 하나 늘려 다시 나눈다


def _overlap_tail(piece: str, limit: int) -> str:
    """piece의 끝에서 문장 단위로 limit자 이하만큼 가져온다. limit이 0이면 빈 글."""
    tail = ""
    for sentence in reversed(_SENTENCE_END.split(piece)):
        if len(tail) + len(sentence) > limit:
            break
        tail = sentence + tail
    return tail


def _split_paragraphs(text: str, limit: int) -> list[str]:
    """문단 경계가 표시된 쪽(_PARA_SEP)을 PARAGRAPH_MODE에 따라 나눈다. 머리 줄은 모든 조각 앞에 붙인다.

    one:  문단 하나 = 청크 하나. 한 문단이 한도를 넘으면 문장 끝에서 나눈다.
    pack: 문단 경계에서만 끊되 limit자 이하로 비슷한 크기로 묶는다. 쪽 전체가 한도 안이면 한 청크.
    """
    *head_lines, body = text.split("\n")
    head = "".join(line + "\n" for line in head_lines)
    room = limit - len(head)
    paragraphs = body.split(_PARA_SEP)
    if PARAGRAPH_MODE == "one":
        pieces: list[str] = []
        for p in paragraphs:
            pieces += [p] if len(p) <= room else _split_body(p, room)
        return [head + p for p in pieces]
    if len("\n".join(paragraphs)) <= room:
        return [head + "\n".join(paragraphs)]
    units: list[str] = []
    for i, p in enumerate(paragraphs):
        tail = "\n" if i < len(paragraphs) - 1 else ""  # 문단 사이는 줄바꿈으로 이음
        if len(p) + len(tail) <= room:
            units.append(p + tail)
        else:  # 한 문단이 한도를 넘으면 문장 단위로 쪼갠다
            sub = _sentences(p, room)
            sub[-1] += tail
            units += sub
    return [head + piece.rstrip("\n") for piece in _pack(units, room)]


def _split_page(text: str, limit: int) -> list[str]:
    """한 쪽의 글이 limit자를 넘으면 나눈다. 머리 줄(제목·부서, 소제목)은 모든 조각 앞에 붙인다.

    _clean_page의 결과는 "머리 줄들 + 본문 한 줄" 모양이라 마지막 줄이 본문이다.
    """
    if _PARA_SEP in text:
        return _split_paragraphs(text, limit)
    if len(text) <= limit:
        return [text]
    *head_lines, body = text.split("\n")
    head = "".join(line + "\n" for line in head_lines)
    overlap = CHUNK_OVERLAP_CHARS
    # 겹치는 글이 앞에 붙어도 한 조각이 limit자를 넘지 않게 그만큼 본문 한도를 줄인다
    pieces = _split_body(body, limit - len(head) - overlap)
    out = [head + pieces[0]]
    for prev, cur in zip(pieces, pieces[1:]):
        out.append(head + _overlap_tail(prev, overlap) + cur)
    return out


def chunk_pages(
    file_name: str, pages: list[tuple[int, str]], *, size: int, overlap: int
) -> list[tuple[str, ChunkMeta]]:
    """쪽마다 청크를 만든다. MAX_CHUNK_CHARS 이하면 한 쪽 = 청크 하나, 넘으면 문장 끝에서 나눈다.

    size와 overlap은 index.py가 넘기는 뼈대의 인자라 받기만 하고 쓰지 않는다.
    config의 CHUNK_SIZE·CHUNK_OVERLAP 정리는 #14에서 config.py를 고칠 때 함께 한다.
    """
    book_id = book_id_from_file_name(file_name)
    out: list[tuple[str, ChunkMeta]] = []
    for page, text in pages:
        for n, piece in enumerate(_split_page(text, MAX_CHUNK_CHARS), start=1):
            meta = ChunkMeta(
                book_id=book_id,
                file_name=file_name,
                page=page,
                chunk_id=f"{book_id}-p{page}-c{n}",
            )
            out.append((piece, meta))
    return out
