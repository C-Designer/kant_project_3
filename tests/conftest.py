import hashlib
import math
import re
from types import SimpleNamespace

import httpx
import openai
import pytest

from src import config
from src.platform import llm
from src.search import embed, store

DIM = 64


def make_pdf(pages: list[str]) -> bytes:
    """외부 의존성 없이 원시 PDF 바이트로 텍스트 PDF를 만든다 (ASCII만)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font = 3 + 2 * n
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def _vec(text: str) -> list[float]:
    v = [0.0] * DIM
    for w in re.findall(r"\w+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


@pytest.fixture(autouse=True)
def _no_langfuse(monkeypatch):
    for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    monkeypatch.setattr(embed, "embed_passages", lambda texts: [_vec(t) for t in texts])
    monkeypatch.setattr(embed, "embed_query", _vec)


@pytest.fixture(autouse=True)
def memory_qdrant(monkeypatch):
    monkeypatch.setattr(config, "QDRANT_URL", None)
    monkeypatch.setattr(config, "QDRANT_PATH", None)
    monkeypatch.setattr(config, "RUN_LOG_PATH", None)
    store.reset_client()
    yield
    store.reset_client()


@pytest.fixture
def pdf_dir(tmp_path):
    d = tmp_path / "documents"
    d.mkdir()
    (d / "FB01.pdf").write_bytes(
        make_pdf(["Demurrage is charged per day after free time expires.", "Detention applies to containers kept outside the port."])
    )
    return d


@pytest.fixture
def fake_llm(monkeypatch):
    """script의 항목: str(JSON 텍스트) 또는 (str, 입력토큰, 출력토큰) 또는 예외. 호출 목록은 .calls."""

    class Fake:
        def __init__(self):
            self.script, self.calls = [], 0

        def invoke(self, messages):
            self.calls += 1
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            text, i, o = (item, None, None) if isinstance(item, str) else item
            usage = None if i is None else {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}
            return SimpleNamespace(content=text, usage_metadata=usage)

    fake = Fake()
    monkeypatch.setattr(llm, "_build_model", lambda name: fake)
    return fake


def timeout_error():
    return openai.APITimeoutError(httpx.Request("POST", "http://x"))
