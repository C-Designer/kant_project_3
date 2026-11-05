import json
from pathlib import Path

from pydantic import BaseModel


def append(path: str | Path, obj) -> None:
    line = obj.model_dump_json() if isinstance(obj, BaseModel) else json.dumps(obj, ensure_ascii=False, default=str)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
