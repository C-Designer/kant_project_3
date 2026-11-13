"""청크 크기 × 문맥 한도 조합마다 3방식의 결과를 한 파일에 나란히 정리한다.

    uv run python scripts/experiments/search/make_setting_report.py --in results/exp0020/laptop1

저장(기본): <결과 폴더>/report/by_setting/
    index.md                      크기 × 한도 목록과 한눈 요약(3방식의 Recall(쪽+인용문)·행동 일치율)
    size<크기>_ctx<한도>.md        그 조합의 k마다: 3방식 비교표 + 질문 72개별 3방식 비교표

GPU·LLM이 필요 없다. 숫자는 결과 폴더의 파일에서만 가져온다(merged.json이 없으면 merge_grid_results.py를 먼저 실행).
"""
import argparse
import json
from pathlib import Path

MODES = ("naive", "hybrid", "hybrid_rerank")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def f(x, n=3):
    return "-" if x is None else f"{x:.{n}f}"


def mark(b):
    return "-" if b is None else ("✅" if b else "❌")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="grid_kset.py 결과 폴더")
    ap.add_argument("--out-dir", help="기본: 결과 폴더 안의 report/by_setting/")
    a = ap.parse_args()
    root = Path(a.inp)
    out = Path(a.out_dir or root / "report" / "by_setting")
    out.mkdir(parents=True, exist_ok=True)
    M = load(root / "report" / "merged.json")
    Q = load(root / "questions.json")
    env = load(root / "env.json")
    sizes = sorted(int(p.stem.split("_")[0]) for p in (root / "retrieval").glob("*_0.json"))
    ks = [int(k) for k in env["k"]]
    ctxs = sorted(int(c) for c in env["context_max"])
    lp = root.name
    qids = list(Q.keys())

    index = ["# 크기 × 문맥 한도별 3방식 결과", "",
             f"결과 폴더: `{lp}`. 조합마다 파일이 하나 있다. 파일 안은 k마다 ① 3방식 비교표 ② 질문별 3방식 비교표다.", "",
             "읽는 법: **Recall(쪽+인용문)**은 근거 청크를 가져왔는가(그룹 단위), **행동 일치율**은 답/되묻기/보류가 기대와 같은가다. 한도가 문맥을 바꾸지 않는 조합은 3000과 값이 같다.", ""]
    for k in ks:
        index += [f"## k = {k}", "", "| 크기 | 한도 | 파일 | " + " | ".join(f"{m} 근거(쪽+인용문) / 행동" for m in MODES) + " | 밀려난 문항(naive/hybrid/rerank) |", "|---|---|---|---|---|---|---|"]
        for z in sizes:
            for c in ctxs:
                cells = []
                drops = []
                for m in MODES:
                    r = M["retrieval"].get(f"{z}|0|{c}|{m}|{k}")
                    cells.append("-" if not r else f"{f(r['recall_pq'], 2)} / {f(r['act']['match'], 2)}")
                    drops.append("-" if not r else f"{round(r['n_q'] and r['n_drop'] * r['n_q'])}")  # 문항당 평균 밀려난 청크 × 문항 = 밀려난 청크 총수
                index.append(f"| {z} | {c} | [size{z}_ctx{c}.md](size{z}_ctx{c}.md) | " + " | ".join(cells) + f" | 청크 {'/'.join(drops)}개 |")
        index.append("")
    (out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8", newline="\n")

    for z in sizes:
        R = load(root / "retrieval" / f"{z}_0.json")
        A = {}
        for rec in load(root / "answers" / f"{z}_0.json")["records"]:
            A[(rec["mode"], rec["qid"], int(rec["k"]), int(rec["ctx"]))] = rec
        faith = {}
        for m in MODES:
            for k in ks:
                fp = root / "ragas" / f"{m}_{z}_0_k{k}.json"
                if fp.exists():
                    for c, v in load(fp)["by_ctx"].items():
                        for q, res in zip(v["qids"], v["results"]):
                            faith[(m, k, int(c), q)] = res.get("faithfulness")
        for c in ctxs:
            L = [f"# 청크 {z}자 · 문맥 한도 {c}토큰 — 3방식 비교", "", f"[목록으로](index.md) · 결과 폴더 `{lp}` · 오버랩 0%", ""]
            for k in ks:
                L += [f"## k = {k}", "", "### ① 3방식 비교 (전체 평균)", "",
                      "| 항목 | " + " | ".join(MODES) + " |", "|---|" + "---|" * len(MODES)]
                rows = {m: M["retrieval"].get(f"{z}|0|{c}|{m}|{k}") for m in MODES}
                fa = {m: M["ragas"].get(f"{z}|0|{c}|{m}|{k}") for m in MODES}
                ee = {m: M["e2e"].get(f"{lp}|{z}|{k}|{c}|{m}") for m in MODES}

                def line(name, fn):
                    L.append(f"| {name} | " + " | ".join(fn(m) for m in MODES) + " |")
                line("Recall ① 문서", lambda m: f(rows[m] and rows[m]["recall_book"]))
                line("Recall ② 쪽", lambda m: f(rows[m] and rows[m]["recall_page"]))
                line("Recall ③ 쪽+인용문", lambda m: f(rows[m] and rows[m]["recall_pq"]))
                line("Hit ① 문서 / ② 쪽 / ③ 쪽+인용문", lambda m: "-" if not rows[m] else f"{f(rows[m]['hit'], 2)} / {f(rows[m]['hit_page'], 2)} / {f(rows[m]['hit_pq'], 2)}")
                line("모든그룹 충족률 ① / ② / ③", lambda m: "-" if not rows[m] else f"{f(rows[m]['all_book'], 2)} / {f(rows[m]['all_page'], 2)} / {f(rows[m]['all_pq'], 2)}")
                line("문맥에 들어간 청크(평균) / 문항당 밀려난 청크", lambda m: "-" if not rows[m] else f"{f(rows[m]['n_used'], 2)} / {f(rows[m]['n_drop'], 2)}")
                line("행동 일치율(전체 / 답 / 되묻기 / 보류)", lambda m: "-" if not rows[m] else "{} / {} / {} / {}".format(*(f(rows[m]["act"].get(x), 2) for x in ("match", "match_answer", "match_clarify", "match_abstain"))))
                line("근거 문서 인용률", lambda m: f(rows[m] and rows[m]["act"]["cites"], 2))
                line("답변 입력 / 출력 토큰(평균)", lambda m: "-" if not rows[m] else f"{rows[m]['act']['tin']:.0f} / {rows[m]['act']['tout']:.0f}")
                line("faithfulness (n)", lambda m: "-" if not fa[m] else f"{f(fa[m]['faithfulness'])} ({fa[m]['n']})")
                line("전체 시간: 검색 / LLM / 합계(초)", lambda m: "-" if not ee[m] else f"{f(ee[m]['retr'], 2)} / {f(ee[m]['llm'], 2)} / {f(ee[m]['mean'], 2)}")
                L += ["", "### ② 질문별 3방식 비교", "",
                      "칸의 읽는 법: `사용/상위k`(문맥에 들어간 청크 / 상위 k) · 근거(쪽+인용문을 가져왔는가, 그룹 비율) · 행동(기대와 같은가) · faithfulness(있는 문항만). ✅ 맞음 ❌ 틀림 - 해당 없음", "",
                      "| 질문 | 기대 | " + " | ".join(MODES) + " |", "|---|---|" + "---|" * len(MODES)]
                for q in qids:
                    cells = []
                    for m in MODES:
                        row = R["modes"][m].get(q)
                        if not row:
                            cells.append("-")
                            continue
                        kk = row["k"][str(k)]
                        cx = kk["ctx"][str(c)]
                        mm = cx.get("m")
                        rec = A.get((m, q, k, c))
                        ev = "-" if mm is None else f"{mark(mm['all_pq'])}{mm['recall_pq']:.2f}"
                        ac = "-" if not rec else f"{mark(rec['status_match'])}{rec['answer']['status']}"
                        fl = faith.get((m, k, c, q))
                        cells.append(f"{cx['n_used']}/{kk['n_top']} · {ev} · {ac}" + ("" if fl is None else f" · f{fl:.2f}"))
                    exp = Q[q].get("expected_action") or Q[q].get("expected") or "-"
                    L.append(f"| {q} | {exp} | " + " | ".join(cells) + " |")
                L.append("")
            (out / f"size{z}_ctx{c}.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"저장: {out} (조합 {len(sizes) * len(ctxs)}개 + index.md)")


if __name__ == "__main__":
    main()
