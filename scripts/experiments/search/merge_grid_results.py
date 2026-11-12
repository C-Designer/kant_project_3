"""grid_kset.py 결과 폴더 여러 개(담당별)를 합쳐 최적의 k·청크 크기·오버랩을 고르는 표를 만든다 (EXP-0016~0019).

    uv run python scripts/experiments/search/merge_grid_results.py --in results/exp0016/laptop1 results/exp0017/laptop2 ... --out results/merged

만드는 것: merged.md(표), merged.json(숫자 전부). 값을 만들어내지 않고 폴더에 있는 값만 모은다. 없는 칸은 "-".
- 같은 (크기, 오버랩, 방식, k)가 여러 폴더에 있으면(확정값 900자·0%·k=5는 모든 담당이 잼) 검색 지표가 서로 같은지 확인하고 다르면 경고한다.
- 시간은 노트북마다 다를 수 있어 합치지 않고 폴더별로 따로 적는다.
- 후보 판정은 계획 문서의 사전 기준 중 1(Recall 둘 다 +.03), 2(행동 일치율), 3의 토큰 부분만 자동으로 본다. 전체 시간·RAGAS는 표를 보고 사람이 판단한다.
"""
import argparse
import json
import statistics as st
from pathlib import Path

MODES = ("naive", "hybrid", "hybrid_rerank")
BASE = (900, 0, 5)
EV_DIR = Path(__file__).resolve().parents[3] / "data" / "shipping" / "evaluation"


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inputs", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--doc", help="계획 문서(docs/experiments/search/00NN-*.md). 주면 '## 결과' 칸을 표로 채우고 상태를 '실행 중'으로 바꾼다")
    return p.parse_args()


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def pct95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * 0.95))] if xs else None


def f(x, d=3):
    return "-" if x is None else f"{x:.{d}f}"


def expected_actions():
    out = {}
    for s in ("development", "additional", "expansion_validation"):
        p = EV_DIR / f"{s}.json"
        if p.exists():
            for a in load(p):
                out[f"{s}/{a['id']}"] = a["expected_action"]
    return out


def fill_doc(doc, lines, dirs, R, E2E):
    """계획 문서의 '## 결과' 칸(다음 '## 해석·한계' 앞까지)을 합친 표로 바꾼다. 해석·결정은 사람이나 AI가 쓰고 상태를 '완료'로 바꾼다."""
    text = doc.read_text(encoding="utf-8")
    i, j = text.index("\n## 결과\n") + 1, text.index("\n## 해석·한계\n") + 1  # 줄 전체로 찾는다("### 결과가..." 제목과 헷갈리지 않게)
    body = []
    for ln in lines[2:]:  # 제목·입력 폴더 줄 제외. 문서 안에서는 한 단계 낮춘 제목을 쓴다
        body.append("#" + ln if ln.startswith("#") else ln)
    head = "## 결과\n\n원자료: " + ", ".join(f"`{d}`" for d in dirs) + " (저장소에 올리지 않음). 아래 표는 `merge_grid_results.py`가 자동으로 만들었다.\n\n"
    text = text[:i] + head + "\n".join(body) + "\n\n" + text[j:]
    errs = sum(v["act"]["errors"] for v in R.values() if "act" in v)
    e2e_err = sum(v["err"] for k, v in E2E.items() if len(k) == 3)
    line = f"- 실패한 실행(`status=\"error\"`)과 원인: 답변 단계 오류 레코드 {errs}건, 직렬 단계 오류 {e2e_err}건 (원인별 분류는 원자료 `answers/*.json`의 `error`). 자동 집계이며 원인 설명은 사람이 덧붙인다"
    text = "\n".join(line if ln.startswith("- 실패한 실행") else ln for ln in text.split("\n"))
    text = text.replace("- 상태: 계획", "- 상태: 실행 중", 1)
    doc.write_text(text, encoding="utf-8", newline="\n")
    print(f"문서 갱신: {doc} (결과 칸 채움, 상태 '실행 중'. 해석·결정을 쓴 뒤 '완료'로 바꾸고 README 행을 갱신한다)")


