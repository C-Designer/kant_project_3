"""실행 기록(results/runs/<id>/*.jsonl)의 최종 컨텍스트 청크를 골든 evidence_groups와 대조한다.

판정 (채점용 골든은 여기서만 읽는다. 검색·생성에는 넣지 않는다)
- page: 청크의 (book_id, page)가 근거 후보의 (book_id, page)와 같다
- text: 근거 quote의 10글자 조각 중 절반 이상이 청크 본문에 있다(공백 무시)
- 그룹 충족: 그룹 안 OR 후보 중 하나라도 맞으면 충족. 문항 재현율 = 충족 그룹 / 전체 그룹
- 근거 그룹이 없는 문항(clarify/abstain)은 재현율 None, 집계 분모에서 뺀다
사용: uv run python results/compare_golden.py results/runs/<run_id>
"""

import json
import re
import sys
from pathlib import Path

GOLD_FILES = ["development.json", "additional.json", "expansion_validation.json"]
N = 10


def norm(s):
    return re.sub(r"\s+", "", s)


def text_cover(quote, text):
    q, t = norm(quote), norm(text)
    grams = {q[i:i + N] for i in range(max(1, len(q) - N + 1))}
    return sum(g in t for g in grams) / len(grams)


def load_gold(root):
    gold = {}
    for f in GOLD_FILES:
        for item in json.loads((root / f).read_text(encoding="utf-8")):
            gold[item["id"]] = item
    return gold


def judge(rec, g):
    chunks = rec.get("final_context") or []
    cited = {(c["book_id"], c["page"]) for c in rec.get("citations") or []}
    groups = g.get("evidence_groups") or []
    rows = []
    for gi, group in enumerate(groups):
        best = None
        for cand in group:
            for rank, ch in enumerate(chunks, 1):
                m = ch["metadata"]
                page = (m["book_id"], m["page"]) == (cand["book_id"], cand["page"])
                cover = text_cover(cand["quote"], ch["text"])
                if page or cover >= 0.5:
                    hit = {"rank": rank, "chunk_id": m.get("chunk_id"), "page_hit": page, "cover": round(cover, 2)}
                    if best is None or hit["rank"] < best["rank"]:
                        best = hit
        rows.append({
            "group": gi,
            "gold": [f'{c["book_id"]} p{c["page"]}' for c in group],
            "hit": best,
            "cited": any((c["book_id"], c["page"]) in cited for c in group),
        })
    sat = sum(r["hit"] is not None for r in rows)
    return {
        "question_id": rec["question_id"],
        "mode": rec["retrieval_mode"],
        "expected": g["expected_action"],
        "status": rec["status"],
        "n_groups": len(groups),
        "recall": sat / len(groups) if groups else None,
        "all_groups": (sat == len(groups)) if groups else None,
        "cite_recall": sum(r["cited"] for r in rows) / len(groups) if groups else None,
        "retrieved": [f'{c["metadata"]["book_id"]} p{c["metadata"]["page"]}' for c in chunks],
        "groups": rows,
    }


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def main(run_dir):
    run_dir = Path(run_dir)
    gold = load_gold(Path("data/shipping_basic/evaluation"))
    results = []
    for f in sorted(run_dir.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            results.append(judge(rec, gold[rec["question_id"]]))
    (run_dir / "golden_compare.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")

    modes = sorted({r["mode"] for r in results})
    out = ["| mode | 근거 그룹 재현율 | 모든 그룹 충족 | 인용 재현율 | 판정 문항 |", "|---|---|---|---|---|"]
    for m in modes:
        rs = [r for r in results if r["mode"] == m]
        out.append(f'| {m} | {mean(r["recall"] for r in rs)} | {mean(r["all_groups"] for r in rs)} | '
                   f'{mean(r["cite_recall"] for r in rs)} | {sum(r["recall"] is not None for r in rs)} |')
    print("\n".join(out))
    print()
    qids = list(dict.fromkeys(r["question_id"] for r in results))
    print("| 문항 | 기대 | 그룹 | " + " | ".join(modes) + " |")
    print("|---|---|---|" + "---|" * len(modes))
    by = {(r["question_id"], r["mode"]): r for r in results}
    for q in qids:
        r0 = by[(q, modes[0])]
        cells = []
        for m in modes:
            r = by[(q, m)]
            cells.append("-" if r["recall"] is None else f'{r["recall"]:.2f} ({r["status"]})')
        print(f'| {q} | {r0["expected"]} | {r0["n_groups"]} | ' + " | ".join(cells) + " |")


assert abs(text_cover("가나다라마바사아자차카", "xx가나다 라마바사아자차카yy") - 1.0) < 1e-9
if __name__ == "__main__":
    main(sys.argv[1])
