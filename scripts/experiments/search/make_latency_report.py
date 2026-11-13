"""검색 시간, 검색 내부 단계, 답변 LLM 시간, 직렬 전체 시간을 한 문서로 정리한다.

    uv run python scripts/experiments/search/make_latency_report.py \
      --in results/exp0020/laptop1 results/exp0022/laptop3 results/exp0020/laptop1_ov --out results/report_v2/findings/latency.md

값은 결과 폴더의 원자료(retrieval/, answers/, e2e/)에서 직접 계산한다. GPU·LLM이 필요 없다.
"""
import argparse
import json
import statistics as st
from pathlib import Path

MODES = ("naive", "hybrid", "hybrid_rerank")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    runs = []
    for d in a.inputs:
        d = Path(d)
        env = load(d / "env.json")
        runs.append(dict(name=f"{d.parent.name}/{d.name}", dir=d, ks=[int(k) for k in env["k"]], pcts=[int(p) for p in env["pcts"]], sizes=[int(s) for s in env["sizes"]],
                         e2e_workers=(env.get("identity") or {}).get("e2e_workers") or env.get("e2e_workers")))
    sizes = sorted({s for r in runs for s in r["sizes"]})
    pcts = sorted({p for r in runs for p in r["pcts"]})
    ks_of = {p: sorted({k for r in runs if p in r["pcts"] for k in r["ks"]}, reverse=True) for p in pcts}

    def src(p, k):
        return next((i for i, r in enumerate(runs) if p in r["pcts"] and k in r["ks"]), None)

    RET = {}  # (z, p) -> retrieval json (그 오버랩에서 가장 큰 k를 만든 실행)
    for p in pcts:
        i = src(p, ks_of[p][0])
        for z in sizes:
            fp = runs[i]["dir"] / "retrieval" / f"{z}_{p}.json"
            if fp.exists():
                RET[(z, p)] = load(fp)
    conds = [(z, p) for z in sizes for p in pcts if (z, p) in RET]

    L = ["# 지연 시간: 검색 / 검색 내부 단계 / 답변 LLM / 직렬 전체 시간", "",
         "[목록](../index.md) · 값은 결과 폴더의 원자료에서 직접 계산했다. 시간은 노트북 한 대(Core Ultra 9 275HX, RTX 5060 Laptop)에서 잰 값이다.", "",
         "| 표 | 무엇을 쟀나 | 오버랩 | 주의 |", "|---|---|---|---|",
         "| A | 검색 시간: `retrieve()` 한 번 | 0·10·20% | 문항 72개 평균. naive의 첫 질문 한 건에 질문 임베딩 모델 로딩(약 4초)이 섞여 평균이 부풀 수 있어 **중앙값을 같이** 적었다 |",
         "| B | 검색 내부 단계(ms) | 0·10·20% | 방식마다 단계 구성이 다르다 |",
         "| C | 답변 단계의 LLM 시간 | 0·10·20% | 다른 호출과 겹쳐 잰 값이라 직렬 시간(표 D)보다 길 수 있다 |",
         "| D | 직렬 전체 시간(검색 + LLM + 합계) | **0%만** | e2e 단계는 오버랩 0%만 쟀다 |", ""]

    # A. 검색 시간
    L += ["## A. 검색 시간 (`retrieve()` 한 번, 초)", "", "칸: `평균 / 중앙값 / p95`. 상위 k를 11개 가져오는 한 번의 호출 시간이다(작은 k는 그 앞부분을 잘라 쓴다).", "",
          "| 오버랩 | 크기 | " + " | ".join(MODES) + " |", "|---|---|---|---|---|"]
    for (z, p) in conds:
        cs = []
        for m in MODES:
            xs = [r["retrieval_s"] for r in RET[(z, p)]["modes"][m].values()]
            cs.append(f"{f(mean(xs), 3)} / {f(st.median(xs), 3)} / {f(p95(xs), 3)}")
        L.append(f"| {p}% | {z}자 | " + " | ".join(cs) + " |")
    L.append("")

    # B. 내부 단계
    L += ["## B. 검색 내부 단계 (ms, 문항 평균)", "",
          "naive는 질문 임베딩 + 벡터 검색, hybrid는 거기에 BM25와 RRF, hybrid_rerank는 그 뒤에 리랭크가 붙는다.", "",
          "| 오버랩 | 크기 | naive 임베딩+벡터 | hybrid 임베딩+벡터 | hybrid BM25 | hybrid RRF | rerank 임베딩+벡터 | rerank BM25 | rerank RRF | **rerank 리랭크** |", "|---|---|---|---|---|---|---|---|---|---|"]

    def stage(z, p, m, key):
        return mean([((r.get("stages") or {}).get("stage_ms") or {}).get(key) for r in RET[(z, p)]["modes"][m].values()])
    for (z, p) in conds:
        L.append(f"| {p}% | {z}자 | {f(stage(z, p, 'naive', 'dense_ms'), 1)} | {f(stage(z, p, 'hybrid', 'dense_ms'), 1)} | {f(stage(z, p, 'hybrid', 'bm25_ms'), 1)} | {f(stage(z, p, 'hybrid', 'rrf_ms'), 2)} | "
                 f"{f(stage(z, p, 'hybrid_rerank', 'dense_ms'), 1)} | {f(stage(z, p, 'hybrid_rerank', 'bm25_ms'), 1)} | {f(stage(z, p, 'hybrid_rerank', 'rrf_ms'), 2)} | **{f(stage(z, p, 'hybrid_rerank', 'rerank_ms'), 1)}** |")
    L.append("")

    # C. 답변 단계 LLM 시간
    L += ["## C. 답변 단계의 LLM 시간 (초, 문항 평균)", "",
          "답변 단계에서 잰 값이라 직렬 시간(표 D)과 직접 비교하지 않는다. 칸은 문맥 한도 `3000 / 4200`이다. 한도가 문맥을 바꾸지 않는 조건은 두 값이 같다.", ""]
    ANS = {}
    for (z, p) in conds:
        for i, r in enumerate(runs):
            fp = r["dir"] / "answers" / f"{z}_{p}.json"
            if p in r["pcts"] and fp.exists():
                for rec in load(fp)["records"]:
                    ANS.setdefault((z, p, rec["mode"], int(rec["k"]), int(rec["ctx"])), []).append((i, rec))
    for k in sorted({k for p in pcts for k in ks_of[p]}, reverse=True):
        L += [f"### k = {k}", "", "| 오버랩 | 크기 | " + " | ".join(MODES) + " |", "|---|---|---|---|---|"]
        for (z, p) in conds:
            if k not in ks_of[p]:
                continue
            i0 = src(p, k)
            cs = []
            for m in MODES:
                vs = []
                for c in (3000, 4200):
                    xs = [rec["llm_ms"] / 1000 for i, rec in ANS.get((z, p, m, k, c), []) if i == i0 and rec.get("llm_ms") is not None]
                    vs.append(f(mean(xs)))
                cs.append(" / ".join(vs))
            L.append(f"| {p}% | {z}자 | " + " | ".join(cs) + " |")
        L.append("")

    # D. 직렬 전체 시간 (오버랩 0%)
    L += ["## D. 직렬 전체 시간 (오버랩 0%만, 초)", "",
          "한 문항을 `retrieve()`(직렬) + 문맥 조립 + LLM 답변으로 끝까지 잰 시간이다. 칸은 `검색 / LLM / 합계(한도 4200) / 합계(한도 3000)`이다. 한도 3000에서 청크가 밀려 문맥이 짧아지면 LLM 시간이 줄 수 있다.", ""]

    def e2e_vals(d, z, k, m, ctx):
        e = load(d / "e2e" / f"{z}_0.json")
        out_ = {"retr": [], "llm": [], "total": []}
        for r in e["modes"][m][str(k)]:
            x = r["ctx"].get(str(ctx))
            if x and "same_as" in x:
                x = r["ctx"].get(str(x["same_as"]))
            if not x or x.get("total_s") is None or x.get("error"):
                continue
            out_["retr"].append(r.get("retrieval_s"))
            out_["llm"].append(x.get("llm_s"))
            out_["total"].append(x["total_s"])
        return out_

    for i, r in enumerate(runs):
        if 0 not in r["pcts"]:  # 오버랩 실행 폴더에 다시 잰 0% 값은 중복이라 뺀다
            continue
        for k in r["ks"]:
            L += [f"### k = {k} · {r['name']}", "", "| 크기 | " + " | ".join(MODES) + " |", "|---|---|---|---|"]
            for z in sizes:
                if not (r["dir"] / "e2e" / f"{z}_0.json").exists():
                    continue
                cs = []
                for m in MODES:
                    hi, lo = e2e_vals(r["dir"], z, k, m, 4200), e2e_vals(r["dir"], z, k, m, 3000)
                    cs.append(f"{f(mean(hi['retr']), 2)} / {f(mean(hi['llm']), 2)} / **{f(mean(hi['total']), 2)}** / {f(mean(lo['total']), 2)}")
                L.append(f"| {z}자 | " + " | ".join(cs) + " |")
            L.append("")
    # 공통 기준점
    L += ["### 공통 기준점 (500자·0%·hybrid_rerank·k=10·한도 3000, 직렬, 시간대 흔들림 확인용)", "", "| 실험 폴더 | 시점 | 시각 | 합계 평균(초) |", "|---|---|---|---|"]
    for r in [r for r in runs if 0 in r["pcts"]]:
        for nm in ("start", "end"):
            fp = r["dir"] / "e2e" / f"anchor_{nm}.json"
            if fp.exists():
                x = load(fp)
                tot = [((row.get("ctx") or {}).get("3000") or {}).get("total_s") for row in x["rows"]]  # 기준점은 한도 3000 한 가지만 잰다
                L.append(f"| {r['name']} | {nm} | {x.get('run_at')} | {f(mean(tot), 2)} |")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
