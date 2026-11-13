"""여러 실험 결과(0020 k=11·5, 0022 k=9·7, 오버랩 10·20% 실행)를 역할별 문서로 나눠 정리한다.

    uv run python scripts/experiments/search/make_report_v2.py \
      --in results/exp0020/laptop1 results/exp0022/laptop3 results/exp0020/laptop1_ov --out results/report_v2

저장:
    index.md                   한눈에: 조건 매핑, 문서 안내, 질문 목록(한도 효과·못 찾음 표시)
    findings/recall_matrix.md  조건별 Recall(쪽+인용문)·밀려난 청크 비교표
    questions/<세트>_<문항>.md  질문 하나: 정답, 조건별 요약, 청크 × 방식 순위표, 답변 비교
    chunks/size<크기>_ov<오버랩>.md  청크 도감: 청크 전문을 한 번만, 어느 질문이 가져왔는지
    data/rows.jsonl, data/metrics.csv, data/schema.md  기계용 원자료
GPU·LLM이 필요 없다(청킹만 다시 한다). 숫자는 결과 폴더의 파일에서만 가져온다. merged.json이 없으면 merge_grid_results.py를 먼저 실행한다.
"""
import argparse
import csv
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_question_md as eq  # noqa: E402  (rechunk, quote_in 재사용)

