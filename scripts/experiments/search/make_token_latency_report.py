"""입력 토큰량에 따른 LLM 지연 시간, 그리고 청크가 한도 때문에 누락됐는지를 한 문서로 정리한다.

    uv run python scripts/experiments/search/make_token_latency_report.py \
      --in results/exp0020/laptop1 results/exp0022/laptop3 results/exp0023/laptop4 results/exp0020/laptop1_ov ... --out results/report_v2/findings/token_latency.md

지연 시간은 오버랩 0% 본 실행의 e2e 파일(문항마다 입력·출력 토큰과 LLM 시간이 같이 기록됨)에서, 누락은 retrieval 파일에서 계산한다.
"""
import argparse
import json
import statistics as st
from pathlib import Path

import numpy as np

MODES = ("naive", "hybrid", "hybrid_rerank")
BINS = [(0, 2000, "2,000 미만"), (2000, 3000, "2,000~3,000"), (3000, 4000, "3,000~4,000"), (4000, 5000, "4,000~5,000"), (5000, 10**9, "5,000 이상")]


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def p95(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(len(xs) * 0.95))] if xs else None


def f(x, n=2):
    return "-" if x is None else f"{x:.{n}f}"


def r2(y, X):
    A = np.column_stack([np.ones(len(y))] + X)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    pred = A @ coef
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return coef, 1 - ss_res / ss_tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    runs = []
    for d in a.inputs:
        d = Path(d)
        env = load(d / "env.json")
        runs.append(dict(name=f"{d.parent.name}/{d.name}", dir=d, ks=[int(k) for k in env["k"]], pcts=[int(p) for p in env["pcts"]], sizes=[int(s) for s in env["sizes"]]))
    sizes = sorted({s for r in runs for s in r["sizes"]})
    pcts = sorted({p for r in runs for p in r["pcts"]})

    # ---- 표본: e2e(오버랩 0%) 문항 단위 ----
    S, SA = [], []  # S: 실제로 따로 잰 건 / SA: 한도 조건마다 한 건(문맥이 같으면 같은 측정값)
    for r in runs:
        if 0 not in r["pcts"]:
            continue
        for z in sizes:
            fp = r["dir"] / "e2e" / f"{z}_0.json"
            if not fp.exists():
                continue
            e = load(fp)
            for m, byk in e["modes"].items():
                for k, rows in byk.items():
                    for row in rows:
                        for c, x in row["ctx"].items():
                            y = row["ctx"].get(str(x["same_as"])) if "same_as" in x else x  # 한도가 달라도 문맥이 같으면 같은 측정값을 쓴다
                            if not y or y.get("error") or y.get("llm_s") is None or y.get("input_tokens") is None:
                                continue
                            s_ = dict(z=z, k=int(k), m=m, c=int(c), tin=y["input_tokens"], tout=y.get("output_tokens"), llm=y["llm_s"], ret=row.get("retrieval_s"),
                                      total=y.get("total_s"), dropped=y["n_used"] < int(k))
                            SA.append(s_)  # 한도 조건마다 한 건(비율 계산용)
                            if "same_as" not in x:
                                S.append(s_)  # 실제로 따로 잰 건(시간 분석용)
    n = len(S)
    tin = np.array([s["tin"] for s in S], dtype=float)
    tout = np.array([s["tout"] or 0 for s in S], dtype=float)
    llm = np.array([s["llm"] for s in S], dtype=float)
    c_in, r_in = r2(llm, [tin])
    c_out, r_out = r2(llm, [tout])
    c_both, r_both = r2(llm, [tin, tout])

    L = ["# 입력 토큰량과 LLM 지연 시간, 그리고 청크 누락", "",
         "[목록](../index.md) · 아래 1~3절은 **오버랩 0% 본 실행의 직렬 전체 시간(e2e) 측정**에서 문항마다 기록된 입력·출력 토큰과 LLM 시간(`llm_s`)으로 계산했다. "
         f"표본은 **{n:,}건**(질문 × 방식 × 크기 × k × 한도). 4절은 검색 결과 파일에서 계산했다.", "",
         "## 1. 한눈에: 입력 토큰이 늘면 LLM 시간이 얼마나 늘까", ""]
    L += [f"- **입력 토큰 1,000개가 늘 때 LLM 시간은 평균 {c_in[1] * 1000:+.2f}초** 늘었다(입력 토큰만으로 설명되는 비율 R² = {r_in:.2f}).",
          f"- **출력 토큰 100개가 늘 때는 {c_out[1] * 100:+.2f}초**였다(출력 토큰만의 R² = {r_out:.2f}).",
          f"- 둘을 함께 넣으면 입력 {c_both[1] * 1000:+.2f}초/1,000토큰, 출력 {c_both[2] * 100:+.2f}초/100토큰이고 R² = {r_both:.2f}다.",
          "- 읽는 법: R²가 1에 가까울수록 그 토큰량만으로 시간이 잘 설명된다. **R²가 낮으면 시간은 다른 요인(LLM 서버 상태, 답변 길이 등)에 더 좌우된다.**", ""]

    # ---- 2. 입력 토큰 구간별 ----
    L += ["## 2. 입력 토큰 구간별 LLM 시간", "", "| 입력 토큰 구간 | 건수 | 입력 토큰 평균 | 출력 토큰 평균 | LLM 시간 평균(초) | 중앙값 | p95 | 검색 시간 평균(초) |", "|---|---|---|---|---|---|---|---|"]
    for lo, hi, name in BINS:
        xs = [s for s in S if lo <= s["tin"] < hi]
        if not xs:
            L.append(f"| {name} | 0 | - | - | - | - | - | - |")
            continue
        L.append(f"| {name} | {len(xs):,} | {mean([s['tin'] for s in xs]):,.0f} | {mean([s['tout'] for s in xs]):,.0f} | {f(mean([s['llm'] for s in xs]))} | "
                 f"{f(st.median([s['llm'] for s in xs]))} | {f(p95([s['llm'] for s in xs]))} | {f(mean([s['ret'] for s in xs]), 3)} |")
    L += ["", "- LLM 시간은 방식(naive·hybrid·hybrid_rerank)과 무관하게 같은 문맥이면 같은 값으로 봤다. 검색 시간은 방식마다 다르다(hybrid_rerank가 약 0.6~0.9초).", ""]

    # ---- 2b. 방식별 ----
    L += ["### 방식별 평균 (입력 토큰 / 출력 토큰 / LLM 시간 / 검색 시간 / 합계)", "", "| 방식 | 건수 | 입력 토큰 | 출력 토큰 | LLM 시간(초) | 검색 시간(초) | 합계(초) |", "|---|---|---|---|---|---|---|"]
    for m in MODES:
        xs = [s for s in S if s["m"] == m]
        L.append(f"| {m} | {len(xs):,} | {mean([s['tin'] for s in xs]):,.0f} | {mean([s['tout'] for s in xs]):,.0f} | {f(mean([s['llm'] for s in xs]))} | {f(mean([s['ret'] for s in xs]), 3)} | {f(mean([s['total'] for s in xs]))} |")
    L.append("")

    # ---- 3. 누락 여부와 시간 ----
    L += ["## 3. 청크가 누락된 경우와 아닌 경우 비교", "",
          "누락 = 상위 k개 청크 중 문맥 한도(토큰 상한) 때문에 문맥에 못 들어간 청크가 하나라도 있는 경우다(한도를 넘는 청크와 그 뒤 청크가 모두 빠진다).", "",
          "| 구분 | 건수 | 입력 토큰 평균 | 출력 토큰 평균 | LLM 시간 평균(초) | 중앙값 | p95 |", "|---|---|---|---|---|---|---|"]
    for name, flag in (("누락 없음", False), ("**누락 있음**", True)):
        xs = [s for s in S if s["dropped"] == flag]
        if xs:
            L.append(f"| {name} | {len(xs):,} | {mean([s['tin'] for s in xs]):,.0f} | {mean([s['tout'] for s in xs]):,.0f} | {f(mean([s['llm'] for s in xs]))} | {f(st.median([s['llm'] for s in xs]))} | {f(p95([s['llm'] for s in xs]))} |")
    L += ["", "### 같은 크기·k에서 한도만 다를 때 (누락이 입력 토큰과 시간을 어떻게 바꾸나)", "",
          "| 크기 | k | 한도 | 건수 | 누락 비율 | 입력 토큰 평균 | LLM 시간 평균(초) |", "|---|---|---|---|---|---|---|"]
    for z in sizes:
        for k in sorted({s["k"] for s in SA if s["z"] == z}, reverse=True):
            for c in (3000, 3400, 3800, 4200):
                xs = [s for s in SA if s["z"] == z and s["k"] == k and s["c"] == c]
                if len(xs) < 30:
                    continue
                dr = sum(s["dropped"] for s in xs) / len(xs)
                if k >= 9 and z >= 800 or dr > 0:  # 누락이 생기는 조합만 보여 표를 짧게 한다
                    L.append(f"| {z}자 | {k} | {c} | {len(xs):,} | {dr * 100:.1f}% | {mean([s['tin'] for s in xs]):,.0f} | {f(mean([s['llm'] for s in xs]))} |")
    L.append("")

    # ---- 4. 누락 여부 표 (문항 수) ----
    L += ["## 4. 누락 여부: 한도 때문에 청크가 밀려난 문항은 몇 개인가", "",
          "칸은 `문항 72개 중 청크가 하나라도 밀려난 문항 수`이고 `0`이면 누락이 없다. 한도 3000 → 4200 순서로 **네 한도 값을 모두** 적었다(`3000 / 3400 / 3800 / 4200`).", ""]
    kmap = {}
    for r in runs:
        for p in r["pcts"]:
            for k in r["ks"]:
                kmap.setdefault((p, k), r)
    ks_all = sorted({k for (_, k) in kmap}, reverse=True)
    for m in MODES:
        L += [f"### {m}", "", "| 오버랩 | 크기 | " + " | ".join(f"k={k}" for k in ks_all) + " |", "|---|---|" + "---|" * len(ks_all)]
        for z in sizes:
            for p in pcts:
                cs = []
                for k in ks_all:
                    r = kmap.get((p, k))
                    fp = r["dir"] / "retrieval" / f"{z}_{p}.json" if r else None
                    if not fp or not fp.exists():
                        cs.append("-")
                        continue
                    R = load(fp)["modes"][m]
                    vals = []
                    for c in (3000, 3400, 3800, 4200):
                        cnt = sum(1 for row in R.values() if row["k"][str(k)]["ctx"][str(c)]["n_used"] < row["k"][str(k)]["n_top"])
                        vals.append(str(cnt))
                    cs.append(" / ".join(vals))
                L.append(f"| {p}% | {z}자 | " + " | ".join(cs) + " |")
        L.append("")
    # ---- 5. 크기 × 오버랩 × k별 입력 토큰과 LLM 시간 ----
    L += ["- 누락은 **크기가 클수록, k가 클수록, 오버랩이 클수록** 많이 생긴다(오버랩이 청크를 길게 만들기 때문). 600·700자나 k=5·7에서는 대부분 0이다.", "- 질문 하나하나의 누락 청크는 `questions/` 파일의 청크 순위표(`❌`)에서 볼 수 있다."]
    L += ["", "## 5. 청크 크기 × 오버랩 × k별 입력 토큰과 LLM 시간", "",
          "입력 토큰·시간 칸은 문맥 한도 4200 기준이고 3방식을 합친 평균이다. **`잘림` 칸은 문맥 한도(max_context)마다 청크가 잘렸는지**다: `✅` = 한 문항도 안 잘림, `✂ n%` = 질문 × 방식 중 n%에서 상위 k개 중 일부가 한도 때문에 문맥에 못 들어감. **LLM 시간(답변 단계)**은 오버랩 0·10·20% 모두 같은 방법으로 잰 값이고, "
          "**LLM 시간(직렬)**은 오버랩 0%에만 있다. 답변 단계 값은 다른 호출과 겹쳐 잰 값이라 직렬 값보다 길 수 있다.", "",
          "| 청크 크기 | 오버랩 | k | **잘림 3000** | **3400** | **3800** | **4200** | 입력 토큰 | 출력 토큰 | LLM 시간(답변 단계) 평균 | 중앙값 | p95 | LLM 시간(직렬) 평균 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    ser = {}
    for s in SA:
        if s["c"] == 4200:
            ser.setdefault((s["z"], s["k"]), []).append(s["llm"])
    done = set()
    for z in sizes:
        for p in pcts:
            for k in sorted({k for (pp, k) in kmap if pp == p}, reverse=True):
                r = kmap[(p, k)]
                fp = r["dir"] / "answers" / f"{z}_{p}.json"
                if not fp.exists() or (z, p, k) in done:
                    continue
                done.add((z, p, k))
                recs = [x for x in load(fp)["records"] if int(x["k"]) == k and int(x["ctx"]) == 4200 and not x.get("error") and x.get("llm_ms") is not None]
                if not recs:
                    continue
                ts = [x["llm_ms"] / 1000 for x in recs]
                RR = load(r["dir"] / "retrieval" / f"{z}_{p}.json")["modes"]
                cut = []
                for c_ in (3000, 3400, 3800, 4200):
                    tot_ = sum(len(RR[m_]) for m_ in RR)
                    drop_ = sum(1 for m_ in RR for row_ in RR[m_].values() if row_["k"][str(k)]["ctx"][str(c_)]["n_used"] < row_["k"][str(k)]["n_top"])
                    cut.append("✅" if drop_ == 0 else f"✂ {drop_ / tot_ * 100:.0f}%")
                sv = ser.get((z, k)) if p == 0 else None
                L.append(f"| {z}자 | {p}% | {k} | {cut[0]} | {cut[1]} | {cut[2]} | {cut[3]} | {mean([x['input_tokens'] for x in recs]):,.0f} | {mean([x['output_tokens'] for x in recs]):,.0f} | {f(mean(ts))} | {f(st.median(ts))} | {f(p95(ts))} | {f(mean(sv)) if sv else '-'} |")
    L += ["", "- 같은 크기·오버랩에서 **k가 클수록 입력 토큰은 늘지만 LLM 시간은 비례해서 늘지 않는다**(시간은 출력 토큰에 좌우된다).",
          "- 오버랩이 클수록 같은 k에서 입력 토큰이 늘어난다(청크가 길어지므로).", ""]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"저장: {a.out} (e2e 표본 {n:,}건)")


if __name__ == "__main__":
    main()
