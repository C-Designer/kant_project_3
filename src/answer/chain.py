from pathlib import Path

from src import config
from src.answer.context import source_map
from src.answer.validate import ValidationFailed, parse_output
from src.contracts import Citation, ContextChunk, LLMOutput
from src.platform import llm, tracing

PROMPT_VERSION = "v1"
_PROMPT_DIR = Path(__file__).parent / "prompts"


def system_prompt(*, defense: bool = False) -> str:
    text = (_PROMPT_DIR / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
    if defense:  # 보안 비교: 기본 프롬프트는 그대로 두고 끝에 방어 문장만 덧붙인다 (evaluation.md "보안 비교")
        text += "\n" + (_PROMPT_DIR / "defense.md").read_text(encoding="utf-8")
    return text


def _messages(question: str, context: list[ContextChunk], *, defense: bool = False) -> list[dict[str, str]]:
    material = "\n\n".join(f"[{c.source_id}]\n{c.text}" for c in context)
    user = f"[질문]\n{question}\n\n[검색 자료]\n{material}"
    return [{"role": "system", "content": system_prompt(defense=defense)}, {"role": "user", "content": user}]


def generate(question: str, context: list[ContextChunk], *, defense: bool = False) -> tuple[LLMOutput, list[Citation]]:
    if not context:
        return LLMOutput(status="abstained", answer="검색한 자료에서 확인하지 못했습니다", reason="검색 결과가 비어 있음", source_ids=[]), []

    messages = _messages(question, context, defense=defense)
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
