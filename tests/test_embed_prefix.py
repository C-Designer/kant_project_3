"""모델마다 입력 접두어가 다르다. E5 계열은 passage:/query:를 붙이고 bge 계열은 붙이지 않는다."""

import pytest

from src import config
from src.search import embed


@pytest.mark.parametrize(
    "model, expected",
    [
        ("intfloat/multilingual-e5-small", ("passage: ", "query: ")),
        ("intfloat/multilingual-e5-large", ("passage: ", "query: ")),
        ("nlpai-lab/KoE5", ("passage: ", "query: ")),
        ("BAAI/bge-m3", ("", "")),
        ("dragonkue/bge-m3-ko", ("", "")),
    ],
)
def test_모델별_접두어(monkeypatch, model, expected):
    monkeypatch.setattr(config, "EMBEDDING_MODEL", model)
    assert embed._prefixes() == expected
