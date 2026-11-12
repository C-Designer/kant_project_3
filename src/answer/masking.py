"""사용자 질문의 개인정보를 자리표시자(<전화1> 등)로 가리고, 답변에서 원래 값으로 되돌린다.

검색 자료(문맥)는 가리지 않는다. 사용자가 입력하는 것은 질문뿐이고, 자료는 교육용 가상 자료다.
대응표는 요청 하나 안에서만 쓰고 로그·트레이스·파일에 남기지 않는다.
"""

import re

# 영문·숫자에 붙은 값(컨테이너 번호 MSKU1234567 등)은 잡지 않고, 한글 조사가 바로 붙은 값("5678인데")은 잡는다.
# \b를 쓰지 않는 이유: 파이썬에서는 한글도 단어 문자라 "5678인데"의 8과 인 사이를 경계로 보지 않는다.
_L, _R = r"(?<![A-Za-z0-9])", r"(?![A-Za-z0-9])"

# (항목, 패턴). 위에서부터 적용하고, 앞 항목이 차지한 구간은 뒤 항목이 다시 잡지 않는다.
# 패턴에 v 그룹이 있으면 그 부분만 가린다(앞의 단서어는 남긴다).
# shortcut: 이름·직장·주소·민감 정보(의료·재무·법적·정치·종교 등)는 정규식으로 못 잡아 빠져 있다, 실측 후 3·4단계에서 정한다
_RULES: list[tuple[str, re.Pattern[str]]] = [
    # 하이픈 없는 13자리도 잡는다. 바코드(880…) 같은 13자리 숫자도 가려지지만 주민번호가 새는 쪽이 더 나쁘다
    ("주민번호", re.compile(rf"{_L}\d{{6}}-?[1-8]\d{{6}}{_R}")),
    ("카드번호", re.compile(rf"{_L}\d{{4}}([- ]?)\d{{4}}\1\d{{4}}\1\d{{4}}{_R}")),
    ("면허번호", re.compile(rf"{_L}\d{{2}}-\d{{2}}-\d{{6}}-\d{{2}}{_R}")),
    ("이메일", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    # 휴대폰은 붙여 써도 잡고, 유선은 HS 코드(0201100000)와 겹쳐 구분자가 있을 때만 잡는다. 대표번호(1588-…)는 업체 번호라 잡지 않는다
    ("전화", re.compile(
        rf"{_L}(?:(?:\+82[- ]?0?|0)1[016789][- ]?\d{{3,4}}[- ]?\d{{4}}"
        rf"|(?:\+82[- ]?0?|0)(?:2|[3-6][1-5]|70)[- ]\d{{3,4}}[- ]\d{{4}}){_R}"
    )),
    # 업체 사이트 URL은 자료에도 실려 있어 SNS 주소만 잡는다
    ("SNS", re.compile(
        rf"{_L}(?:https?://)?(?:www\.|m\.)?(?:instagram\.com|facebook\.com|x\.com|twitter\.com|threads\.net"
        r"|tiktok\.com|youtube\.com|open\.kakao\.com|blog\.naver\.com)/[A-Za-z0-9._~%/?#=&+-]+"
    )),
    # 운임 표기(@20ft)와 겹쳐 SNS 단서어 뒤의 @아이디만 잡는다
    ("SNS", re.compile(r"(?:인스타|트위터|페이스북|틱톡|스레드|SNS|계정|아이디|DM)[^@\n]{0,10}?(?P<v>@[A-Za-z0-9_.]*[A-Za-z0-9_])", re.I)),
    # 예약번호·B/L 번호와 모양이 같아 단서어 뒤에서만 잡는다. 숫자 10자리 이상이라 날짜(2026-11-12)는 빠진다
    ("계좌", re.compile(rf"(?:계좌|입금)\D{{0,15}}?(?P<v>{_L}(?=(?:\d-?){{10}})\d[\d-]{{8,18}}\d{_R})")),
    ("여권번호", re.compile(rf"여권\D{{0,15}}?(?P<v>{_L}[A-Za-z]{{1,2}}\d{{7,8}}{_R})")),
    ("생년월일", re.compile(
        rf"(?:생년월일|생일|출생)\D{{0,10}}?(?P<v>{_L}(?:\d{{2,4}}[./-]\d{{1,2}}[./-]\d{{1,2}}"
        rf"|\d{{4}}년 ?\d{{1,2}}월 ?\d{{1,2}}일|\d{{6,8}}){_R})"
    )),
    ("생년월일", re.compile(rf"{_L}\d{{2,4}}년생")),
    ("나이", re.compile(rf"{_L}(?:만 ?)?\d{{1,3}} ?(?:세|살)(?![대관금트기])")),  # 3세대, 세관, 세금, 3세트, 21세기 제외
    # "여성의류" 같은 품목명과 겹쳐 자기소개 단서어 뒤에서만 잡는다
    ("성별", re.compile(r"(?:성별|저는|제가|본인은?)[^.?!\n]{0,10}?(?P<v>남성|여성|남자|여자)(?!의류|복|용|전용|친구)")),
]

_PLACEHOLDER = re.compile(r"<\s*([^<>\s\d]+)\s*(\d+)\s*>")

UNMASK_OFFER = (
    "개인정보로 보이는 값을 가린 채로는 답하지 못했습니다. 가린 값을 답변 생성 모델(외부 서비스)에 그대로 보내 "
    "다시 물으려면 같은 질문에 \"unmask\": true를 붙여 다시 요청하세요. 실행 기록에는 가린 값으로 남습니다."
)


def mask(question: str) -> tuple[str, dict[str, str]]:
    """질문 → (가린 질문, {자리표시자: 원래 값}). 같은 값은 같은 자리표시자를 쓴다."""
    spans: list[tuple[int, int, str]] = []
    for kind, pattern in _RULES:
        for m in pattern.finditer(question):
            s, e = m.span("v") if "v" in pattern.groupindex else m.span()
            if all(e <= s2 or s >= e2 for s2, e2, _ in spans):
                spans.append((s, e, kind))
    spans.sort()

    table: dict[str, str] = {}
    seen: dict[tuple[str, str], str] = {}
    counts: dict[str, int] = {}
    out, last = [], 0
    for s, e, kind in spans:
        value = question[s:e]
        key = (kind, re.sub(r"[\s-]", "", value).lower())  # 010-1234-5678과 01012345678은 같은 값
        if key not in seen:
            counts[kind] = counts.get(kind, 0) + 1
            seen[key] = f"<{kind}{counts[kind]}>"
            table[seen[key]] = value  # 처음 나온 표기로 되돌린다
        out += [question[last:s], seen[key]]
        last = e
    out.append(question[last:])
    return "".join(out), table


def restore(text: str, table: dict[str, str]) -> str:
    """자리표시자를 원래 값으로 바꾼다. 공백 차이(<전화 1>)는 허용하고, 대응표에 없는 자리표시자는 그대로 둔다."""
    if not table:
        return text
    return _PLACEHOLDER.sub(lambda m: table.get(f"<{m[1]}{m[2]}>", m[0]), text)


def hide(data):
    """기록용: 문자열·목록·사전 안의 개인정보를 모두 가린다. 모델이 바꿔 쓴 표기(01012345678 → 010-1234-5678)도 잡는다."""
    if isinstance(data, str):
        return mask(data)[0]
    if isinstance(data, list):
        return [hide(x) for x in data]
    if isinstance(data, dict):
        return {k: hide(v) for k, v in data.items()}
    return data
