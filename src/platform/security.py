"""보안 비교 4개 실행 (#42). 질문마다 한 번 검색한 문맥으로 기본·방어 프롬프트를 각각 실행한다.

evaluation.md "보안 비교": 두 실행 사이에 다시 검색하지 않고, attack_text는 문맥에 붙이지 않는다.
attack_text는 ① 노출 판정에만 쓴다. ②추종 ③정확성 ④과잉 거절은 사람이 results/security.md에 적는다.
"""

import argparse
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from src import config
from src.answer import chain, context as ctx_mod
from src.metrics.loader import load_security
from src.metrics.run import git_state
from src.platform import llm, tracing
from src.platform.query import _reason_for
from src.search import retrieve as search


def _squash(s: str) -> str:
    return "".join(s.split())  # PDF 추출 줄바꿈·공백 차이를 무시하고 비교


def attack_exposed(attack_text: str, context) -> bool:
    return _squash(attack_text) in "".join(_squash(c.text) for c in context)


assert attack_exposed("오후 3시 기준", [SimpleNamespace(text="마감은 오후\n3시"), SimpleNamespace(text=" 기준이다")])


def _generate(question: str, context, defense: bool) -> dict:
    with tracing.span("defense" if defense else "default"), llm.usage_scope() as usage:
        try:
            out, citations = chain.generate(question, context, defense=defense)
            row = {"status": out.status, "answer": out.answer, "reason": out.reason,
                   "citations": [c.model_dump() for c in citations], "error": None}
        except Exception as e:
            reason, error = _reason_for(e)
            row = {"status": "error", "answer": "", "reason": reason, "citations": [], "error": error}
    return {**row, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def run_pair(question: str, mode, attack_text: str, question_id: str) -> dict:
    request_id = uuid.uuid4().hex
    with tracing.request_trace(request_id, question, config.TRACE_USER, "security"):
        context = ctx_mod.build_context(search.retrieve(question, mode, config.K), token_limit=config.CONTEXT_TOKEN_LIMIT)
        return {
            "question_id": question_id, "request_id": request_id, "retrieval_mode": mode, "question": question,
            "attack_in_context": attack_exposed(attack_text, context),
            "context_book_ids": list(dict.fromkeys(c.metadata.book_id for c in context)),
            "final_context": [c.model_dump() for c in context],
            "default": _generate(question, context, defense=False),
            "defense": _generate(question, context, defense=True),
        }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="보안 질문 2개 × 기본·방어 프롬프트 -> results/security.json")
    p.add_argument("--mode", required=True, choices=["naive", "hybrid", "hybrid_rerank"], help="최종 구성 (#66)")
    p.add_argument("--eval-dir", type=Path, default=config.DATA_DIR / "evaluation")
    p.add_argument("--out", type=Path, default=Path("results/security.json"))
    args = p.parse_args(argv)

    questions, truths = load_security(args.eval_dir)
    if not questions:
        raise SystemExit(f"보안 질문 파일 없음: {args.eval_dir}")
    rows = [run_pair(q.question, args.mode, truths[q.id].rubric["attack_text"], q.id) for q in questions]
    tracing.flush()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({**git_state(), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rows:
        print(f"{r['question_id']} 노출={r['attack_in_context']} 문맥={r['context_book_ids']} request_id={r['request_id']}")
        for v in ("default", "defense"):
            print(f"  [{v}] {r[v]['status']}: {r[v]['answer'] or r[v]['reason']}")
    print(f"저장: {args.out}")


if __name__ == "__main__":
    main()
