"""청킹 규칙을 고정한다. PDF 없이 문자열만으로 돌아간다."""

from src.search.chunking import _clean_page, _join_lines

RAW = (
    "SB01 | 예약지원팀\n"
    "가온루트해운 부산–LA 예약 업무 안내\n"
    "예약 신청에 필요한 내용\n"
    "장비 종류와 대\n"
    "수, 일반적인 화물명을 보낸다.\n"
    "2 / 24"
)


def test_join_lines_removes_newline_inside_word():
    assert _join_lines("대\n수") == "대수"


def test_clean_page_drops_book_id_header_and_footer():
    text = _clean_page(RAW, "SB01", 2, 24)
    assert "SB01 |" not in text
    assert "2 / 24" not in text


def test_clean_page_puts_title_and_department_first_then_subtitle_then_body():
    text = _clean_page(RAW, "SB01", 2, 24)
    assert text == (
        "가온루트해운 부산–LA 예약 업무 안내 (담당: 예약지원팀)\n"
        "예약 신청에 필요한 내용\n"
        "장비 종류와 대수, 일반적인 화물명을 보낸다."
    )


def test_clean_page_without_doc_context_has_only_subtitle_and_body():
    text = _clean_page(RAW, "SB01", 2, 24, include_doc_context=False)
    assert text == "예약 신청에 필요한 내용\n장비 종류와 대수, 일반적인 화물명을 보낸다."


def test_clean_page_falls_back_without_losing_text_when_structure_differs():
    raw = "다른 구조의 쪽\n본문 첫 줄\n본문 둘째 줄"
    assert _clean_page(raw, "SB01", 1, 24) == "다른 구조의 쪽본문 첫 줄본문 둘째 줄"
