"""하위 질문 분해 (search 영역, #125).

물음이 둘 이상인 복합 질문을 물음마다 하위 질문 하나로 나눈다. 질문 글만 LLM에 주고(정답·근거는 쓰지 않는다),
LLM 호출은 platform.llm.call 한 곳만 쓴다.
"""

import json
import re

from src import config
from src.platform import llm

SYSTEM = (
    "너는 문서 검색용 질문 분해기다. 사용자의 복합 질문을 문서 검색에 쓸 하위 질문으로 나눈다. 규칙: "
    "(1) 하위 질문마다 한 가지만 묻고, 혼자 읽어도 뜻이 통하게 필요한 조건(장비 종류, 날짜 등)을 포함한다. "
    "(2) 질문이 하나뿐이면 원문 하나만 낸다. (3) 최대 4개. (4) 답을 추측하거나 사실을 덧붙이지 않는다. "
    "출력은 JSON 문자열 배열 하나만, 다른 글은 쓰지 않는다."
)  # 분석(search-notes)에서 쓴 프롬프트 그대로. 규칙 (3)의 4는 config.SUBQ_MAX와 맞춘다


def decompose(question: str) -> list[str]:
    """하위 질문 목록(최대 SUBQ_MAX개). LLM 오류나 형식 오류면 빈 목록이라, 호출자가 원래 질문으로 대신한다."""
    try:
        text = llm.call([{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]).text
    except llm.LLMError:
        return []
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        subs = json.loads(m.group(0))
    except ValueError:
        return []
    return [s for s in subs if isinstance(s, str) and s.strip()][: config.SUBQ_MAX]
