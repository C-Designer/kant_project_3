"""발제 규칙 "개인정보는 기록에 남기지 않는다"를 지키는 질문 마스킹 규칙을 고정한다."""

import pytest

from src.answer import masking
from src.platform import tracing


@pytest.mark.parametrize(
    "question, kind",
    [
        ("제 번호는 010-1234-5678인데요", "전화"),
        ("01012345678로 연락 주세요", "전화"),
        ("+82 10-1234-5678로 주세요", "전화"),
        ("사무실은 02-123-4567입니다", "전화"),
        ("test.user@example.com으로 보내 주세요", "이메일"),
        ("주민번호 900101-1234567입니다", "주민번호"),
        ("주민번호 9001011234567입니다", "주민번호"),
        ("카드 1234-5678-9012-3456로 결제", "카드번호"),
        ("면허 11-22-333333-44", "면허번호"),
        ("환불 계좌는 123-4567-890123입니다", "계좌"),
        ("여권번호 M12345678입니다", "여권번호"),
        ("instagram.com/example_user 보세요", "SNS"),
        ("인스타 @example_user로 DM 주세요", "SNS"),
        ("저는 35세입니다", "나이"),
        ("90년생입니다", "생년월일"),
        ("생년월일 1990-01-01", "생년월일"),
        ("저는 여성입니다", "성별"),
    ],
)
def test_항목별로_가리고_되돌린다(question, kind):
    masked, table = masking.mask(question)
    assert list(table) == [f"<{kind}1>"] and f"<{kind}1>" in masked
    assert masking.restore(masked, table) == question


@pytest.mark.parametrize(
    "question",
    [
        "컨테이너 MSKU1234567의 체화료는 하루 얼마인가요?",
        "2026-11-12 기준 운임 1,500,000원",
        "HS 0201100000 냉장 쇠고기",  # 유선 전화(02…)와 모양이 같은 10자리
        "예약번호 1234567890 상태",  # 계좌와 모양이 같지만 단서어 없음
        "입금일 2026-11-12에 확정",  # 계좌 단서어 뒤의 날짜
        "USD 150 @20ft",
        "여성의류 수출 서류",
        "3세대 컨테이너선",
        "컨테이너 3세트",
        "21세기 해운",
        "고객센터 1588-1234",
    ],
)
def test_도메인_값은_가리지_않는다(question):
    assert masking.mask(question) == (question, {})


def test_같은_값은_같은_자리표시자():
    masked, table = masking.mask("010-1234-5678, 01012345678, 010-9999-8888")
    assert masked == "<전화1>, <전화1>, <전화2>"
    assert table == {"<전화1>": "010-1234-5678", "<전화2>": "010-9999-8888"}


def test_공백_차이는_되돌리고_모르는_자리표시자는_둔다():
    table = {"<전화1>": "010-1234-5678"}
    assert masking.restore("<전화 1>로 연락, <전화3>은 모름", table) == "010-1234-5678로 연락, <전화3>은 모름"


def test_hide_pii_안에서만_기록을_가린다():
    data = {"messages": [{"role": "user", "content": "01012345678로 연락"}], "status": "answered"}
    assert tracing._mask(data=data) == data
    with tracing.hide_pii():
        assert tracing._mask(data=data) == {"messages": [{"role": "user", "content": "<전화1>로 연락"}], "status": "answered"}
    assert tracing._mask(data=data) == data
