"""실행 환경이 팀 고정값과 같은지 확인한다.

`uv sync`로 만든 환경이 아니면(예: PC 기본 Python 3.14, pip로 따로 설치) 여기서 바로 실패한다.
작업 중 이상한 import 오류를 만나기 전에 원인을 알려 주는 것이 목적이다.

실행: uv run pytest tests/test_environment.py -q
"""

import importlib.metadata as metadata
import sys


def _major_minor(package: str) -> tuple[int, int]:
    major, minor = metadata.version(package).split(".")[:2]
    return int(major), int(minor)


def test_파이썬은_3_12다():
    assert sys.version_info[:2] == (3, 12), (
        f"지금 Python {sys.version.split()[0]}. 팀 환경은 3.12다. `uv sync` 후 `uv run`으로 실행한다."
    )


def test_langchain은_0_3_계열이다():
    for package in ("langchain", "langchain-core", "langchain-community", "langchain-openai"):
        assert _major_minor(package) == (0, 3), (
            f"{package} {metadata.version(package)}. LangChain은 0.3 계열로 고정이다(RAGAS 호환). "
            "AGENTS.md와 docs/specs/judge.md '실행 환경 제약' 참고."
        )


def test_ragas는_0_4_3이다():
    assert metadata.version("ragas") == "0.4.3"


def test_ragas를_불러올_수_있다():
    # 최신 langchain-community(0.4.x)와 섞이면 여기서 ImportError가 난다.
    from ragas import SingleTurnSample  # noqa: F401
    from ragas.llms.base import BaseRagasLLM  # noqa: F401
