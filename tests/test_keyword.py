from src.search.keyword import Bm25Index, tokenize


def test_tokenize_2gram():
    assert tokenize("예약을") == ["예약", "약을"]
    assert tokenize("20GP") == ["20", "0g", "gp"]  # 소문자
    assert tokenize("a b") == ["ab"]  # 공백 제거
    assert tokenize("가") == ["가"]
    assert tokenize("") == []


def test_josa_still_matches():
    # 띄어쓰기 단위라면 "예약을"과 "예약"이 달라 못 찾는다
    idx = Bm25Index(["예약을 신청한다", "서류를 제출한다"])
    assert idx.top("예약", 5)[0][0] == 0


def test_code_match_and_zero_score_dropped():
    idx = Bm25Index(["장비는 20GP다", "장비는 40GP다", "냉동 컨테이너"])
    top = idx.top("20GP", 5)
    assert top[0][0] == 0
    assert all(s > 0 for _, s in top)
    assert idx.top("zzzz", 5) == []
