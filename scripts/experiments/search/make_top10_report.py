"""청크 크기별 가장 좋은 조건 Top 10을 보기 쉬운 요약표로 만든다(막대, 쉬운 말, 자세한 칸은 접기).

    uv run python scripts/experiments/search/make_top10_report.py \
      --in results/exp0020/laptop1 results/exp0022/laptop3 results/exp0023/laptop4 results/exp0020/laptop1_ov ... --out results/report_v2/findings/top10.md

값은 각 실행의 report/merged.json과 retrieval/ 원자료에서만 가져온다(merge_grid_results.py를 먼저 실행).
"""
import argparse
import json
import statistics as st
from pathlib import Path

MODES = ("naive", "hybrid", "hybrid_rerank")
BASE = (900, 0, 5, 3000)  # 확정값: 900자 · 오버랩 0% · k=5 · 한도 3000
MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def f(x, n=3):
    return "-" if x is None else f"{x:.{n}f}"


def pct(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def bar(x, width=20):
    n = round((x or 0) * width)
    return "█" * n + "░" * (width - n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-hit-book", type=float, default=1.0, help="Hit ①(문서)가 이 값 이상인 조건만 후보로 쓴다(기본 1.0). 0이면 거르지 않는다")
    a = ap.parse_args()
    runs = []
    for d in a.inputs:
        d = Path(d)
        env = load(d / "env.json")
        runs.append(dict(name=f"{d.parent.name}/{d.name}", dir=d, ks=[int(k) for k in env["k"]], pcts=[int(p) for p in env["pcts"]], sizes=[int(s) for s in env["sizes"]],
                         ctxs=[int(c) for c in env["context_max"]], M=load(d / "report" / "merged.json")))
    sizes = sorted({s for r in runs for s in r["sizes"]})
    ctxs = sorted({c for r in runs for c in r["ctxs"]})
    pcts = sorted({p for r in runs for p in r["pcts"]})

    def src(p, k):
        return next((r for r in runs if p in r["pcts"] and k in r["ks"]), None)

    rt = {}
    cands = []
    for p in pcts:
        for k in sorted({k for r in runs if p in r["pcts"] for k in r["ks"]}):
            r = src(p, k)
            for z in sizes:
                for c in ctxs:
                    for m in MODES:
                        x = r["M"]["retrieval"].get(f"{z}|{p}|{c}|{m}|{k}")
                        if not x or x.get("recall_pq") is None:
                            continue
                        key = (r["name"], z, p, m)
                        if key not in rt:
                            fp = r["dir"] / "retrieval" / f"{z}_{p}.json"
                            rt[key] = st.mean(v["retrieval_s"] for v in load(fp)["modes"][m].values()) if fp.exists() else None
                        g = r["M"]["ragas"].get(f"{z}|{p}|{c}|{m}|{k}")
                        cands.append(dict(p=p, z=z, k=k, c=c, m=m, rec_pq=x["recall_pq"], rec_bk=x["recall_book"], hit_bk=x["hit"], hit_pg=x["hit_page"], hit_pq=x["hit_pq"],
                                          match=x["act"]["match"], tin=x["act"]["tin"], drop=x["n_drop"], faith=g["faithfulness"] if g else None, ret_s=rt[key], run=r["name"],
                                          tot_s=(r["M"]["e2e"].get(f"{r['dir'].name}|{z}|{k}|{c}|{m}") or {}).get("median") if p == 0 else None))
    base = {m: next((c for c in cands if (c["z"], c["p"], c["k"], c["c"]) == BASE and c["m"] == m), None) for m in MODES}
    ok_hit = [x for x in cands if (x["hit_bk"] or 0) >= a.min_hit_book - 1e-9]

    per = {}
    for z in sizes:
        grp = {}
        for x in ok_hit:
            if x["z"] != z:
                continue
            g = (x["p"], x["k"], x["m"])  # 한도만 다른 조건은 가장 좋은 한도 하나로 합친다
            if g not in grp or (round(x["rec_pq"], 6), -x["tin"]) > (round(grp[g]["rec_pq"], 6), -grp[g]["tin"]):
                grp[g] = x
        per[z] = sorted(grp.values(), key=lambda x: (-round(x["rec_pq"], 6), -(x["match"] or 0), x["tin"]))[:a.top]

    def delta(x):
        b = base.get(x["m"])
        if not b:
            return "-"
        d = (x["rec_pq"] - b["rec_pq"]) * 100
        return f"▲ +{d:.1f}%p" if d > 0.05 else (f"▼ {d:.1f}%p" if d < -0.05 else "= 같음")

    def cond(x):
        return f"오버랩 {x['p']}% · k={x['k']} · 한도 {x['c']} · {x['m']}"

    L = ["# 청크 크기별 가장 좋은 조건 Top 10", "",
         "> **한 줄 요약**: 청크 크기마다, 정답 문장이 든 청크를 가장 잘 찾아오는 조건 10개를 뽑았다. [목록](../index.md)", "",
         "## 한눈에 보기: 청크 크기별 1위", "", "| 청크 크기 | 가장 좋은 조건 | 정답 청크를 찾은 비율 |", "|---|---|---|"]
    for z in sizes:
        if per[z]:
            t = per[z][0]
            L.append(f"| **{z}자** | {cond(t)} | `{bar(t['rec_pq'])}` **{pct(t['rec_pq'])}** |")
        else:
            L.append(f"| **{z}자** | 기준을 넘는 조건 없음 | - |")
    if base.get("hybrid_rerank"):
        L.append(f"| (비교) 확정값 | 900자 · 오버랩 0% · k=5 · 한도 3000 · hybrid_rerank | `{bar(base['hybrid_rerank']['rec_pq'])}` {pct(base['hybrid_rerank']['rec_pq'])} |")
    # 종합 Top 10: 모든 청크 크기를 한꺼번에 놓고 같은 방식으로 뽑는다
    ggrp = {}
    for x in ok_hit:
        g = (x["z"], x["p"], x["k"], x["m"])
        if g not in ggrp or (round(x["rec_pq"], 6), -x["tin"]) > (round(ggrp[g]["rec_pq"], 6), -ggrp[g]["tin"]):
            ggrp[g] = x
    overall = sorted(ggrp.values(), key=lambda x: (-round(x["rec_pq"], 6), -(x["match"] or 0), x["tin"]))[:a.top]
    L += ["", "## 종합 Top 10: 모든 청크 크기를 합쳐서 가장 좋은 조건", "",
          "| 순위 | 청크 크기 | 오버랩 | k | 한도 | 방식 | 정답 청크를 찾은 비율 (Recall ③) | 확정값 대비 | Recall ① 문서 | Hit ① / ③ | 행동 일치율 | 입력 토큰 | 검색(초) | 전체(초) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, x in enumerate(overall, 1):
        L.append(f"| {MEDAL.get(i, i)} | **{x['z']}자** | {x['p']}% | {x['k']} | {x['c']} | {x['m']} | `{bar(x['rec_pq'], 14)}` **{pct(x['rec_pq'])}** | {delta(x)} | {pct(x['rec_bk'])} | {f(x['hit_bk'], 2)} / {f(x['hit_pq'], 2)} | {pct(x['match'])} | {x['tin']:,.0f} | {f(x['ret_s'], 2)} | {f(x['tot_s'], 1)} |")
    sizes_in = {x["z"] for x in overall}
    L += ["", f"- 종합 Top 10에 든 청크 크기: {', '.join(f'{z}자 {sum(1 for x in overall if x['z'] == z)}개' for z in sorted(sizes_in))}.",
          f"- 모두 {'`' + overall[0]['m'] + '`' if len({x['m'] for x in overall}) == 1 else '여러 방식'}이고, 오버랩은 {', '.join(f'{p}%' for p in sorted({x['p'] for x in overall}))}가 섞여 있다.",
          "- **1~5위 차이는 1.5%p 안팎이라 사실상 같은 수준**이다(문항 하나가 약 1.5%p). 이 안에서는 입력 토큰이 적은 조건이 더 경제적이다.", ""]
    L += ["", "## 이 표 읽는 법", "",
          "| 말 | 뜻 |", "|---|---|",
          "| **정답 청크를 찾은 비율** (Recall ③) | 정답 문장이 든 청크를 상위 k개 안에 가져온 비율. **높을수록 좋다.** 이 문서의 순위 기준 |",
          "| **확정값 대비** | 확정값(900자 · 오버랩 0% · k=5 · 한도 3000, 같은 방식)보다 얼마나 올랐나. ▲ 올랐다, ▼ 내려갔다, %p는 퍼센트포인트 |",
          "| **행동 일치율** | LLM이 답변·되묻기·보류를 질문 유형에 맞게 했는지. 높을수록 좋다 |",
          "| **입력 토큰** | LLM에 넣는 문맥의 평균 길이. **낮을수록 시간·비용이 덜 든다** |",
          "| **Recall ① 문서** | 근거 문서를 가져왔는가(공식 정의, 대안 문서를 모두 세므로 낮게 나온다) |",
          "| **Hit ① / ③** | 근거 문서를 하나라도 / 정답 문장이 든 청크를 하나라도 가져온 질문의 비율 |",
          "| **검색(초)** | 검색 단계 한 번의 평균 시간. 실행(노트북·시각)마다 달라 같은 실행 안에서만 비교 |",
          "| **전체(초)** | 검색 + LLM 답변 시간의 **중앙값**(직렬 전체 시간 측정). **오버랩 0% 실행에만 있고 10·20%는 `-`** |",
          "| k, 한도 | 가져오는 청크 수, LLM에 넣을 수 있는 최대 토큰 |", ""]
    L += ["## 먼저 알아둘 것", "",
          f"- **근거 문서를 모든 질문에서 하나 이상 가져온 조건**(Hit ① = 1.00)만 후보로 썼다(전체 {len(cands)}개 중 {len(ok_hit)}개). 문서를 아예 못 찾는 조건은 뺀 것이다.",
          "- 같은 오버랩·k·방식에서 **문맥 한도만 다른 조건은 하나로 합쳤다**(가장 좋은 한도만 표시). 한도별 값은 [recall_matrix.md](recall_matrix.md)에 있다.",
          "- 질문 68개 평균이라 **한 문항이 약 1.5%p를 움직인다. 3%p보다 작은 차이는 우연일 수 있다.**",
          "- 이 표는 **정답 청크를 찾는 능력(검색 품질)**이다. 답변이 맞다는 뜻은 아니라서 행동 일치율을 옆에 뒀다.", ""]
    for z in sizes:
        L += [f"## {z}자: Top 10", ""]
        if not per[z]:
            L += ["기준을 넘는 조건이 없다.", ""]
            continue
        L += ["| 순위 | 오버랩 | k | 한도 | 방식 | 정답 청크를 찾은 비율 (Recall ③) | 확정값 대비 | Recall ① 문서 | Hit ① / ③ | 행동 일치율 | 입력 토큰 | 검색(초) | 전체(초) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for i, x in enumerate(per[z], 1):
            L.append(f"| {MEDAL.get(i, i)} | {x['p']}% | {x['k']} | {x['c']} | {x['m']} | `{bar(x['rec_pq'], 14)}` **{pct(x['rec_pq'])}** | {delta(x)} | {pct(x['rec_bk'])} | {f(x['hit_bk'], 2)} / {f(x['hit_pq'], 2)} | {pct(x['match'])} | {x['tin']:,.0f} | {f(x['ret_s'], 2)} | {f(x['tot_s'], 1)} |")
        L.append("")
    L += ["## 자세한 값 (전체 칸)", "", "<details><summary>누르면 Top 10의 모든 칸(문서 Recall, Hit 3단계, faithfulness, 검색 시간, 밀려난 청크)이 펼쳐진다</summary>", "",
          "| 청크 크기 | 순위 | 오버랩 | k | 한도 | 방식 | Recall ③ | Recall ① 문서 | Hit ① / ② / ③ | 행동 일치율 | faithfulness | 입력 토큰 | 검색 시간(초) | 밀려난 청크 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for z in sizes:
        for i, x in enumerate(per[z], 1):
            L.append(f"| {z}자 | {i} | {x['p']}% | {x['k']} | {x['c']} | {x['m']} | {f(x['rec_pq'])} | {f(x['rec_bk'])} | {f(x['hit_bk'], 2)} / {f(x['hit_pg'], 2)} / {f(x['hit_pq'], 2)} | "
                     f"{f(x['match'], 2)} | {f(x['faith'])} | {x['tin']:.0f} | {f(x['ret_s'], 3)} | {x['drop']:.2f} |")
    L += ["", "- faithfulness가 `-`인 조건은 RAGAS를 돌리지 않았다(오버랩 10·20%의 k=9·7·8).",
          "- **검색 시간은 실행(노트북·시각·그때의 부하)마다 달라 서로 직접 비교하면 안 된다.** 같은 실행 안에서의 비교만 믿을 수 있다.",
          "- 자료: " + ", ".join(f"`{r['name']}`(오버랩 {','.join(map(str, r['pcts']))}%, k {','.join(map(str, r['ks']))})" for r in runs), "", "</details>"]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"저장: {a.out} (후보 {len(cands)}개, 기준 통과 {len(ok_hit)}개)")


if __name__ == "__main__":
    main()
