from pathlib import Path

from src import config
from src.answer.context import source_map
from src.answer.validate import ValidationFailed, parse_output
from src.contracts import Citation, ContextChunk, LLMOutput
from src.platform import llm, tracing

_PROMPT_PATH = Path(__file__).parent / "prompts" / "v0.md"


def _messages(question: str, context: list[ContextChunk]) -> list[dict[str, str]]:
    material = "\n\n".join(f"[{c.source_id}]\n{c.text}" for c in context)
    user = f"[질문]\n{question}\n\n[검색 자료]\n{material}"
    return [{"role": "system", "content": _PROMPT_PATH.read_text(encoding="utf-8")}, {"role": "user", "content": user}]


def generate(question: str, context: list[ContextChunk], *, defense: bool = False) -> tuple[LLMOutput, list[Citation]]:
    if defense:
        raise NotImplementedError("방어 프롬프트는 구현 예정 (#22)")
    if not context:
        return LLMOutput(status="abstained", answer="검색한 자료에서 확인하지 못했습니다", reason="검색 결과가 비어 있음", source_ids=[]), []

    messages = _messages(question, context)
    last: ValidationFailed | None = None
    for _ in range(1 + config.REGENERATE_MAX):
        with tracing.span("generate", input=messages) as sp:
            res = llm.call(messages)
            sp.update(output=res.text)
        with tracing.span("validate", input=res.text) as sp:
            try:
                out = parse_output(res.text, context)
            except ValidationFailed as e:
                sp.update(output="failed", metadata={"error": str(e)})
                last = e
                continue
            sp.update(output="ok")
        smap = source_map(context)
        ids = list(dict.fromkeys(out.source_ids))
        return out, [
            Citation(source_id=i, book_id=smap[i].book_id, file_name=smap[i].file_name, page=smap[i].page) for i in ids
        ]
    raise last  # type: ignore[misc]  # 루프는 최소 1회 돌고 실패했을 때만 여기 온다
