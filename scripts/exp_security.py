"""EXP-0002 설정들에 보안 비교(src/platform/security.py)를 붙인다. 이미 만든 설정별 색인을 읽고 새로 색인하지 않는다.

    PYTHONPATH=. uv run python scripts/exp_security.py --sweep exposure            # 전 설정, 노출 여부만(LLM 없음)
    PYTHONPATH=. uv run python scripts/exp_security.py --sweep full --labels baseline,c1,c2,c3,c4 --modes hybrid_rerank

설정 하나는 자식 프로세스 하나로 돈다(config 덮어쓰기와 로컬 Qdrant 클라이언트가 프로세스 단위라서).
attack_text는 노출 판정에만 쓰고 문맥·프롬프트에 넣지 않는다. 추종·정확성·과잉 거절은 사람이 판정한다.
발제 필수 산출물(동결 설정, 공식 Langfuse 프로젝트의 보안 답변 4개, #42)을 대신하지 않는다.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

IDX = Path(".scratch/idx")
OUT = Path("results/exp2/security")
MODES = ["naive", "hybrid", "hybrid_rerank"]
# (청크, 겹침) -> 그 청킹으로 만든 색인 폴더
INDEX = {(900, 0): "baseline-r1", (300, 0): "s1-chunk-300", (450, 0): "s2-chunk-450", (600, 0): "chunk-600", (750, 0): "s2-chunk-750",
         (1050, 0): "s1-chunk-1050", (1200, 0): "chunk-1200", (900, 50): "s1-overlap-50", (900, 100): "overlap-100",
         (900, 150): "s1-overlap-150", (900, 200): "overlap-200", (900, 300): "s1-overlap-300"}
BASE = dict(chunk=900, overlap=0, k=5, ctx=3000, rerank=20)


def settings() -> dict[str, dict]:
    s = {"baseline": dict(BASE)}
    for k in (2, 3, 4, 6, 8):
        s[f"topk-{k}"] = {**BASE, "k": k}
    for k in (10, 12):  # LLM 평가 때와 같이 문맥 한도를 6000으로 푼다
        s[f"topk-{k}"] = {**BASE, "k": k, "ctx": 6000}
    for c in (300, 450, 600, 750, 1050, 1200):
        s[f"chunk-{c}"] = {**BASE, "chunk": c}
    for o in (50, 100, 150, 200, 300):
        s[f"overlap-{o}"] = {**BASE, "overlap": o}
    for c in (1000, 1500):
        s[f"ctx-{c}"] = {**BASE, "ctx": c}
    for c in (1500, 2000, 2500, 4000, 6000):
        s[f"ctx8-{c}"] = {**BASE, "k": 8, "ctx": c}
    for r in (5, 10, 15, 30, 40):
        s[f"rerank-{r}"] = {**BASE, "rerank": r, "modes": ["hybrid_rerank"]}  # 이 방식에만 영향
    for name, (c, k, r) in {"c1": (450, 10, 20), "c2": (600, 8, 16), "c3": (450, 8, 16), "c4": (600, 10, 20)}.items():
        s[name] = {**BASE, "chunk": c, "k": k, "rerank": r}
    return s


def child(label: str, modes: list[str], full: bool) -> None:
    from scripts.exp_config import apply
    applied = apply()
    from src import config
    from src.answer import context as ctx_mod
    from src.metrics.loader import load_security
    from src.platform import security, tracing
    from src.search.retrieve import retrieve

    questions, truths = load_security(config.DATA_DIR / "evaluation")
    assert len(questions) == 2, "보안 질문은 2개여야 한다"
    rows = []
    for mode in modes:
        for q in questions:
            attack = truths[q.id].rubric["attack_text"]
            chunks = retrieve(q.question, mode, config.K)
            context = ctx_mod.build_context(chunks, token_limit=config.CONTEXT_TOKEN_LIMIT)
            row = {"label": label, "mode": mode, "question_id": q.id, **{k: applied[k] for k in ("chunk_size", "chunk_overlap", "topk", "context_tokens", "rerank_candidates")},
                   "attack_in_retrieved": security.attack_exposed(attack, chunks),  # 검색은 됐는데 문맥 한도로 빠졌는지 구분하려고 따로 본다
                   "attack_in_context": security.attack_exposed(attack, context), "n_context": len(context),
                   "context_book_ids": list(dict.fromkeys(c.metadata.book_id for c in context))}
            if full:
                pair = security.run_pair(q.question, mode, attack, q.id)
                row.update(question=q.question, request_id=pair["request_id"], attack_in_context=pair["attack_in_context"],
                           default=pair["default"], defense=pair["defense"])
            rows.append(row)
    if full:
        tracing.flush()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{'full' if full else 'exposure'}-{label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sweep", choices=["exposure", "full"])
    p.add_argument("--labels", default="")
    p.add_argument("--modes", default=",".join(MODES))
    p.add_argument("--child", default="")
    p.add_argument("--full", action="store_true")
    a = p.parse_args()
    if a.child:
        return child(a.child, a.modes.split(","), a.full)

    todo = settings()
    if a.labels:
        todo = {k: todo[k] for k in a.labels.split(",")}
    full = a.sweep == "full"
    for label, s in todo.items():
        idx = IDX / INDEX[(s["chunk"], s["overlap"])]
        if not (idx / "index_meta.json").exists():
            print(f"{label}: 색인 없음({idx}), 건너뜀"); continue
        modes = [m for m in a.modes.split(",") if m in s.get("modes", MODES)]
        if not modes:
            continue
        env = {**os.environ, "EXP_LABEL": f"sec-{label}", "EXP_INDEX_DIR": str(idx), "EXP_CHUNK_SIZE": str(s["chunk"]), "EXP_CHUNK_OVERLAP": str(s["overlap"]),
               "EXP_TOPK": str(s["k"]), "EXP_CONTEXT_TOKENS": str(s["ctx"]), "EXP_RERANK_CANDIDATES": str(s["rerank"]), "PYTHONPATH": "."}
        if not full:  # 노출만 볼 때는 Langfuse에 스팬을 남기지 않는다
            env.update(LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="")
        r = subprocess.run([sys.executable, __file__, "--child", label, "--modes", ",".join(modes)] + (["--full"] if full else []),
                           env=env, capture_output=True, text=True)
        f = OUT / f"{'full' if full else 'exposure'}-{label}.json"
        if r.returncode != 0 or not f.exists():
            print(f"{label}: 실패 {r.stderr.strip().splitlines()[-1][:200] if r.stderr.strip() else r.returncode}"); continue
        rows = json.loads(f.read_text(encoding="utf-8"))
        print(label, " ".join(f"{x['mode'][:6]}/{x['question_id'][-2:]}:{'노출' if x['attack_in_context'] else ('검색만' if x['attack_in_retrieved'] else '-')}" for x in rows), flush=True)


if __name__ == "__main__":
    assert len(settings()) == 35 and INDEX[(900, 0)] == "baseline-r1"
    main()
