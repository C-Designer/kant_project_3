"""EXP-0001 청크 크기 x 오버랩 x k 실험 러너 (docs/experiments/0001-chunk-overlap-k.md).

    uv run python scripts/chunk_overlap_experiment.py retrieve   # 조합마다 로컬 메모리 색인을 만들고 k=7로 검색해 저장
    uv run python scripts/chunk_overlap_experiment.py generate   # 저장된 검색 결과로 k=4~7 답변 생성 (retrieve와 동시에 돌려도 된다)
    uv run python scripts/chunk_overlap_experiment.py report     # 표와 예시를 OUT/tables.md로
    (retrieve·generate에 --sizes 100,200 --overlaps 0,10 을 붙이면 그 조합만 맡는다. 병렬 실행 prompt: docs/experiments/0001-worker-prompt.md)

공용 Qdrant·Langfuse는 건드리지 않는다: QDRANT_URL과 Langfuse 키를 비우고 색인은 메모리에만 둔다.
청크 본문·정답이 든 산출물은 git 제외인 data/crag_exp/ 아래에만 둔다.
shortcut: 오버랩은 이 스크립트 안에서만 구현(src/search는 search 담당 영역), 채택하면 chunking.py로 옮긴다.
"""

import os

for _k in ("QDRANT_URL", "QDRANT_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
    os.environ[_k] = ""  # load_dotenv는 이미 있는 값을 덮어쓰지 않는다

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config  # noqa: E402
from src.answer import chain, context as ctx_mod  # noqa: E402
from src.contracts import ChunkMeta, RetrievedChunk, book_id_from_file_name  # noqa: E402
from src.metrics.loader import load_ground_truth  # noqa: E402
from src.metrics.questions import load_selection  # noqa: E402
from src.metrics.retrieval_metrics import hit_recall  # noqa: E402
from src.platform import llm  # noqa: E402
from src.search import chunking, index, keyword, retrieve, store  # noqa: E402

MAIN = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True).strip()).resolve().parent
DATA = MAIN / "data" / "shipping_basic"
QUESTIONS = MAIN / "results" / "questions-2.json"
OUT = MAIN / "data" / "crag_exp" / "chunk_overlap"
SIZES = range(100, 1000, 100)
OVERLAPS = (0, 10, 20)  # 크기 대비 %
KS = (4, 5, 6, 7)
MODES = ("naive", "hybrid", "hybrid_rerank")
KMAX = max(KS)
ACTION = {"answered": "answer", "needs_clarification": "clarify", "abstained": "abstain"}

config.QDRANT_PATH = None  # 메모리 색인
config.COLLECTION = "exp_chunk_overlap"


def chunk_with_overlap(file_name, pages, *, size, overlap):
    """chunking.chunk_pages와 같은 쪽 분할. 둘째 조각부터 앞 조각 본문의 마지막 overlap자를 앞에 붙인다. 전체 길이는 size 이하."""
    book_id = book_id_from_file_name(file_name)
    out = []
    for page, text in pages:
        if len(text) <= size:
            pieces = [text]
        else:
            *head_lines, body = text.split("\n")
            head = "".join(line + "\n" for line in head_lines)
            fresh = size - len(head) - overlap
            assert fresh > 0, (size, overlap, len(head))
            parts = chunking._split_body(body, fresh)
            pieces = [head + (parts[i - 1][-overlap:] if i and overlap else "") + p for i, p in enumerate(parts)]
            assert all(len(p) <= size for p in pieces)
        for n, piece in enumerate(pieces, start=1):
            out.append((piece, ChunkMeta(book_id=book_id, file_name=file_name, page=page, chunk_id=f"{book_id}-p{page}-c{n}")))
    return out


def _opt(flag, default):
    """--sizes 100,200 처럼 쉼표 목록으로 조합 일부만 맡는다(다른 장치와 나눠 돌릴 때)."""
    return tuple(int(x) for x in sys.argv[sys.argv.index(flag) + 1].split(",")) if flag in sys.argv else tuple(default)


def combos():
    return [(s, o) for s in _opt("--sizes", SIZES) for o in _opt("--overlaps", OVERLAPS)]


def name(size, pct):
    return f"s{size}_o{pct}"


def cmd_retrieve():
    questions = load_selection(QUESTIONS)
    (OUT / "retrieval").mkdir(parents=True, exist_ok=True)
    pages_cache = {p: chunking.extract_pages(p) for p in sorted((DATA / "documents").glob("*.pdf"))}
    chunking.extract_pages = lambda p, *a, **kw: pages_cache[Path(p)]
    for size, pct in combos():
        path = OUT / "retrieval" / f"{name(size, pct)}.json"
        if path.exists():
            continue
        overlap = size * pct // 100
        chunking.chunk_pages = lambda fn, pages, *, size, overlap, _o=overlap: chunk_with_overlap(fn, pages, size=size, overlap=_o)
        config.CHUNK_SIZE, config.CHUNK_OVERLAP = size, overlap
        store.reset_client()
        keyword.reset()
        t0 = time.time()
        rep = index.build_index(DATA / "documents")
        assert not rep["failed"], rep
        res = {"size": size, "overlap_pct": pct, "overlap": overlap, "chunks": rep["chunks"], "results": {}}
        for mode in MODES:
            for q in questions:
                t1 = time.perf_counter()
                chunks = retrieve.retrieve(q.question, mode, KMAX)
                res["results"].setdefault(mode, {})[q.id] = {
                    "retrieval_s": round(time.perf_counter() - t1, 2),
                    "chunks": [{"text": c.text, "score": c.score, "metadata": c.metadata.model_dump()} for c in chunks],
                }
        path.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"{name(size, pct)}: chunks={rep['chunks']} {time.time() - t0:.0f}s", flush=True)


