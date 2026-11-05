import json
import re

from pydantic import ValidationError

from src.contracts import ContextChunk, LLMOutput


class ValidationFailed(Exception):
    pass


def parse_output(raw: str, context: list[ContextChunk]) -> LLMOutput:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        out = LLMOutput.model_validate(json.loads(text))
    except (ValueError, ValidationError) as e:  # JSONDecodeError도 ValueError
        raise ValidationFailed(f"출력 형식 오류: {e}") from e
    unknown = set(out.source_ids) - {c.source_id for c in context}
    if unknown:
        raise ValidationFailed(f"문맥에 없는 source_ids: {sorted(unknown)}")
    if out.status == "answered" and not out.source_ids:
        raise ValidationFailed("answered인데 source_ids가 비어 있음")
    return out
