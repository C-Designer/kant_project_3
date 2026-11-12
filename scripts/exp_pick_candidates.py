"""EXP-0002 2단계 후보 선택. 1단계(검색 지표) CSV에서 docs/experiments/0002-param-sweep.md의 규칙대로 변수별 상위 3개를 뽑는다.

    PYTHONPATH=. uv run python scripts/exp_pick_candidates.py            # 후보와 2단계 큐 출력
규칙은 결과를 보기 전에 문서에 적었다. 바꾸려면 문서에 이유와 함께 적는다.
"""

import csv
import glob
import statistics as st
from pathlib import Path

RESULTS = Path("results/exp2")
MODE = "hybrid_rerank"  # 선택에는 이 방식의 검색 지표만 쓴다
RECALL_BAND = 0.02
TOP = 3
# 변수 -> 기준값(기준 설정 값). context_size는 topK 8에서 재므로 기준점은 topk-8 설정(문맥 한도 3000)
BASELINE = {"topk": 5, "chunk_size": 900, "overlap": 0, "rerank_candidates": 20}
# LLM 평가가 이미 끝난 설정(13개): (변수, 값) -> 라벨. ctx-1000·1500은 topK 5라 context_size_k8과 다르다
DONE = {("topk", 3): "topk-3", ("topk", 8): "topk-8", ("chunk_size", 600): "chunk-600", ("chunk_size", 1200): "chunk-1200",
        ("overlap", 100): "overlap-100", ("overlap", 200): "overlap-200", ("rerank_candidates", 10): "rerank-10",
        ("rerank_candidates", 50): "rerank-50", ("context_size_k8", 3000): "topk-8"}
for var, val in BASELINE.items():
    DONE[(var, val)] = "baseline-r1"


def load() -> dict[tuple[str, int], dict]:
    """(변수, 값) -> 지표. 같은 (변수, 값)이 여러 라벨이면(기준 3회) 첫 것을 쓴다(검색 지표는 결정적)."""
    points: dict[tuple[str, int], dict] = {}
    for f in sorted(glob.glob(str(RESULTS / "*-retrieval.csv"))):
        rows = [r for r in csv.DictReader(open(f, encoding="utf-8")) if r["mode"] == MODE]
        if not rows:
            continue
        var, val = rows[0]["variable"], rows[0]["value"]
        label = Path(f).name.removesuffix("-retrieval.csv")
        if label.startswith("smoke"):
            continue
        num = lambda k: [float(r[k]) for r in rows if r[k] != ""]
        key = (var, int(val)) if val.isdigit() else None
        if var == "baseline":  # 기준 설정은 모든 변수의 기준값 점이 된다
            for v, b in BASELINE.items():
                points.setdefault((v, b), dict(label=label, recall=st.mean(num("recall")), ctx=st.mean(num("context_tokens")),
                                               ms=st.median(num("retrieve_ms")), trunc=sum(int(r["truncated"]) for r in rows)))
            continue
        if key and key not in points:
            points[key] = dict(label=label, recall=st.mean(num("recall")), ctx=st.mean(num("context_tokens")),
                               ms=st.median(num("retrieve_ms")), trunc=sum(int(r["truncated"]) for r in rows))
    # context_size_k8의 기준점: topK 8(문맥 한도 3000)
    if ("topk", 8) in points:
        points.setdefault(("context_size_k8", 3000), points[("topk", 8)])
    return points


def pick(points: dict, var: str) -> list[int]:
    vals = {v: m for (x, v), m in points.items() if x == var}
    if var == "context_size_k8":
        zero = min((v for v, m in vals.items() if m["trunc"] == 0), default=None)
        below = sorted((v for v in vals if zero is not None and v < zero), key=lambda v: (vals[v]["trunc"], -v))
        return ([zero] if zero is not None else []) + below[:TOP - 1]
    best = max(m["recall"] for m in vals.values())
    ok = [v for v, m in vals.items() if m["recall"] >= best - RECALL_BAND]
    ranked = sorted(ok, key=lambda v: (vals[v]["ctx"], vals[v]["ms"]))
    rest = sorted((v for v in vals if v not in ranked), key=lambda v: (-vals[v]["recall"], vals[v]["ctx"]))
    return (ranked + rest)[:TOP]  # band 안이 3개 미만이면 Recall 높은 순으로 채운다


if __name__ == "__main__":
    fake = {("topk", v): dict(label=f"t{v}", recall=r, ctx=c, ms=1.0, trunc=0)
            for v, r, c in [(3, 0.60, 900), (5, 0.70, 1600), (6, 0.72, 1900), (8, 0.75, 2600), (10, 0.76, 3300)]}
    assert pick(fake, "topk") == [8, 10, 6]  # band(0.76±0.02)는 8·10, 모자라 Recall 높은 6으로 채운다
    fake2 = {("context_size_k8", v): dict(label="x", recall=0.7, ctx=1.0, ms=1.0, trunc=t)
             for v, t in [(1500, 15), (2000, 11), (2500, 4), (3000, 0), (4000, 0)]}
    assert pick(fake2, "context_size_k8") == [3000, 2500, 2000]  # 잘림 0이 되는 최소값 + 그 아래 잘림이 적은 2개
    pts = load()
    queue = []
    for var in ("topk", "chunk_size", "overlap", "context_size_k8", "rerank_candidates"):
        chosen = pick(pts, var) if any(x == var for x, _ in pts) else []
        print(f"\n== {var}: 후보 {len(chosen)}개 (1단계 점 {sum(1 for x, _ in pts if x == var)}개)")
        for v in chosen:
            m = pts[(var, v)]
            done = DONE.get((var, v))
            tag = f"LLM 평가 있음({done})" if done else "2단계에서 돌림"
            note = " [해석 보류: 임베딩 512토큰 초과]" if var == "chunk_size" and v > 900 else ""
            print(f"  {v:>5}  Recall={m['recall']:.2f} 문맥토큰={m['ctx']:.0f} 검색ms={m['ms']:.0f} 잘림={m['trunc']}  {tag}{note}")
            if not done:
                queue.append(f"s2-{var.replace('_k8', '').replace('rerank_candidates', 'rerank').replace('chunk_size', 'chunk').replace('context_size', 'ctx8')}-{v} {var} {v}")
    print("\n# 2단계 큐(라벨 변수 값)")
    print("\n".join(queue))