def _generate(q, chunks):
    context = ctx_mod.build_context([RetrievedChunk(**c) for c in chunks], token_limit=config.CONTEXT_TOKEN_LIMIT)
    rec = {"n_context": len(context), "context_ids": [c.source_id for c in context]}
    t0 = time.perf_counter()
    try:
        with llm.usage_scope() as usage:
            out, cites = chain.generate(q, context)
        rec |= {"status": out.status, "answer": out.answer, "reason": out.reason, "citations": [c.model_dump() for c in cites],
                "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "error": None}
    except Exception as e:  # noqa: BLE001 실패도 기록하고 계속
        rec |= {"status": "error", "answer": "", "reason": "", "citations": [], "input_tokens": None, "output_tokens": None,
                "error": f"{type(e).__name__}: {e}"}
    rec["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return rec


def cmd_generate(workers=6):
    qtext = {q.id: q.question for q in load_selection(QUESTIONS)}
    (OUT / "answers").mkdir(parents=True, exist_ok=True)
    pending = True
    while pending:
        pending = False
        for size, pct in combos():
            src = OUT / "retrieval" / f"{name(size, pct)}.json"
            dst = OUT / "answers" / f"{name(size, pct)}.json"
            if dst.exists():
                continue
            if not src.exists():
                pending = True  # 아직 검색 중. 나중에 다시 본다
                continue
            data = json.loads(src.read_text(encoding="utf-8"))
            jobs = [(m, qid, k) for m in MODES for qid in data["results"][m] for k in KS]
            with ThreadPoolExecutor(workers) as ex:
                outs = list(ex.map(lambda j: _generate(qtext[j[1]], data["results"][j[0]][j[1]]["chunks"][: j[2]]), jobs))
            ans = {}
            for (m, qid, k), rec in zip(jobs, outs):
                ans.setdefault(m, {}).setdefault(qid, {})[str(k)] = rec
            dst.write_text(json.dumps(ans, ensure_ascii=False), encoding="utf-8")
            print(f"answers {name(size, pct)}", flush=True)
        if pending:
            time.sleep(60)


def _gold():
    truths = {t.question_id: t for t in load_ground_truth(DATA / "evaluation")}
    return truths


def page_recall(groups, chunks):
    """근거 그룹 중 (book_id, page)가 일치하는 청크가 있는 그룹 비율. 그룹 안은 OR."""
    got = {(c["metadata"]["book_id"], c["metadata"]["page"]) for c in chunks}
    ok = [any((g["book_id"], g["page"]) in got for g in grp) for grp in groups]
    return sum(ok) / len(ok) if ok else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def f(x, d=2):
    return "-" if x is None else f"{x:.{d}f}"


def cmd_report():
    truths = _gold()
    questions = load_selection(QUESTIONS)
    rows = []  # (size, pct, mode, k, hit, recall, page_recall, action_ok, n_ctx, in_tok, latency_s, errors, n_eval, chunks)
    for size, pct in combos():
        rp, ap = OUT / "retrieval" / f"{name(size, pct)}.json", OUT / "answers" / f"{name(size, pct)}.json"
        if not rp.exists():
            continue
        data = json.loads(rp.read_text(encoding="utf-8"))
        ans = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else {}
        for mode in MODES:
            for k in KS:
                hits, recs, prs, oks, nctx, tok, lat, err, ev = [], [], [], [], [], [], [], 0, 0
                for q in questions:
                    t = truths[q.id]
                    chunks = data["results"][mode][q.id]["chunks"][:k]
                    s = hit_recall(t.evidence_book_ids, [c["metadata"]["book_id"] for c in chunks], k)
                    hits.append(s.hit), recs.append(s.recall)
                    prs.append(page_recall(t.rubric.get("evidence_groups", []), chunks))
                    a = ans.get(mode, {}).get(q.id, {}).get(str(k))
                    if a:
                        if a["status"] == "error":
                            err += 1
                        else:
                            oks.append(ACTION[a["status"]] == t.expected_action)
                            lat.append(a["latency_ms"] / 1000)
                        nctx.append(a["n_context"])
                        tok.append(a["input_tokens"])
                rows.append((size, pct, mode, k, mean(hits), mean(recs), mean(prs), mean(oks), mean(nctx), mean(tok), mean(lat), err,
                             sum(h is not None for h in hits), data["chunks"]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    lines = []
    for mode in MODES:
        lines += [f"\n### {mode}: 청크 크기 x 오버랩 (k별 Recall@k / 쪽 단위 근거 재현율 / 행동 일치율)\n",
                  "| 크기 | 오버랩 | 청크 수 | " + " | ".join(f"k={k}" for k in KS) + " |", "|---|---|---|" + "---|" * len(KS)]
        for size, pct in combos():
            rs = [r for r in rows if r[:3] == (size, pct, mode)]
            if rs:
                lines.append(f"| {size} | {pct}% | {rs[0][13]} | " + " | ".join(f"{f(r[5])} / {f(r[6])} / {f(r[7])}" for r in rs) + " |")
    (OUT / "tables.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    {"retrieve": cmd_retrieve, "generate": cmd_generate, "report": cmd_report}[sys.argv[1]]()
