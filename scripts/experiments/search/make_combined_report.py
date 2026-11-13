"""여러 실험 결과(예: EXP-0020 k=11·5, EXP-0022 k=9·7)를 합쳐 질문마다 한 파일로 정리한다.

    uv run python scripts/experiments/search/make_combined_report.py \
      --in results/exp0020/laptop1 results/exp0022/laptop3 --out results/combined_report [--qids development/S-DEV-01 ...]

질문 파일 하나에 k·청크 크기·오버랩·방식별로: 정답(골든 답변·근거 위치·정답 청크), 가져온 청크(순위, 정답 ★, 한도로 밀려난 것),
놓친 정답 청크, 근거 충족, LLM 답변이 모인다. GPU·LLM이 필요 없다(청킹만 다시 한다). 숫자는 결과 폴더의 파일에서만 가져온다.
"""
import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_question_md as eq  # noqa: E402  (rechunk, quote_in 재사용)

MODES = ("naive", "hybrid", "hybrid_rerank")
FIRST_LIMIT = 3000


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def ok(b):
    return "-" if b is None else ("✅" if b else "❌")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True, help="결과 폴더들(k가 다른 실험). 같은 k는 앞에 준 폴더를 쓴다")
    ap.add_argument("--out", required=True)
    ap.add_argument("--qids", nargs="*")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "questions").mkdir(parents=True, exist_ok=True)

    runs = []  # (이름, 폴더, env, 질문)
    kmap = {}  # k -> 실행 인덱스
    for i, d in enumerate(a.inputs):
        d = Path(d)
        env = load(d / "env.json")
        runs.append((d.parent.name + "/" + d.name, d, env, load(d / "questions.json")))
        for k in env["k"]:
            kmap.setdefault(int(k), i)
    ks = sorted(kmap, reverse=True)
    sizes = sorted({int(s) for _, _, e, _ in runs for s in e["sizes"]})
    ctxs = sorted({int(c) for _, _, e, _ in runs for c in e["context_max"]})
    Q = runs[0][3]
    qids = a.qids or list(Q)

    R, A, FA = {}, {}, {}
    for i, (_, d, _, _) in enumerate(runs):
        for z in sizes:
            fp = d / "retrieval" / f"{z}_0.json"
            if fp.exists():
                R[(i, z)] = load(fp)
                for rec in load(d / "answers" / f"{z}_0.json")["records"]:
                    A[(i, z, rec["mode"], rec["qid"], int(rec["k"]), int(rec["ctx"]))] = rec
                for m in MODES:
                    for k in ks:
                        gp = d / "ragas" / f"{m}_{z}_0_k{k}.json"
                        if gp.exists():
                            for c, v in load(gp)["by_ctx"].items():
                                for q, res in zip(v["qids"], v["results"]):
                                    FA[(i, z, m, k, int(c), q)] = res.get("faithfulness")
    allc = {z: eq.rechunk(z, 0)[0] for z in sizes}  # 크기별 전체 청크(정답 청크 찾기용)

    index_rows = []
    for qid in qids:
        q = Q[qid]
        groups = [g for g in q.get("evidence_groups", []) if g]
        exp = q["expected_action"]
        L = [f"# {qid} — 질문 결과 종합", "",
             f"오버랩 0% · 청크 크기 {'·'.join(map(str, sizes))}자 · k {'·'.join(map(str, ks))} · 문맥 한도 {'·'.join(map(str, ctxs))}토큰 · 3방식. "
             f"자료: {', '.join(r[0] for r in runs)}", "", "[목록](../index.md)", "",
             "## 1. 질문과 정답", "", f"- **질문**: {q['question']}", f"- **기대 동작**: `{exp}` (answer = 답변, clarify = 되묻기, abstain = 보류)",
             f"- **골든 답변(reference_answer)**: {q.get('reference_answer') or '-'}"]
        if q.get("required_facts"):
            L.append(f"- 필수 사실: {q['required_facts']}")
        if q.get("forbidden_claims"):
            L.append(f"- 금지 주장: {q['forbidden_claims']}")
        L.append("")
        if groups:
            L += ["**정답 근거(골든 데이터셋)** — 그룹 안은 대안(하나만 찾으면 그 그룹 충족)", "", "| 그룹 | book_id | 쪽 | quote |", "|---|---|---|---|"]
            for gi, g in enumerate(groups, 1):
                for e in g:
                    L.append(f"| {gi} | {e['book_id']} | {e['page']} | {e['quote'][:120].replace('|', '/')}{'…' if len(e['quote']) > 120 else ''} |")
            L.append("")
        else:
            L += ["이 질문은 근거가 없는 유형이라(되묻기·보류) 검색 정답 청크가 없다. 아래에서는 가져온 청크와 LLM의 동작(기대와 같은가)만 본다.", ""]

        # 크기별 정답 청크
        gold = {}
        for z in sizes:
            gold[z] = {}
            for gi, g in enumerate(groups, 1):
                for e in g:
                    for cid, c in allc[z].items():
                        if c["book"] == e["book_id"] and c["page"] == e["page"] and eq.quote_in(c["text"], e["quote"]):
                            gold[z].setdefault(cid, []).append(gi)

        def cell(z, mode, k):
            i = kmap[k]
            row = R.get((i, z), {}).get("modes", {}).get(mode, {}).get(qid)
            if not row:
                return None
            kk = row["k"][str(k)]
            return row, kk

        # 2. 한눈에 보기
        L += ["## 2. 한눈에 보기 (문맥 한도 3000 → 4200)", "",
              "칸: `근거 3000/4200 · 밀려난 청크 3000/4200 · 답변(기대와 같은가) 3000/4200`. 근거 ✅는 정답 그룹을 **모두** 찾았다는 뜻이고 `-`는 근거가 없는 질문이다.", ""]
        for k in ks:
            L += [f"### k = {k}  ({runs[kmap[k]][0]})", "", "| 청크 크기 | " + " | ".join(MODES) + " |", "|---|---|---|---|"]
            for z in sizes:
                cs = []
                for m in MODES:
                    c = cell(z, m, k)
                    if not c:
                        cs.append("-")
                        continue
                    row, kk = c
                    lo, hi = str(min(ctxs)), str(max(ctxs))
                    mm3, mm4 = kk["ctx"][lo].get("m"), kk["ctx"][hi].get("m")
                    n_top = kk["n_top"]
                    d3, d4 = n_top - kk["ctx"][lo]["n_used"], n_top - kk["ctx"][hi]["n_used"]
                    a3, a4 = A.get((kmap[k], z, m, qid, k, int(lo))), A.get((kmap[k], z, m, qid, k, int(hi)))
                    cs.append(f"{ok(mm3 and mm3['all_pq'])}/{ok(mm4 and mm4['all_pq'])} · 밀림 {d3}/{d4} · 답 {ok(a3 and a3['status_match'])}/{ok(a4 and a4['status_match'])}")
                L.append(f"| {z}자 | " + " | ".join(cs) + " |")
            L.append("")

        # 3. 크기별 상세
        L += ["## 3. 청크 크기별 상세", "",
              "청크 표기: `id` 그대로 = 한도 3000에서 문맥에 들어감 · **★** = 정답 청크(quote가 든 청크) · `❌id(≥3400)` = 한도 3000에서 **밀려남**, 괄호는 그 청크가 문맥에 들어가는 가장 작은 한도(없으면 `없음`). 밀려난 청크와 그 뒤 청크는 모두 빠진다.", ""]
        for z in sizes:
            gz = gold[z]
            L += [f"### 청크 {z}자", ""]
            if groups:
                L.append("**정답 청크(이 크기로 자른 청킹)**: " + (", ".join(f"`{c}`(그룹 {','.join(map(str, gs))})" for c, gs in gz.items()) or "없음 (quote 앞 40자가 한 청크 안에 없다 — 청크 경계에서 잘림)"))
                L.append("")
            L += ["| k | 방식 | 가져온 청크 (순위순) | 놓친 정답 청크 | 근거 충족 3000 / 4200 | 답변 3000 / 4200 |", "|---|---|---|---|---|---|"]
            seen_chunks, answers = {}, []
            for k in ks:
                for m in MODES:
                    c = cell(z, m, k)
                    if not c:
                        continue
                    row, kk = c
                    top = row["top_ids"][:k]
                    used_by = {int(l): set(v["ids"]) for l, v in kk["ctx"].items()}
                    parts = []
                    for r_, cid in enumerate(top, 1):
                        star = "★" if cid in gz else ""
                        seen_chunks[cid] = R[(kmap[k], z)]["chunks"][cid]
                        if cid in used_by[min(ctxs)]:
                            parts.append(f"{r_}.`{cid}`{star}")
                        else:
                            back = next((l for l in ctxs if cid in used_by[l]), None)
                            parts.append(f"{r_}.❌`{cid}`{star}(≥{back if back else '없음'})")
                    missed = [cid for cid in gz if cid not in top]
                    lo, hi = str(min(ctxs)), str(max(ctxs))
                    mm3, mm4 = kk["ctx"][lo].get("m"), kk["ctx"][hi].get("m")
                    a3, a4 = A.get((kmap[k], z, m, qid, k, int(lo))), A.get((kmap[k], z, m, qid, k, int(hi)))
                    f3, f4 = FA.get((kmap[k], z, m, k, int(lo), qid)), FA.get((kmap[k], z, m, k, int(hi), qid))
                    ans = lambda x: "-" if not x else f"{ok(x['status_match'])}{x['answer']['status']}"  # noqa: E731
                    L.append(f"| {k} | {m} | {'<br>'.join(parts)} | {', '.join(f'`{c}`' for c in missed) or ('-' if groups else '해당 없음')} | "
                             f"{ok(mm3 and mm3['all_pq'])} / {ok(mm4 and mm4['all_pq'])} | {ans(a3)} / {ans(a4)}"
                             + (f" · faith {f3:.2f}/{f4:.2f}" if f3 is not None and f4 is not None else "") + " |")
                    answers.append((k, m, a3, a4))
            L.append("")
            # 가져온 청크 내용: 방식마다 상위 K개를 순위표로, 앞부분 미리보기가 보이고 클릭하면 전문이 펼쳐진다
            K = max(ks)
            esc = lambda s: html.escape(s).replace("|", "&#124;").replace("\n", "<br>")  # noqa: E731
            L += [f"#### {z}자: 가져온 청크 내용 (순위순, 상위 {K}개, 내용을 누르면 전문)", "",
                  f"한 표가 한 방식이다. `들어가는 k`는 그 순위의 청크가 어느 k부터 문맥에 들어가는지(예: 7 = k 7·9·11), `한도 3000`은 문맥 한도 3000에서 그 청크가 들어가는지(❌ 밀림, 괄호는 들어가는 가장 작은 한도)다.", ""]
            shown = set()
            for m in MODES:
                c = cell(z, m, K)
                if not c:
                    continue
                row, kk = c
                top = row["top_ids"][:K]
                used_by = {int(l): set(v["ids"]) for l, v in kk["ctx"].items()}
                L += [f"**{m}**", "", "| 순위 | 청크 id | 쪽 | 들어가는 k | 한도 3000 | 정답 | 내용 (앞부분 / 클릭하면 전문) |", "|---|---|---|---|---|---|---|"]
                for r_, cid in enumerate(top, 1):
                    ch = R[(kmap[K], z)]["chunks"][cid]
                    shown.add(cid)
                    first_k = next((kk_ for kk_ in sorted(ks) if r_ <= kk_), K)
                    if cid in used_by[min(ctxs)]:
                        stat = "✅"
                    else:
                        back = next((l for l in ctxs if cid in used_by[l]), None)
                        stat = f"❌(≥{back if back else '없음'})"
                    body = ch["text"].rpartition("\n")[2] or ch["text"]  # 첫 줄은 문서 제목이라 본문 줄로 미리보기
                    prev = esc(body[:70]) + ("…" if len(body) > 70 else "")
                    L.append(f"| {r_} | `{cid}` | {ch['book_id']} {ch['page']}쪽 | {first_k} | {stat} | {'★' if cid in gz else ''} | <details><summary>{prev}</summary>{esc(ch['text'])}</details> |")
                L.append("")
            missed_gold = [cid for cid in gz if cid not in shown]
            if missed_gold:
                L += [f"**어느 방식의 상위 {K}개에도 없는 정답 청크** (놓침)", "", "| 청크 id | 쪽 | 내용 (앞부분 / 클릭하면 전문) |", "|---|---|---|"]
                for cid in missed_gold:
                    ch = allc[z][cid]
                    body = ch["text"].rpartition("\n")[2] or ch["text"]
                    L.append(f"| `{cid}`★ | {ch['book']} {ch['page']}쪽 | <details><summary>{esc(body[:70])}{'…' if len(body) > 70 else ''}</summary>{esc(ch['text'])}</details> |")
                L.append("")
            L += [f"<details><summary>{z}자: LLM 답변과 골든 답변 비교 (한도 3000 / 4200)</summary>", "",
                  f"골든 답변: {q.get('reference_answer') or '-'}", ""]
            for k, m, a3, a4 in answers:
                for lim, x in ((min(ctxs), a3), (max(ctxs), a4)):
                    if x:
                        an = x["answer"]
                        L.append(f"- **k={k} · {m} · 한도 {lim}** ({ok(x['status_match'])} `{an['status']}`, 입력 {x['input_tokens']} / 출력 {x['output_tokens']}토큰, LLM {x['llm_ms']}ms): {an.get('answer') or '-'}")
            L += ["", "</details>", ""]

        fn = qid.replace("/", "_") + ".md"
        (out / "questions" / fn).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
        index_rows.append((qid, exp, fn, q["question"]))

    # index
    I = ["# EXP-0020 + EXP-0022 합친 보고서", "",
         f"- 청크 크기 {', '.join(map(str, sizes))}자, 오버랩 0%, k {', '.join(map(str, ks))}, 문맥 한도 {', '.join(map(str, ctxs))}토큰, 방식 naive / hybrid / hybrid_rerank",
         "- 자료: " + ", ".join(f"{r[0]}(k {', '.join(map(str, r[2]['k']))})" for r in runs), "",
         "## 이 보고서의 구조", "", "- `questions/<세트>_<문항>.md`: 질문 하나의 모든 조건 결과 — 정답, 가져온 청크, 정답 청크 ★, 밀려난 청크 ❌, 놓친 정답 청크, 답변 비교",
         "- 이 `index.md`: 조건 매핑과 질문 목록", "", "## 조건 매핑 (어느 실험이 어느 k를 맡았나)", "", "| k | 실험 폴더 | 청크 크기 | 오버랩 | 문맥 한도 |", "|---|---|---|---|---|"]
    for k in ks:
        I.append(f"| {k} | {runs[kmap[k]][0]} | {', '.join(map(str, sizes))} | 0% | {', '.join(map(str, ctxs))} |")
    I += ["", f"## 질문 목록 ({len(index_rows)}개)", "", "| 질문 | 기대 | 질문 글 | 파일 |", "|---|---|---|---|"]
    for qid, exp, fn, qt in index_rows:
        I.append(f"| {qid} | {exp} | {qt[:60]}{'…' if len(qt) > 60 else ''} | [{fn}](questions/{fn}) |")
    (out / "index.md").write_text("\n".join(I) + "\n", encoding="utf-8", newline="\n")
    print(f"저장: {out} (질문 {len(index_rows)}개)")


if __name__ == "__main__":
    main()