def main():
    A = parse()
    dirs = [Path(x) for x in A.inputs]
    EXP = expected_actions()
    warn = []
    R = {}  # (size,pct,mode,k) -> dict
    T = {}  # (size,pct,mode) -> [retrieval_s]
    for d in dirs:
        for rp in sorted((d / "retrieval").glob("*.json")):
            r = load(rp)
            for mode, rows in r["modes"].items():
                key_t = (r["size"], r["pct"], mode)
                T.setdefault(key_t, {})[d.name if d.name != "." else str(d)] = [v["retrieval_s"] for v in rows.values()]
                for k in r["ks"]:
                    ms = [v["k"][str(k)]["m"] for v in rows.values()]
                    ms = [m for m in ms if m]
                    cell = dict(
                        n=len(ms), chunks=r["chunks_total"],
                        recall_book=mean([m["recall_book"] for m in ms]), hit=mean([m["hit"] for m in ms]),
                        recall_pq=mean([m["recall_pq"] for m in ms]), all_pq=mean([m["all_pq"] for m in ms]),
                        all_book=mean([m["all_book"] for m in ms]),
                        n_used=mean([v["k"][str(k)]["n_used"] for v in rows.values()]),
                        tok_sum=mean([v["k"][str(k)]["tok_sum"] for v in rows.values()]),
                    )
                    key = (r["size"], r["pct"], mode, k)
                    if key in R and any(abs((R[key][x] or 0) - (cell[x] or 0)) > 1e-9 for x in ("recall_book", "recall_pq", "hit")):
                        warn.append(f"검색 지표가 폴더 사이에 다르다: {key} ({d})")
                    R.setdefault(key, cell)
    for d in dirs:
        for ap in sorted((d / "answers").glob("*.json")):
            a = load(ap)
            by = {}
            for rec in a["records"]:
                by.setdefault((a["size"], a["pct"], rec["mode"], rec["k"]), []).append(rec)
            for key, recs in by.items():
                if key not in R or "act" in R[key]:
                    continue
                ok = [x for x in recs if x.get("answer")]
                typ = lambda t: mean([x["status_match"] for x in ok if EXP.get(x["qid"]) == t])  # noqa: E731
                R[key]["act"] = dict(
                    n=len(recs), errors=len(recs) - len(ok), match=mean([x["status_match"] for x in ok]),
                    match_answer=typ("answer"), match_clarify=typ("clarify"), match_abstain=typ("abstain"),
                    cites=mean([x["cites_gold_doc"] for x in ok if "cites_gold_doc" in x]),
                    tin=mean([x["input_tokens"] for x in ok]), tout=mean([x["output_tokens"] for x in ok]),
                    llm_s=mean([x["llm_ms"] / 1000 for x in ok if x.get("llm_ms") is not None]),
                    regen=mean([x.get("llm_calls", 1) > 1 for x in ok]),
                )
    E2E = {}
    for d in dirs:
        for ep in sorted((d / "e2e").glob("*.json")):
            e = load(ep)
            if ep.name.startswith("anchor"):
                rows = [x for x in e["rows"] if not x.get("error")]
                E2E[(d.name, ep.stem)] = dict(mean=mean([x["total_s"] for x in rows]), median=st.median([x["total_s"] for x in rows]) if rows else None, at=e["run_at"], n=len(rows))
                continue
            for k, rows in e["rows"].items():
                ok = [x for x in rows if not x.get("error")]
                tot = [x["total_s"] for x in ok]
                E2E[(d.name, e["size"], int(k))] = dict(
                    n=len(ok), err=len(rows) - len(ok), mean=mean(tot), median=st.median(tot) if tot else None, p95=pct95(tot),
                    retr=mean([x["retrieval_s"] for x in ok]), ctx=mean([x["context_s"] for x in ok]), llm=mean([x["llm_s"] for x in ok]),
                    tin=mean([x["input_tokens"] for x in ok]), tout=mean([x["output_tokens"] for x in ok]))
    G = {}
    for d in dirs:
        for gp in sorted((d / "ragas").glob("*.json")):
            g = load(gp)
            res = g["results"]
            G[(g["size"], g["pct"], g["mode"], g["k"])] = dict(
                n=g["n"], faithfulness=mean([x["faithfulness"] for x in res]),
                tokens_in=mean([x["tokens_in"] for x in res]), tokens_out=mean([x["tokens_out"] for x in res]))

    sizes = sorted({k[0] for k in R})
    pcts = sorted({k[1] for k in R})
    ks = sorted({k[3] for k in R})
    L = ["# 격자 실험 합친 결과 (EXP-0016~0019)\n", f"입력 폴더 {len(dirs)}개: " + ", ".join(str(d) for d in dirs) + "\n"]
    for w in warn:
        L.append(f"> 경고: {w}\n")
    envs = [(d, load(d / "env.json")) for d in dirs if (d / "env.json").exists()]
    if envs:
        L += ["## 실행 환경(노트북별)\n", "| 폴더 | GPU | torch | 스레드 | 문항 제한 | 실행 시각 | git |", "|---|---|---|---|---|---|---|"]
        L += [f"| {d} | {e.get('gpu')} | {e.get('torch')} | {e.get('threads')} | {e.get('limit_q')} | {e.get('run_at')} | {e.get('git_commit')}{' (src 수정됨)' if e.get('git_dirty') else ''} |" for d, e in envs]
        L.append("")

    def table(title, getter, d=3):
        for mode in MODES:
            L.append(f"### {title} - {mode} (행 = 크기/오버랩%, 열 = k)\n")
            L.extend(["| 크기 / 오버랩 | " + " | ".join(f"k={k}" for k in ks) + " |", "|---|" + "---|" * len(ks)])  # 함수 안이라 `+=`는 L을 지역 변수로 만든다
            for z in sizes:
                for p in pcts:
                    cells = [getter(R.get((z, p, mode, k)), (z, p, mode, k)) for k in ks]
                    if any(c is not None for c in cells):
                        L.append(f"| {z} / {p}% | " + " | ".join(f(c, d) for c in cells) + " |")
            L.append("")

    L.append("## 검색 (근거 있는 문항 기준, raw top-k가 아니라 3000토큰 한도에 들어간 앞부분)\n")
    table("Recall@k (book_id)", lambda c, _: c and c["recall_book"])
    table("Recall@k (page+quote, 그룹 단위)", lambda c, _: c and c["recall_pq"])
    table("Hit@k", lambda c, _: c and c["hit"])
    table("모든그룹 충족률 (page+quote)", lambda c, _: c and c["all_pq"])
    table("3000토큰 한도에 들어간 청크 수(평균)", lambda c, _: c and c["n_used"], 2)
    L.append("## 답변 품질 (행동 일치율·토큰은 병렬 호출, RAGAS는 faithfulness만)\n")
    table("답변 행동 일치율(전체)", lambda c, _: c and c.get("act", {}).get("match"))
    table("답변 유형 일치율", lambda c, _: c and c.get("act", {}).get("match_answer"))
    table("되묻기 유형 일치율", lambda c, _: c and c.get("act", {}).get("match_clarify"))
    table("보류 유형 일치율", lambda c, _: c and c.get("act", {}).get("match_abstain"))
    table("근거 문서 인용률", lambda c, _: c and c.get("act", {}).get("cites"))
    table("입력 토큰 평균", lambda c, _: c and c.get("act", {}).get("tin"), 0)
    table("출력 토큰 평균", lambda c, _: c and c.get("act", {}).get("tout"), 0)
    table("재생성한 문항 비율(LLM 호출 2회 이상)", lambda c, _: c and c.get("act", {}).get("regen"))
    table("병렬 답변 호출 LLM 시간 평균(초, 24병렬 부하 중 값)", lambda c, _: c and c.get("act", {}).get("llm_s"), 2)
    if G:
        L += ["### RAGAS faithfulness (홀수 번째 36문항, 3회 평균)\n", "| 방식 | 크기 / 오버랩 | k | n | faithfulness |", "|---|---|---|---|---|"]
        for (z, p, m, k), v in sorted(G.items(), key=lambda x: (MODES.index(x[0][2]), x[0][0], x[0][3])):
            L.append(f"| {m} | {z} / {p}% | {k} | {v['n']} | {f(v['faithfulness'])} |")
        L.append("")

    L += ["## 운영 지표 (노트북별로 따로 적는다)\n", "### 검색 시간(retrieve() 한 번, k=11, 초) - 노트북 폴더별\n", "| 방식 | 크기 / 오버랩 | 폴더 | 평균 | 중앙값 | p95 |", "|---|---|---|---|---|---|"]
    for (z, p, m), per in sorted(T.items(), key=lambda x: (MODES.index(x[0][2]), x[0][0], x[0][1])):
        for d, xs in per.items():
            L.append(f"| {m} | {z} / {p}% | {d} | {f(st.mean(xs), 4)} | {f(st.median(xs), 4)} | {f(pct95(xs), 4)} |")
    L.append("")
    if E2E:
        L += ["### 전체 시간(retrieve~LLM 답변, 직렬, hybrid_rerank, 초) - 노트북 폴더별\n", "| 폴더 | 크기 | k | n(오류) | 평균 | 중앙값 | p95 | 검색 | 문맥 | LLM | 입력 토큰 | 출력 토큰 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for key, v in sorted(k_ for k_ in E2E.items() if len(k_[0]) == 3):
            L.append(f"| {key[0]} | {key[1]} | {key[2]} | {v['n']}({v['err']}) | {f(v['mean'], 2)} | {f(v['median'], 2)} | {f(v['p95'], 2)} | {f(v['retr'], 3)} | {f(v['ctx'], 4)} | {f(v['llm'], 2)} | {f(v['tin'], 0)} | {f(v['tout'], 0)} |")
        L += ["", "### 공통 기준점(500자·0%·hybrid_rerank·k=10) - 노트북 사이 비교와 시간대 흔들림\n", "| 폴더 | 시점 | 시각 | n | 평균 | 중앙값 |", "|---|---|---|---|---|---|"]
        for key, v in sorted(k_ for k_ in E2E.items() if len(k_[0]) == 2):
            L.append(f"| {key[0]} | {key[1]} | {v['at']} | {v['n']} | {f(v['mean'], 2)} | {f(v['median'], 2)} |")
        L.append("")
    L += ["## 확정값(900자·0%·k=5) 대비 후보 (사전 기준 1·2·토큰만 자동 판정)\n", "| 방식 | 크기 / 오버랩 | k | ΔRecall(book) | ΔRecall(p+q) | Δ행동 일치율 | 입력 토큰 비 | 후보 |", "|---|---|---|---|---|---|---|---|"]
    cand = []
    for mode in MODES:
        b = R.get((*BASE[:2], mode, BASE[2]))
        if not b or "act" not in b:
            continue
        for (z, p, m, k), c in sorted(R.items()):
            if m != mode or "act" not in c or (z, p, k) == BASE:
                continue
            db, dq = c["recall_book"] - b["recall_book"], c["recall_pq"] - b["recall_pq"]
            da = c["act"]["match"] - b["act"]["match"]
            ratio = c["act"]["tin"] / b["act"]["tin"] if b["act"]["tin"] else None
            ok = db >= 0.03 and dq >= 0.03 and da >= -0.02 and (ratio is None or ratio <= 1.5)
            for t in ("match_clarify", "match_abstain"):
                if c["act"][t] is not None and b["act"][t] is not None and c["act"][t] < b["act"][t]:
                    ok = False
            L.append(f"| {m} | {z} / {p}% | {k} | {db:+.3f} | {dq:+.3f} | {da:+.3f} | {f(ratio, 2)} | {'후보' if ok else ''} |")
            if ok:
                cand.append(dict(mode=m, size=z, pct=p, k=k, d_book=db, d_pq=dq, d_act=da))
    L.append(f"\n후보 {len(cand)}개. 전체 시간·RAGAS 기준(사전 기준 3·4)은 위 표로 직접 확인한다.\n")

    if A.doc:
        fill_doc(Path(A.doc), L, dirs, R, E2E)
    out = Path(A.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "merged.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    ser = lambda t: {"|".join(map(str, k)) if isinstance(k, tuple) else k: v for k, v in t.items()}  # noqa: E731
    (out / "merged.json").write_text(json.dumps(dict(retrieval=ser(R), e2e=ser(E2E), ragas=ser(G), candidates=cand, warnings=warn), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"저장: {out / 'merged.md'} (설정 {len(R)}개, 후보 {len(cand)}개, 경고 {len(warn)}개)")


if __name__ == "__main__":
    main()