MODES = ("naive", "hybrid", "hybrid_rerank")
CTX_KEYS = ("used_3000", "used_3400", "used_3800", "used_4200")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def ok(b):
    return "-" if b is None else ("✅" if b else "❌")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--qids", nargs="*")
    ap.add_argument("--only-findings", action="store_true", help="findings/recall_matrix.md만 다시 만든다(몇 초)")
    a = ap.parse_args()
    out = Path(a.out)
    for d in ("findings", "questions", "chunks", "data"):
        (out / d).mkdir(parents=True, exist_ok=True)

    runs = []
    for d in a.inputs:
        d = Path(d)
        env = load(d / "env.json")
        runs.append(dict(name=f"{d.parent.name}/{d.name}", dir=d, ks=[int(k) for k in env["k"]], pcts=[int(p) for p in env["pcts"]],
                         merged=load(d / "report" / "merged.json") if (d / "report" / "merged.json").exists() else None))
    sizes = sorted({int(s) for r in runs for s in load(r["dir"] / "env.json")["sizes"]})
    ctxs = sorted({int(c) for r in runs for c in load(r["dir"] / "env.json")["context_max"]})
    pcts = sorted({p for r in runs for p in r["pcts"]})
    Q = load(runs[0]["dir"] / "questions.json")
    qids = a.qids or list(Q)

    def src(p, k):  # 그 오버랩·k를 만든 실행(앞에 준 폴더 우선)
        return next((i for i, r in enumerate(runs) if p in r["pcts"] and k in r["ks"]), None)

    ks_of = {p: sorted({k for r in runs if p in r["pcts"] for k in r["ks"]}, reverse=True) for p in pcts}
    R, A, FA = {}, {}, {}
    for i, r in enumerate(runs):
        for z in sizes:
            for p in r["pcts"]:
                fp = r["dir"] / "retrieval" / f"{z}_{p}.json"
                if fp.exists():
                    R[(i, z, p)] = load(fp)
                    for rec in load(r["dir"] / "answers" / f"{z}_{p}.json")["records"]:
                        A[(i, z, p, rec["mode"], rec["qid"], int(rec["k"]), int(rec["ctx"]))] = rec
                    for m in MODES:
                        for k in r["ks"]:
                            gp = r["dir"] / "ragas" / f"{m}_{z}_{p}_k{k}.json"
                            if gp.exists():
                                for c, v in load(gp)["by_ctx"].items():
                                    for q, res in zip(v["qids"], v["results"]):
                                        FA[(i, z, p, m, k, int(c), q)] = res.get("faithfulness")
    conds = [(z, p) for z in sizes for p in pcts if (src(p, ks_of[p][0]), z, p) in R]
    esc = lambda s: html.escape(s).replace("|", "&#124;").replace("\n", "<br>")  # noqa: E731
    pv = lambda ch, n=40: esc((ch["text"].rpartition("\n")[2] or ch["text"])[:n]) + ("…" if len(ch["text"].rpartition("\n")[2] or ch["text"]) > n else "")  # noqa: E731
    ov = lambda p: f"ov{p}"  # noqa: E731

    # ---------- findings/ ----------
    def write_findings():
        def table(title, key, fmt="{:.3f}"):
            F.append(f"## {title}")
            F.append("")
            for k in sorted({k for p in pcts for k in ks_of[p]}, reverse=True):
                F.extend([f"### k = {k}", "", "| 오버랩 | 크기 | " + " | ".join(f"{m} {c}" for m in MODES for c in ctxs) + " |", "|---|---|" + "---|" * (len(MODES) * len(ctxs))])
                for (z, p) in conds:
                    if k not in ks_of[p]:
                        continue
                    M = runs[src(p, k)]["merged"]
                    cs = []
                    for m in MODES:
                        for c in ctxs:
                            x = M and M["retrieval"].get(f"{z}|{p}|{c}|{m}|{k}")
                            v = None if not x else (x["n_drop"] if key == "n_drop" else x[key])
                            cs.append("-" if v is None else fmt.format(v))
                    F.append(f"| {p}% | {z}자 | " + " | ".join(cs) + " |")
                F.append("")

        F = ["# 조건별 비교: 문맥 한도(3000·3400·3800·4200)마다 Recall", "",
             "[목록](../index.md) · 값은 각 실행의 `report/merged.json`에서 가져왔다. 칸 이름은 `방식 문맥한도`다. 한도가 문맥을 바꾸지 않는 조건은 네 값이 같다. 근거가 있는 68문항 평균이다.", "",
             "- **Recall ③ 쪽+인용문**(그룹 단위): 정답 quote가 든 청크까지 가져왔는가. 이 보고서의 중심 지표",
             "- **Recall ② 쪽**(그룹 단위): 정답 쪽의 청크를 가져왔는가",
             "- **Recall ① 문서**(공식 정의): 근거 문서를 가져왔는가. 대안 문서를 모두 세므로 낮게 나온다",
             "- **밀려난 청크**: 문항당 평균, 상위 k개 중 문맥 한도 때문에 빠진 청크 수", ""]
        table("Recall ③ 쪽+인용문", "recall_pq")
        table("Recall ② 쪽", "recall_page")
        table("Recall ① 문서 (공식)", "recall_book")
        table("문항당 밀려난 청크 수", "n_drop", "{:.2f}")
        (out / "findings" / "recall_matrix.md").write_text("\n".join(F) + "\n", encoding="utf-8", newline="\n")

    write_findings()
    if a.only_findings:
        print(f"저장: {out / 'findings' / 'recall_matrix.md'}")
        return

    allc = {(z, p): eq.rechunk(z, p)[0] for z, p in conds}
    gold = {}  # (z, p) -> qid -> {chunk_id: [그룹]}
    for (z, p) in conds:
        gold[(z, p)] = {}
        for qid in qids:
            g = {}
            for gi, grp in enumerate([x for x in Q[qid].get("evidence_groups", []) if x], 1):
                for e in grp:
                    for cid, c in allc[(z, p)].items():
                        if c["book"] == e["book_id"] and c["page"] == e["page"] and eq.quote_in(c["text"], e["quote"]):
                            g.setdefault(cid, []).append(gi)
            gold[(z, p)][qid] = g

    # ---------- data/ ----------
    rows_f = open(out / "data" / "rows.jsonl", "w", encoding="utf-8", newline="\n")
    met_f = open(out / "data" / "metrics.csv", "w", encoding="utf-8", newline="")
    cw = csv.writer(met_f)
    cw.writerow(["qid", "expected", "size", "overlap_pct", "mode", "k", "ctx", "hit_book", "hit_page", "hit_pq", "recall_book", "recall_page", "recall_pq", "all_page", "all_pq",
                 "n_top", "n_used", "n_dropped", "status", "status_match", "input_tokens", "output_tokens", "llm_ms", "faithfulness"])
    retrieved_by = {}  # (z, p, cid) -> [(qid, mode)]
    for (z, p) in conds:
        Kmax = ks_of[p][0]
        ri = src(p, Kmax)
        for qid in qids:
            exp = Q[qid]["expected_action"]
            for m in MODES:
                row = R[(ri, z, p)]["modes"][m].get(qid)
                if not row:
                    continue
                top = row["top_ids"][:Kmax]
                kk = row["k"][str(Kmax)]["ctx"]
                for r_, cid in enumerate(top, 1):
                    ch = R[(ri, z, p)]["chunks"][cid]
                    rec = dict(qid=qid, size=z, overlap_pct=p, mode=m, rank=r_, chunk_id=cid, book_id=ch["book_id"], page=ch["page"], chars=len(ch["text"]),
                               is_gold=cid in gold[(z, p)][qid], first_k=next((k for k in sorted(ks_of[p]) if r_ <= k), Kmax))
                    for c in ctxs:
                        rec[f"used_{c}"] = cid in set(kk[str(c)]["ids"])
                    rows_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    retrieved_by.setdefault((z, p, cid), []).append((qid, m))
                for k in ks_of[p]:
                    rk = src(p, k)
                    rrow = R[(rk, z, p)]["modes"][m].get(qid)
                    if not rrow:
                        continue
                    for c in ctxs:
                        x = rrow["k"][str(k)]["ctx"][str(c)]
                        mm = x.get("m") or {}
                        rc = A.get((rk, z, p, m, qid, k, c))
                        cw.writerow([qid, exp, z, p, m, k, c, mm.get("hit"), mm.get("hit_page"), mm.get("hit_pq"), mm.get("recall_book"), mm.get("recall_page"), mm.get("recall_pq"),
                                     mm.get("all_page"), mm.get("all_pq"), rrow["k"][str(k)]["n_top"], x["n_used"], rrow["k"][str(k)]["n_top"] - x["n_used"],
                                     rc and rc["answer"]["status"], rc and rc["status_match"], rc and rc["input_tokens"], rc and rc["output_tokens"], rc and rc["llm_ms"],
                                     FA.get((rk, z, p, m, k, c, qid))])
    rows_f.close()
    met_f.close()
    (out / "data" / "schema.md").write_text("""# data/ 스키마

## rows.jsonl — 질문 × 청크 크기 × 오버랩 × 방식 × 순위 (한 줄이 청크 하나)
상위 청크는 가장 큰 k(11)까지만 저장한다. 작은 k의 상위는 앞부분(`rank <= k`)이다.

| 필드 | 뜻 |
|---|---|
| qid | 질문 id (`세트/문항`) |
| size, overlap_pct | 청크 글자 상한, 오버랩 % |
| mode | naive / hybrid / hybrid_rerank |
| rank | 검색 순위(1이 가장 위) |
| chunk_id, book_id, page, chars | 청크 id, 문서, 쪽, 글자 수 |
| is_gold | 이 청크가 정답 청크(골든 quote 앞 40자가 든 청크)인가 |
| first_k | 이 순위가 문맥에 들어가는 가장 작은 k (k가 이 값 이상이면 들어간다) |
| used_3000 … used_4200 | k=11에서 그 문맥 한도로 이 청크가 실제 문맥에 들어갔는가. 더 작은 k의 사용 여부는 `rank <= k` 이면서 `used_<한도>`이다(한도를 넘는 청크와 뒤 청크는 모두 빠진다) |

## metrics.csv — 질문 × 청크 크기 × 오버랩 × 방식 × k × 한도 (한 줄이 한 조건)
| 필드 | 뜻 |
|---|---|
| hit_book / hit_page / hit_pq | Hit: 문서 / 쪽 / 쪽+인용문을 하나라도 찾았는가 |
| recall_book / recall_page / recall_pq | Recall ①문서(공식) / ②쪽(그룹) / ③쪽+인용문(그룹) |
| all_page / all_pq | 모든 정답 그룹을 충족했는가 |
| n_top / n_used / n_dropped | 상위 k 개수 / 문맥에 들어간 개수 / 한도로 밀려난 개수 |
| status, status_match | LLM 답변 상태, 기대 동작과 같은가 |
| input_tokens, output_tokens, llm_ms | 답변 입력·출력 토큰, LLM 시간(병렬 호출 중 값, 부하가 섞임) |
| faithfulness | RAGAS faithfulness(3회 평균, 홀수 번째 36문항만, 없으면 빈칸) |

근거가 없는 질문(되묻기·보류)은 recall·hit·all 필드가 빈칸이다.
""", encoding="utf-8", newline="\n")

    # ---------- chunks/ ----------
    for (z, p) in conds:
        ri = src(p, ks_of[p][0])
        ch_all = R[(ri, z, p)]["chunks"]
        ids = sorted({cid for (zz, pp, cid) in retrieved_by if zz == z and pp == p})
        L = [f"# 청크 도감: {z}자 · 오버랩 {p}%", "", "[목록](../index.md) · 이 크기·오버랩으로 자른 청크 중 질문 검색에서 한 번이라도 상위 11개에 든 청크의 전문이다. 청크 id는 `<문서>-p<쪽>-c<쪽 안 번호>`다.", "",
             f"청크 {len(ids)}개", ""]
        gold_for = {}
        for qid in qids:
            for cid in gold[(z, p)][qid]:
                gold_for.setdefault(cid, []).append(qid)
        for cid in ids:
            c = ch_all.get(cid) or {"book_id": allc[(z, p)][cid]["book"], "page": allc[(z, p)][cid]["page"], "text": allc[(z, p)][cid]["text"]}
            by = retrieved_by[(z, p, cid)]
            L += [f'<a id="{cid}"></a>', f"### {cid}", "", f"- 문서 {c['book_id']} · {c['page']}쪽 · {len(c['text'])}자",
                  f"- 가져온 횟수: {len(by)}회(질문 × 방식), 질문 {len({q for q, _ in by})}개",
                  "- 정답 청크인 질문: " + (", ".join(gold_for[cid]) if cid in gold_for else "없음"), "", "> " + c["text"].replace("\n", "\n> "), ""]
        (out / "chunks" / f"size{z}_{ov(p)}.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ---------- questions/ ----------
    tags = {}
    for qid in qids:
        q = Q[qid]
        groups = [g for g in q.get("evidence_groups", []) if g]
        exp = q["expected_action"]
        L = [f"# {qid}", "", "[목록](../index.md) · [조건별 비교](../findings/recall_matrix.md)", "",
             "## 1. 질문과 정답", "", f"- **질문**: {q['question']}", f"- **기대 동작**: `{exp}` (answer = 답변, clarify = 되묻기, abstain = 보류)",
             f"- **골든 답변**: {q.get('reference_answer') or '-'}"]
        if q.get("required_facts"):
            L.append(f"- 필수 사실: {q['required_facts']}")
        if q.get("forbidden_claims"):
            L.append(f"- 금지 주장: {q['forbidden_claims']}")
        L.append("")
        if groups:
            L += ["| 그룹 | book_id | 쪽 | quote |", "|---|---|---|---|"]
            for gi, g in enumerate(groups, 1):
                for e in g:
                    L.append(f"| {gi} | {e['book_id']} | {e['page']} | {esc(e['quote'][:100])}{'…' if len(e['quote']) > 100 else ''} |")
            L += ["", "그룹 안은 대안이다(하나만 찾으면 그 그룹 충족)."]
        else:
            L.append("근거가 없는 유형(되묻기·보류)이라 정답 청크가 없다. LLM의 동작이 기대와 같은지만 본다.")
        L.append("")

        # 2. 조건별 요약: k마다 (오버랩, 크기) × 방식
        L += ["## 2. 조건별 요약 (문맥 한도 3000 → 4200)", "", "칸: `근거 3000/4200 · 밀려난 청크 3000/4200 · 답 3000/4200`. 근거 ✅ = 정답 그룹을 모두 찾음, `-` = 근거 없는 질문.", ""]
        any_eff, any_hit, dropped_gold = False, False, False
        lo, hi = min(ctxs), max(ctxs)
        for k in sorted({k for p in pcts for k in ks_of[p]}, reverse=True):
            L += [f"### k = {k}", "", "| 오버랩 | 크기 | " + " | ".join(MODES) + " |", "|---|---|---|---|---|"]
            for (z, p) in conds:
                if k not in ks_of[p]:
                    continue
                rk = src(p, k)
                cs = []
                for m in MODES:
                    rrow = R[(rk, z, p)]["modes"][m].get(qid)
                    if not rrow:
                        cs.append("-")
                        continue
                    kk = rrow["k"][str(k)]["ctx"]
                    m3, m4 = kk[str(lo)].get("m"), kk[str(hi)].get("m")
                    d3, d4 = rrow["k"][str(k)]["n_top"] - kk[str(lo)]["n_used"], rrow["k"][str(k)]["n_top"] - kk[str(hi)]["n_used"]
                    a3, a4 = A.get((rk, z, p, m, qid, k, lo)), A.get((rk, z, p, m, qid, k, hi))
                    cs.append(f"{ok(m3 and m3['all_pq'])}/{ok(m4 and m4['all_pq'])} · 밀림 {d3}/{d4} · 답 {ok(a3 and a3['status_match'])}/{ok(a4 and a4['status_match'])}")
                    any_eff |= bool(m3 and m4 and m3["recall_pq"] != m4["recall_pq"])
                    any_hit |= bool(m4 and m4["hit_pq"])
                    dropped_gold |= bool(m3 and m4 and m4["recall_pq"] > m3["recall_pq"])
                L.append(f"| {p}% | {z}자 | " + " | ".join(cs) + " |")
            L.append("")
        tags[qid] = dict(exp=exp, groups=bool(groups), effect=any_eff, dropped_gold=dropped_gold, never=bool(groups) and not any_hit)

        # 3. 청크 × 방식 순위표 (오버랩·크기마다)
        L += ["## 3. 가져온 청크 (오버랩 · 청크 크기별)", "",
              "표 하나가 오버랩·크기 하나다. 행은 청크, 칸은 그 방식이 그 청크를 **몇 위**로 가져왔는지다(`·` = 상위 11개에 없음). 한도 3000에서 밀려나면 `❌`. 순위가 k 이하이면 그 k에서 문맥에 들어가는 후보다. 청크 id를 누르면 도감(전문)으로 간다.", ""]
        for (z, p) in conds:
            Kmax = ks_of[p][0]
            ri = src(p, Kmax)
            gz = gold[(z, p)][qid]
            L += [f"### 오버랩 {p}% · {z}자", ""]
            if groups:
                L += ["정답 청크: " + (", ".join(f"`{c}`(그룹 {','.join(map(str, g))})" for c, g in gz.items()) or "없음 (quote 앞 40자가 한 청크 안에 없다: 청크 경계에서 잘림)"), ""]
            rk_ = {}
            for m in MODES:
                row = R[(ri, z, p)]["modes"][m].get(qid)
                if not row:
                    continue
                cut = row["k"][str(Kmax)]["ctx"][str(lo)]["ids"]
                for r_, cid in enumerate(row["top_ids"][:Kmax], 1):
                    rk_.setdefault(cid, {})[m] = (r_, cid not in set(cut))
            order = sorted(rk_, key=lambda c: (min(v[0] for v in rk_[c].values()), c))
            L += ["| 청크 | 쪽 | 정답 | naive | hybrid | hybrid_rerank | 미리보기 |", "|---|---|---|---|---|---|---|"]
            for cid in order:
                ch = R[(ri, z, p)]["chunks"][cid]
                cells = []
                for m in MODES:
                    v = rk_[cid].get(m)
                    cells.append("·" if not v else (f"❌{v[0]}" if v[1] else str(v[0])))
                L.append(f"| [`{cid}`](../chunks/size{z}_{ov(p)}.md#{cid}) | {ch['book_id']} {ch['page']}쪽 | {'★' if cid in gz else ''} | " + " | ".join(cells) + f" | {pv(ch)} |")
            missed = [c for c in gz if c not in rk_]
            if missed:
                L.append(f"\n상위 {Kmax}개 어디에도 없는 정답 청크(놓침): " + ", ".join(f"[`{c}`](../chunks/size{z}_{ov(p)}.md#{c})" if (z, p, c) in retrieved_by else f"`{c}`" for c in missed))
            L.append("")

        # 4. 답변 비교
        L += ["## 4. LLM 답변과 골든 답변 비교", "", f"골든 답변: {q.get('reference_answer') or '-'}", ""]
        for (z, p) in conds:
            parts = []
            for k in sorted({ks_of[p][0], ks_of[p][-1]}, reverse=True):
                rk = src(p, k)
                for m in MODES:
                    for c in (lo, hi):
                        x = A.get((rk, z, p, m, qid, k, c))
                        if x:
                            an = x["answer"]
                            parts.append(f"- **k={k} · {m} · 한도 {c}** ({ok(x['status_match'])} `{an['status']}`, 입력 {x['input_tokens']} / 출력 {x['output_tokens']}토큰): {esc(an.get('answer') or '-')}")
            if parts:
                L += [f"<details><summary>오버랩 {p}% · {z}자</summary>", ""] + parts + ["", "</details>", ""]
        fn = qid.replace("/", "_") + ".md"
        (out / "questions" / fn).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ---------- index ----------
    n_eff = sum(t["effect"] for t in tags.values())
    I = ["# 문맥 한도 실험 종합 보고서 (초안)", "",
         f"- 청크 크기 {', '.join(map(str, sizes))}자 · 오버랩 {', '.join(f'{p}%' for p in pcts)} · 문맥 한도 {', '.join(map(str, ctxs))}토큰 · 방식 naive / hybrid / hybrid_rerank · 질문 {len(qids)}개",
         "- 자료: " + ", ".join(f"{r['name']}(오버랩 {','.join(map(str, r['pcts']))}%, k {','.join(map(str, r['ks']))})" for r in runs), "",
         "## 목차", "",
         "1. [가장 좋은 조건 Top 10 (요약)](findings/top10.md): 기준, 확정값 대비, Top 10 두 가지(Recall 순 / 비용을 함께 본 순), 방식별 1위",
         "2. [조건별 Recall](findings/recall_matrix.md): 오버랩 × 크기 × 방식 × 한도 4개(3000·3400·3800·4200)",
         "3. [지연 시간](findings/latency.md): 검색 시간, 검색 내부 단계, 답변 LLM 시간, 직렬 전체 시간",
         "4. [질문 목록](#질문-목록) → `questions/`: 질문 하나의 정답, 가져온 청크, 밀려난 청크, 답변",
         "5. [청크 도감](chunks/): 청크 전문(크기 × 오버랩마다 한 파일)",
         "6. [분석용 원자료](data/schema.md): `rows.jsonl`, `metrics.csv`", "",
         "## 문서 안내 (무엇을 보려면 어디로)", "", "| 보고 싶은 것 | 문서 |", "|---|---|",
         "| **어떤 조건이 가장 좋은가 (Top 10)** | [findings/top10.md](findings/top10.md) |",
         "| 지연 시간(검색 / LLM 답변 / 직렬 전체) | [findings/latency.md](findings/latency.md) |",
         "| 조건이 바뀌면 Recall이 어떻게 달라지나 | [findings/recall_matrix.md](findings/recall_matrix.md) |",
         "| 질문 하나가 조건마다 어떻게 나왔나(정답, 가져온 청크, 밀려난 청크, 답변) | 아래 질문 목록 → `questions/` |",
         "| 청크 내용(전문) | [chunks/](chunks/) 크기·오버랩마다 한 파일 |",
         "| 분석용 원자료(엑셀·AI) | [data/schema.md](data/schema.md), `data/rows.jsonl`, `data/metrics.csv` |", "",
         "## 조건 매핑", "", "| 오버랩 | k | 실험 폴더 |", "|---|---|---|"]
    for p in pcts:
        for k in ks_of[p]:
            I.append(f"| {p}% | {k} | {runs[src(p, k)]['name']} |")
    plan_k = {"0020": "11·5", "0021": "10·6", "0022": "9·7", "0023": "8"}
    I += ["", "## 실험별 현황", "", "| 실험 | k | 오버랩 0% | 오버랩 10·20% | 비고 |", "|---|---|---|---|---|"]
    for ex, kk_ in plan_k.items():
        z0 = [r["name"] for r in runs if f"exp{ex}" in r["name"] and r["pcts"] == [0]]
        zo = [r["name"] for r in runs if f"exp{ex}" in r["name"] and 0 not in r["pcts"]]
        note = "" if (z0 or zo) else "결과 없음(이 보고서에 포함되지 않음)"
        I.append(f"| EXP-{ex} | {kk_} | {', '.join(z0) or '-'} | {', '.join(zo) or '-'} | {note} |")
    I += ["", "- 오버랩 10·20% 실행 중 EXP-0022(k=9·7)와 EXP-0023(k=8)은 검색·답변 단계까지만 있어 faithfulness와 직렬 전체 시간이 없다. 오버랩의 직렬 전체 시간(e2e)은 어느 k에서도 측정하지 않았다.", "",
          f"## 질문 목록 ({len(qids)}개; 한도에 따라 결과가 달라진 질문 {n_eff}개)", "",
          "표시: **한도 효과** = 문맥 한도 3000과 4200에서 Recall이 달라지는 조건이 있음 · **한도로 놓침** = 한도를 올리면 근거를 더 찾는 조건이 있음 · **못 찾음** = 어느 조건에서도 정답 청크(쪽+인용문)를 하나도 못 가져옴", "",
          "| 질문 | 기대 | 질문 글 | 표시 | 파일 |", "|---|---|---|---|---|"]
    for qid in qids:
        t = tags[qid]
        flags = ", ".join(x for x, c in (("한도 효과", t["effect"]), ("한도로 놓침", t["dropped_gold"]), ("못 찾음", t["never"])) if c) or "-"
        fn = qid.replace("/", "_") + ".md"
        I.append(f"| {qid} | {t['exp']} | {esc(Q[qid]['question'][:50])}{'…' if len(Q[qid]['question']) > 50 else ''} | {flags} | [{fn}](questions/{fn}) |")
    (out / "index.md").write_text("\n".join(I) + "\n", encoding="utf-8", newline="\n")
    print(f"저장: {out} (질문 {len(qids)}개, 조건 {len(conds)}개, 청크 도감 {len(conds)}개)")


if __name__ == "__main__":
    main()
