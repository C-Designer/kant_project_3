"""grid_kset.py 결과 폴더 여러 개(담당별)를 합쳐 최적의 k·청크 크기·오버랩·문맥 한도를 고르는 표를 만든다.

    uv run python scripts/experiments/search/merge_grid_results.py --in results/<실험>/laptop1 results/<실험>/laptop2 ... --out results/merged

만드는 것: merged.md(표), merged.json(숫자 전부). 값을 만들어내지 않고 폴더에 있는 값만 모은다. 없는 칸은 "-".
- 같은 (크기, 오버랩, 한도, 방식, k)가 여러 폴더에 있으면(확정값 900자·0%·k=5는 모든 담당이 잼) 검색 지표가 서로 같은지 확인하고 다르면 경고한다.
- 시간은 노트북마다 다를 수 있어 합치지 않고 폴더별로 따로 적는다.
- 후보 판정은 계획 문서의 사전 기준 중 1(Recall 둘 다 +.03), 2(행동 일치율), 3의 토큰 부분만 자동으로 본다. 전체 시간·RAGAS는 표를 보고 사람이 판단한다.
- `--doc 계획문서.md`를 주면 그 문서의 '## 결과' 칸을 표로 채우고 상태를 '실행 중'으로 바꾼다.
"""
import argparse
import json
import statistics as st
from pathlib import Path

MODES = ("naive", "hybrid", "hybrid_rerank")
BASE = (900, 0, 5)  # 확정값: 크기, 오버랩%, k (한도는 3000)
BASE_CTX = 3000
EV_DIR = Path(__file__).resolve().parents[3] / "data" / "shipping" / "evaluation"


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inputs", nargs="+", required=True)
    p.add_argument("--out", help="기본: 첫 결과 폴더 안의 report/ (노트북 여러 개를 합칠 때는 따로 지정)")
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
    e2e_err = sum(v["err"] for k, v in E2E.items() if len(k) == 5)
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
    R = {}  # (size,pct,ctx,mode,k) -> dict
    T = {}  # (size,pct,mode) -> {폴더: [retrieval_s]}
    for d in dirs:
        for rp in sorted((d / "retrieval").glob("*.json")):
            r = load(rp)
            for mode, rows in r["modes"].items():
                T.setdefault((r["size"], r["pct"], mode), {})[d.name if d.name != "." else str(d)] = [v["retrieval_s"] for v in rows.values()]
                for k in r["ks"]:
                    for lim in r["ctxs"]:
                        cells = [(v["k"][str(k)]["ctx"][str(lim)], v["k"][str(k)]) for v in rows.values()]
                        ms = [c["m"] for c, _ in cells if c["m"]]
                        cell = dict(
                            n=len(ms), chunks=r["chunks_total"],
                            recall_book=mean([m["recall_book"] for m in ms]), hit=mean([m["hit"] for m in ms]),
                            hit_page=mean([m.get("hit_page") for m in ms]), hit_pq=mean([m.get("hit_pq") for m in ms]),
                            recall_page=mean([m.get("recall_page") for m in ms]), all_page=mean([m.get("all_page") for m in ms]),
                            recall_pq=mean([m["recall_pq"] for m in ms]), all_pq=mean([m["all_pq"] for m in ms]),
                            all_book=mean([m["all_book"] for m in ms]),
                            n_used=mean([c["n_used"] for c, _ in cells]),
                            n_drop=mean([kk["n_top"] - c["n_used"] for c, kk in cells]),
                            n_trunc=sum(1 for c, kk in cells if kk["n_top"] > c["n_used"]), n_q=len(cells),
                            tok_sum=mean([kk["tok_sum"] for _, kk in cells]),
                        )
                        key = (r["size"], r["pct"], lim, mode, k)
                        if key in R and any(abs((R[key][x] or 0) - (cell[x] or 0)) > 1e-9 for x in ("recall_book", "recall_pq", "hit")):
                            warn.append(f"검색 지표가 폴더 사이에 다르다: {key} ({d})")
                        R.setdefault(key, cell)
    for d in dirs:
        for ap in sorted((d / "answers").glob("*.json")):
            a = load(ap)
            by = {}
            for rec in a["records"]:
                by.setdefault((a["size"], a["pct"], rec["ctx"], rec["mode"], rec["k"]), []).append(rec)
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
    E2E = {}  # (폴더, 크기, k, 한도) -> 집계, (폴더, 'anchor_*') -> 집계
    DIFF = {}  # (폴더, 크기, k, 한도) -> 문맥이 달라진 문항만: 이 한도의 시간 vs 가장 큰 한도의 시간
    for d in dirs:
        for ep in sorted((d / "e2e").glob("*.json")):
            e = load(ep)
            if ep.name.startswith("anchor"):
                rows = [x for x in e["rows"] if not x["ctx"]["3000"].get("error")]
                tot = [x["ctx"]["3000"]["total_s"] for x in rows]
                E2E[(d.name, ep.stem)] = dict(mean=mean(tot), median=st.median(tot) if tot else None, at=e["run_at"], n=len(rows))
                continue
            lims = sorted(e["ctxs"], reverse=True)
            for mode, by_k in e["modes"].items():
                for k, rows in by_k.items():
                    for lim in lims:
                        eff, redo = [], []
                        for x in rows:
                            c = x["ctx"][str(lim)]
                            src = x["ctx"][str(c["same_as"])] if "same_as" in c else c  # 문맥이 같으면 큰 한도의 값을 그대로 쓴다
                            if src.get("error"):
                                continue
                            eff.append(dict(src, retrieval_s=x["retrieval_s"]))
                            if "same_as" not in c and lim != lims[0]:
                                redo.append((c, x["ctx"][str(lims[0])]))
                        tot = [x["total_s"] for x in eff]
                        E2E[(d.name, e["size"], int(k), lim, mode)] = dict(
                            n=len(eff), err=len(rows) - len(eff), mean=mean(tot), median=st.median(tot) if tot else None, p95=pct95(tot),
                            retr=mean([x["retrieval_s"] for x in eff]), ctx=mean([x["context_s"] for x in eff]) if eff and "context_s" in eff[0] else None,
                            llm=mean([x["llm_s"] for x in eff]), llm_med=st.median([x["llm_s"] for x in eff]) if eff else None,
                            tin=mean([x.get("input_tokens") for x in eff]), tout=mean([x.get("output_tokens") for x in eff]), redo=len(redo))
                        if redo:
                            DIFF[(d.name, e["size"], int(k), lim, mode)] = dict(n=len(redo), at_lim=mean([c["total_s"] for c, _ in redo]), at_max=mean([m["total_s"] for _, m in redo]),
                                                                                 tin_lim=mean([c.get("input_tokens") for c, _ in redo]), tin_max=mean([m.get("input_tokens") for _, m in redo]))
    # 검색 내부 단계 시간(retrieve()와 같은 연산을 한 번 더 돌려 잰 값): (크기, 오버랩, 방식) -> 단계별 평균 ms
    STG = {}
    for d in dirs:
        for rp in sorted((d / "retrieval").glob("*.json")):
            r = load(rp)
            for mode, rows in r["modes"].items():
                per = {}
                for v in rows.values():
                    for s_, ms_ in v["stages"].get("stage_ms", {}).items():
                        per.setdefault(s_, []).append(ms_)
                if per:
                    STG[(r["size"], r["pct"], mode)] = {s_: mean(v) for s_, v in per.items()}
    G = {}  # (size,pct,ctx,mode,k) -> faithfulness
    for d in dirs:
        for gp in sorted((d / "ragas").glob("*.json")):
            g = load(gp)
            for lim, v in g["by_ctx"].items():
                res = v["results"]
                G[(g["size"], g["pct"], int(lim), g["mode"], g["k"])] = dict(
                    n=len(res), faithfulness=mean([x["faithfulness"] for x in res]),
                    tokens_in=mean([x["tokens_in"] for x in res]), tokens_out=mean([x["tokens_out"] for x in res]))

    sizes = sorted({k[0] for k in R})
    pcts = sorted({k[1] for k in R})
    ctxs = sorted({k[2] for k in R}, reverse=True)
    ks = sorted({k[4] for k in R})
    rowkeys = [(z, p, c) for z in sizes for p in pcts for c in ctxs]
    label = lambda z, p, c: f"{z}" + (f" / {p}%" if len(pcts) > 1 else "") + (f" / 한도 {c}" if len(ctxs) > 1 else "")  # noqa: E731
    head = "행 = 크기" + ("/오버랩%" if len(pcts) > 1 else "") + ("/문맥 한도" if len(ctxs) > 1 else "") + ", 열 = k"
    L = ["# 격자 실험 합친 결과\n", f"입력 폴더 {len(dirs)}개: " + ", ".join(str(d) for d in dirs) + "\n"]
    for w in warn:
        L.append(f"> 경고: {w}\n")
    envs = [(d, load(d / "env.json")) for d in dirs if (d / "env.json").exists()]
    if envs:
        L += ["## 실행 환경(노트북별, computing_env)\n", "| 폴더 | CPU | RAM(GB) | GPU | torch | 스레드 | 전원 | 한도 | 방식 | 문항 제한 | 실행 시각 | git |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        L += [f"| {d} | {e.get('cpu_name') or e.get('cpu')} | {e.get('ram_total_gb')} | {e.get('gpu')} | {e.get('torch')} | {e.get('threads')} | {e.get('power_plan') or '-'} (AC {e.get('on_ac_power')}) | {e.get('context_max', [3000])} | {','.join(e.get('modes', MODES))} | {e.get('limit_q')} | {e.get('run_at')} | {e.get('git_commit')}{' (src 수정됨)' if e.get('git_dirty') else ''} |" for d, e in envs]
        L.append("")
        # 노트북 사이 컴퓨팅 환경이 같은지: 시간 비교는 같은 환경일 때만 의미가 있다
        def flat(d, pre=""):
            out_ = {}
            for k_, v in d.items():
                if isinstance(v, dict):
                    out_.update(flat(v, f"{pre}{k_}."))
                else:
                    out_[f"{pre}{k_}"] = v
            return out_

        flats = [(d, {**flat({k_: e.get(k_) for k_ in ("cpu_name", "ram_total_gb", "cpu_cores_applied", "context_max", "modes", "k_order")}), **flat(e.get("identity", {}))}) for d, e in envs]
        keys = sorted({k_ for _, fl in flats for k_ in fl})
        diff = {k_: sorted({json.dumps(fl.get(k_), ensure_ascii=False) for _, fl in flats}) for k_ in keys}
        diff = {k_: v for k_, v in diff.items() if len(v) > 1}
        fps = {str(e.get("env_fingerprint")) for _, e in envs}
        L.append(f"환경 지문(env_fingerprint): {', '.join(sorted(fps))}\n")
        if len(envs) > 1 and (diff or len(fps) > 1):
            L += ["### ⚠ 노트북 사이 환경이 다른 항목 (이 항목이 다르면 시간·토큰·결과 비교에 주의)\n", "| 항목 | 값들 |", "|---|---|"] + [f"| {k_} | {' / '.join(v)} |" for k_, v in diff.items()] + [""]
            warn.append(f"노트북 사이 환경이 다르다: {', '.join(diff)}")
        elif len(envs) > 1:
            L += ["환경 동일성 점검: 소프트웨어 버전·모델 판본·데이터·프롬프트 지문·고정 설정·컴퓨팅 한도·CPU·RAM·커밋이 모든 폴더에서 **같다**.\n"]

    def table(title, getter, d=3):
        for mode in MODES:
            if not any(k[3] == mode for k in R):
                continue
            L.append(f"### {title} - {mode} ({head})\n")
            L.extend(["| 크기 / 한도 | " + " | ".join(f"k={k}" for k in ks) + " |", "|---|" + "---|" * len(ks)])  # 함수 안이라 `+=`는 L을 지역 변수로 만든다
            for z, p, c in rowkeys:
                cells = [getter(R.get((z, p, c, mode, k)), None) for k in ks]
                if any(x is not None for x in cells):
                    L.append(f"| {label(z, p, c)} | " + " | ".join(f(x, d) for x in cells) + " |")
            L.append("")

    L.append("## 검색 (근거 있는 문항 기준, raw top-k가 아니라 문맥 한도에 들어간 앞부분)\n")
    L.append("Recall을 3단계로 따로 적는다: **문서(book_id)** = 근거 문서의 청크를 가져왔는가(id만), **쪽(book_id+page)** = 그 문서의 근거 쪽 청크까지, **쪽+인용문** = 그 쪽에서 quote가 든 청크까지. 뒤로 갈수록 엄격하다. 문서는 공식 정의(모든 그룹의 모든 대안 문서를 찾아야 1.0), 쪽과 쪽+인용문은 그룹 단위(그룹마다 대안 하나면 충족)다.\n")
    table("Recall@k ① 문서(book_id), 공식", lambda c, _: c and c["recall_book"])
    table("Recall@k ② 쪽(book_id+page), 그룹 단위", lambda c, _: c and c["recall_page"])
    table("Recall@k ③ 쪽+인용문(page+quote), 그룹 단위", lambda c, _: c and c["recall_pq"])
    table("Hit@k ① 문서(book_id): 근거 문서를 하나라도", lambda c, _: c and c["hit"])
    table("Hit@k ② 쪽(book_id+page): 근거 쪽을 하나라도", lambda c, _: c and c["hit_page"])
    table("Hit@k ③ 쪽+인용문(page+quote): quote가 든 청크를 하나라도", lambda c, _: c and c["hit_pq"])
    table("모든그룹 충족률 ① 문서(그룹마다 대안 하나)", lambda c, _: c and c["all_book"])
    table("모든그룹 충족률 ② 쪽(book_id+page)", lambda c, _: c and c["all_page"])
    table("모든그룹 충족률 ③ 쪽+인용문(page+quote)", lambda c, _: c and c["all_pq"])
    table("문맥에 들어간 청크 수(평균)", lambda c, _: c and c["n_used"], 2)
    table("한도 때문에 청크가 밀려난 문항 수", lambda c, _: c and c["n_trunc"], 0)
    table("문항당 밀려난 청크 수(전체 평균)", lambda c, _: c and c["n_drop"], 2)
    L.append("## 답변 품질 (행동 일치율·토큰은 병렬 호출, RAGAS는 faithfulness만)\n")
    table("답변 행동 일치율(전체)", lambda c, _: c and c.get("act", {}).get("match"))
    table("답변 유형 일치율", lambda c, _: c and c.get("act", {}).get("match_answer"))
    table("되묻기 유형 일치율", lambda c, _: c and c.get("act", {}).get("match_clarify"))
    table("보류 유형 일치율", lambda c, _: c and c.get("act", {}).get("match_abstain"))
    table("근거 문서 인용률", lambda c, _: c and c.get("act", {}).get("cites"))
    table("입력 토큰 평균", lambda c, _: c and c.get("act", {}).get("tin"), 0)
    table("출력 토큰 평균", lambda c, _: c and c.get("act", {}).get("tout"), 0)
    table("재생성한 문항 비율(LLM 호출 2회 이상)", lambda c, _: c and c.get("act", {}).get("regen"))
    table("병렬 답변 호출 LLM 시간 평균(초, 병렬 부하 중 값)", lambda c, _: c and c.get("act", {}).get("llm_s"), 2)
    if G:
        L += ["### RAGAS faithfulness (3회 평균, 문항 수는 n). 채점 토큰은 채점 LLM이 쓴 문항당 평균(3회 합)이며 답변 토큰과 따로 센다\n", "| 방식 | 크기 / 오버랩 | 한도 | k | n | faithfulness | 채점 입력 토큰 | 채점 출력 토큰 |", "|---|---|---|---|---|---|---|---|"]
        for (z, p, c, m, k), v in sorted(G.items(), key=lambda x: (MODES.index(x[0][3]), x[0][0], -x[0][2], x[0][4])):
            L.append(f"| {m} | {z} / {p}% | {c} | {k} | {v['n']} | {f(v['faithfulness'])} | {f(v['tokens_in'], 0)} | {f(v['tokens_out'], 0)} |")
        L.append("")

    L += ["## 운영 지표 (노트북별로 따로 적는다)\n", "### 검색 시간(retrieve() 한 번, k=11, 초) - 노트북 폴더별\n", "| 방식 | 크기 / 오버랩 | 폴더 | 평균 | 중앙값 | p95 |", "|---|---|---|---|---|---|"]
    for (z, p, m), per in sorted(T.items(), key=lambda x: (MODES.index(x[0][2]), x[0][0], x[0][1])):
        for d, xs in per.items():
            L.append(f"| {m} | {z} / {p}% | {d} | {f(st.mean(xs), 4)} | {f(st.median(xs), 4)} | {f(pct95(xs), 4)} |")
    L.append("")
    if STG:
        L += ["### 검색 내부 단계 시간 (ms, 문항 평균) — 질문 임베딩+벡터 검색 / BM25 / RRF / 리랭크\n", "(`retrieve()`와 같은 연산을 같은 순서로 한 번 더 돌려 단계마다 잰 값이라, 위 검색 시간과 합이 조금 다를 수 있다. k와 무관하다)\n",
              "| 방식 | 크기 / 오버랩 | 임베딩+벡터 | BM25 | RRF | 리랭크 | 합계 |", "|---|---|---|---|---|---|---|"]
        for (z, p, m), s_ in sorted(STG.items(), key=lambda x: (MODES.index(x[0][2]), x[0][0], x[0][1])):
            L.append(f"| {m} | {z} / {p}% | {f(s_.get('dense_ms'), 1)} | {f(s_.get('bm25_ms'), 1)} | {f(s_.get('rrf_ms'), 1)} | {f(s_.get('rerank_ms'), 1)} | {f(sum(s_.values()), 1)} |")
        L.append("")
    if E2E:
        L += ["### 전체 시간(검색 + 문맥 + LLM 답변, 검색 직렬·LLM 동시 호출, 초) - 노트북 폴더별. 문맥이 같은 문항은 가장 큰 한도의 값을 그대로 쓴다\n",
              "| 폴더 | 방식 | 크기 | k | 한도 | n(오류) | **합계 평균** | 합계 중앙값 | 합계 p95 | **검색(평균)** | **LLM 답변(평균)** | LLM 답변(중앙값) | 입력 토큰 | 출력 토큰 | 다시 잰 문항 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for key, v in sorted((k_ for k_ in E2E.items() if len(k_[0]) == 5), key=lambda x: (x[0][0], MODES.index(x[0][4]), x[0][1], x[0][2], -x[0][3])):
            L.append(f"| {key[0]} | {key[4]} | {key[1]} | {key[2]} | {key[3]} | {v['n']}({v['err']}) | {f(v['mean'], 2)} | {f(v['median'], 2)} | {f(v['p95'], 2)} | {f(v['retr'], 3)} | {f(v['llm'], 2)} | {f(v['llm_med'], 2)} | {f(v['tin'], 0)} | {f(v['tout'], 0)} | {v['redo']} |")
        if DIFF:
            L += ["", "### 한도 때문에 문맥이 달라진 문항만 비교 (같은 문항의 가장 큰 한도 대비)\n", "| 폴더 | 방식 | 크기 | k | 한도 | 문항 수 | 전체 시간(이 한도) | 전체 시간(가장 큰 한도) | 입력 토큰(이 한도) | 입력 토큰(가장 큰 한도) |", "|---|---|---|---|---|---|---|---|---|---|"]
            for key, v in sorted(DIFF.items(), key=lambda x: (x[0][0], MODES.index(x[0][4]), x[0][1], x[0][2], -x[0][3])):
                L.append(f"| {key[0]} | {key[4]} | {key[1]} | {key[2]} | {key[3]} | {v['n']} | {f(v['at_lim'], 2)} | {f(v['at_max'], 2)} | {f(v['tin_lim'], 0)} | {f(v['tin_max'], 0)} |")
        L += ["", "### 공통 기준점(500자·0%·hybrid_rerank·k=10·한도 3000) - 노트북 사이 비교와 시간대 흔들림\n", "| 폴더 | 시점 | 시각 | n | 평균 | 중앙값 |", "|---|---|---|---|---|---|"]
        for key, v in sorted(k_ for k_ in E2E.items() if len(k_[0]) == 2):
            L.append(f"| {key[0]} | {key[1]} | {v['at']} | {v['n']} | {f(v['mean'], 2)} | {f(v['median'], 2)} |")
        L.append("")
    L += [f"## 확정값(900자·0%·k=5·한도 {BASE_CTX}) 대비 후보 (사전 기준 1·2·토큰만 자동 판정)\n", "| 방식 | 크기 / 오버랩 / 한도 | k | ΔRecall(book) | ΔRecall(p+q) | Δ행동 일치율 | 입력 토큰 비 | 후보 |", "|---|---|---|---|---|---|---|---|"]
    cand = []
    for mode in MODES:
        b = R.get((*BASE[:2], BASE_CTX, mode, BASE[2]))
        if not b or "act" not in b:
            continue
        for (z, p, c, m, k), x in sorted(R.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[0][2], kv[0][4])):
            if m != mode or "act" not in x or (z, p, c, k) == (*BASE[:2], BASE_CTX, BASE[2]):
                continue
            db, dq = x["recall_book"] - b["recall_book"], x["recall_pq"] - b["recall_pq"]
            da = x["act"]["match"] - b["act"]["match"]
            ratio = x["act"]["tin"] / b["act"]["tin"] if b["act"]["tin"] else None
            ok = db >= 0.03 and dq >= 0.03 and da >= -0.02 and (ratio is None or ratio <= 1.5)
            for t in ("match_clarify", "match_abstain"):
                if x["act"][t] is not None and b["act"][t] is not None and x["act"][t] < b["act"][t]:
                    ok = False
            L.append(f"| {m} | {z} / {p}% / {c} | {k} | {db:+.3f} | {dq:+.3f} | {da:+.3f} | {f(ratio, 2)} | {'후보' if ok else ''} |")
            if ok:
                cand.append(dict(mode=m, size=z, pct=p, ctx=c, k=k, d_book=db, d_pq=dq, d_act=da))
    L.append(f"\n후보 {len(cand)}개. 전체 시간·RAGAS 기준(사전 기준 3·4)은 위 표로 직접 확인한다.\n")

    if A.doc:
        fill_doc(Path(A.doc), L, dirs, R, E2E)
    out = Path(A.out or Path(A.inputs[0]) / "report")
    out.mkdir(parents=True, exist_ok=True)
    (out / "merged.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    ser = lambda t: {"|".join(map(str, k)) if isinstance(k, tuple) else k: v for k, v in t.items()}  # noqa: E731
    (out / "merged.json").write_text(json.dumps(dict(retrieval=ser(R), e2e=ser(E2E), e2e_diff=ser(DIFF), ragas=ser(G), candidates=cand, warnings=warn), ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"저장: {out / 'merged.md'} (설정 {len(R)}개, 후보 {len(cand)}개, 경고 {len(warn)}개)")


if __name__ == "__main__":
    main()
