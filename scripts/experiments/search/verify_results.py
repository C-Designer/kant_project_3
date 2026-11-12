"""grid_kset.py 결과 폴더가 끝까지 제대로 만들어졌는지 확인한다(AI·사람 공통의 '끝났다' 판정). 값을 고치지 않고 읽기만 한다.

    uv run python scripts/experiments/search/verify_results.py --in results/exp0020/laptop1 --k 11,5 \\
      --sizes 600,700,800,900 --pcts 0 --context-max 3000,3400,3800,4200 --ragas-sizes 600,700,800,900 --e2e-modes naive,hybrid,hybrid_rerank

실행할 때 쓴 옵션과 **같은 값**을 준다. 결과: 항목마다 ✅(통과) / ⚠(주의, 진행 가능하나 보고에 적는다) / ❌(실패, 해당 단계를 다시 돌린다).
종료 코드: ❌가 하나라도 있으면 1, 없으면 0.
"""
import argparse
import json
import sys
from pathlib import Path

MODES_ALL = ("naive", "hybrid", "hybrid_rerank")
BASE = (900, 0, 5)
SETS = ("development", "additional", "expansion_validation")


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--k", required=True)
    p.add_argument("--sizes", default="100,200,300,400,500,600,700,800,900")
    p.add_argument("--pcts", default="0,10,20")
    p.add_argument("--context-max", default="3000")
    p.add_argument("--modes", default="naive,hybrid,hybrid_rerank")
    p.add_argument("--e2e-modes", default="hybrid_rerank")
    p.add_argument("--ragas-sizes", default="500,900")
    p.add_argument("--e2e-workers", type=int, default=1, help="본 실행에 쓴 --e2e-workers(결과 파일에 기록된 값과 같아야 한다)")
    p.add_argument("--limit-q", type=int, default=0)
    p.add_argument("--expect-gpu", default="RTX 5060")
    p.add_argument("--skip", default="", help="검사하지 않을 단계(쉼표): retrieval,answers,e2e,ragas")
    p.add_argument("-v", "--verbose", action="store_true", help="통과(✅) 항목도 모두 출력")
    return p.parse_args()


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    a = parse()
    root = Path(a.inp)
    ks = [int(x) for x in a.k.split(",")]
    sizes = [int(x) for x in a.sizes.split(",")]
    pcts = [int(x) for x in a.pcts.split(",")]
    ctxs = sorted({int(x) for x in a.context_max.split(",")}, reverse=True)
    modes = a.modes.split(",")
    e2e_modes = a.e2e_modes.split(",")
    ragas_sizes = [int(x) for x in a.ragas_sizes.split(",")]
    skip = set(filter(None, a.skip.split(",")))
    out = []

    def add(level, name, detail=""):
        out.append((level, name, detail))

    settings = [(z, p) for z in sizes for p in pcts]
    if BASE[:2] not in settings:
        settings.append(BASE[:2])
    ks_for = lambda z, p: ks + ([BASE[2]] if (z, p) == BASE[:2] and BASE[2] not in ks else [])  # noqa: E731

    # 0. 환경
    ep = root / "env.json"
    if not ep.exists():
        add("❌", "env.json", "없음: check 단계가 안 돌았다(`--stages check`)")
    else:
        e = load(ep)
        add("✅" if e.get("gpu") and a.expect_gpu.lower() in e["gpu"].lower() else "❌", "GPU", f"{e.get('gpu')} (기준 {a.expect_gpu})")
        add("✅" if e.get("cpu_cores_applied") == e.get("cpu_cores_requested") else "❌", "CPU 코어 제한", f"요청 {e.get('cpu_cores_requested')} / 적용 {e.get('cpu_cores_applied')}")
        add("✅" if e.get("threads") == 8 and e.get("gpu_fraction") == 0.5 else "⚠", "스레드·GPU 비율", f"threads {e.get('threads')}, gpu_fraction {e.get('gpu_fraction')} (기준 8, 0.5)")
        add("✅" if e.get("on_ac_power") is not False else "⚠", "전원 연결", str(e.get("on_ac_power")))
        add("✅" if not e.get("git_dirty") else "⚠", "src 수정 여부(git_dirty)", str(e.get("git_dirty")))
        add("✅" if not e.get("limit_q") else "⚠", "문항 제한(limit_q)", f"{e.get('limit_q')} (진짜 실행이면 0이어야 한다)")
    qp = root / "questions.json"
    nq = len(load(qp)) if qp.exists() else 0
    add("✅" if nq and (not a.limit_q or nq <= 3 * a.limit_q) else "❌", "questions.json", f"{nq}문항" + (" (골든: reference_answer 포함)" if nq else ""))
    n_ev = sum(1 for v in load(qp).values() if v["evidence_groups"]) if nq else 0

    # 1. 검색
    if "retrieval" not in skip:
        for z, p in settings:
            f = root / "retrieval" / f"{z}_{p}.json"
            if not f.exists():
                add("❌", f"retrieval/{z}_{p}.json", "없음")
                continue
            r = load(f)
            miss_mode = [m for m in modes if m not in r["modes"]]
            n_rows = {m: len(v) for m, v in r["modes"].items()}
            bad_match = sum(1 for m in r["modes"].values() for v in m.values() if not v["stages"].get("same_as_retrieve", True))
            no_stage = sum(1 for m in r["modes"].values() for v in m.values() if "stage_ms" not in v["stages"])
            ok = not miss_mode and all(n == nq for n in n_rows.values()) and set(r["ctxs"]) == set(ctxs)
            add("✅" if ok else "❌", f"retrieval/{z}_{p}.json", f"방식 {list(n_rows)}, 문항 {set(n_rows.values())}, 한도 {r['ctxs']}")
            if bad_match:
                add("⚠", f"retrieval/{z}_{p}.json 선별 기록 불일치", f"{bad_match}건(retrieve() 결과와 선별 기록이 다름)")
            if no_stage:
                add("⚠", f"retrieval/{z}_{p}.json 내부 단계 시간 누락", f"{no_stage}건")

    # 2. 답변
    if "answers" not in skip:
        for z, p in settings:
            f = root / "answers" / f"{z}_{p}.json"
            if not f.exists():
                add("❌", f"answers/{z}_{p}.json", "없음(오류 5% 초과로 저장 안 됐을 수 있다: 로그 확인)")
                continue
            d = load(f)
            want = len(modes) * nq * len(ks_for(z, p)) * len(ctxs)
            recs = d["records"]
            ok_recs = [r for r in recs if r.get("answer")]
            err = len(recs) - len(ok_recs)
            none_tok = sum(1 for r in ok_recs if r.get("input_tokens") is None or r.get("output_tokens") is None)
            lv = "✅" if len(recs) == want and err / max(1, len(recs)) <= 0.05 and none_tok == 0 else ("⚠" if len(recs) == want else "❌")
            add(lv, f"answers/{z}_{p}.json", f"레코드 {len(recs)}/{want}, 오류 {err}, 토큰 None {none_tok}, 새 호출 {d.get('calls')}")

    # 3. 직렬 전체 시간
    if "e2e" not in skip:
        for z in sizes:
            f = root / "e2e" / f"{z}_0.json"
            if not f.exists():
                add("❌", f"e2e/{z}_0.json", "없음")
                continue
            d = load(f)
            miss = [(m, k) for m in e2e_modes for k in ks if str(k) not in d["modes"].get(m, {})]
            n_err = sum(1 for m in d["modes"].values() for rows in m.values() for x in rows for c in x["ctx"].values() if c.get("error"))
            slow = bool((d.get("gpu_end") or {}).get("thermal_or_hw_slowdown"))
            wk = d.get("e2e_workers", 1)
            if wk != a.e2e_workers:
                add("❌", f"e2e/{z}_0.json 동시 호출 수", f"기록 {wk} / 기대 {a.e2e_workers}: 노트북 사이 같은 값이어야 한다")
            add("✅" if not miss and n_err == 0 and not slow else ("⚠" if not miss else "❌"), f"e2e/{z}_0.json",
                f"방식 {list(d['modes'])}, k {sorted({int(k) for m in d['modes'].values() for k in m})}, 오류 {n_err}, 동시 호출 {d.get('e2e_workers', 1)}" + (", GPU 열/전력 제한 신호" if slow else ""))
        for nm in ("start", "end"):
            ok_a = (root / "e2e" / f"anchor_{nm}.json").exists()
            add("✅" if ok_a else "❌", f"e2e/anchor_{nm}.json", "공통 기준점(시간대 흔들림 확인용)" if ok_a else "없음: e2e 단계가 끝까지 안 돌았다")

    # 4. faithfulness
    if "ragas" not in skip:
        targets = {(z, 0, k) for z in ragas_sizes if z in sizes for k in ks} | {BASE}
        for z, p, k in sorted(targets):
            for m in modes:
                f = root / "ragas" / f"{m}_{z}_{p}_k{k}.json"
                if not f.exists():
                    add("❌", f"ragas/{m}_{z}_{p}_k{k}.json", "없음")
                    continue
                g = load(f)
                res = [x for v in g["by_ctx"].values() for x in v["results"]]
                none = sum(1 for x in res if x["faithfulness"] is None)
                short = sum(1 for x in res if x["n_runs"] != 3)
                add("✅" if res and none == 0 and short == 0 else "⚠", f"ragas/{m}_{z}_{p}_k{k}.json", f"채점 {len(res)}건(고유 {g['scored']}), 점수 None {none}, 3회 미만 {short}")

    # 5. 사용량
    up = root / "usage.json"
    if not up.exists():
        add("❌", "usage.json", "없음")
    else:
        u = load(up)
        need = [s for s in ("check", "retrieval", "answers", "e2e", "ragas") if s not in skip]
        miss = [s for s in need if s not in u]
        add("✅" if not miss else "⚠", "usage.json", f"단계 {list(u)}" + (f", 빠짐 {miss}" if miss else ""))

    # 출력
    n = {"✅": 0, "⚠": 0, "❌": 0}
    for lv, name, d in out:
        n[lv] += 1
    for lv, name, d in out:
        if lv != "✅" or a.verbose:
            print(f"{lv} {name}: {d}")
    print(f"\n요약: ✅ {n['✅']}  ⚠ {n['⚠']}  ❌ {n['❌']}  (근거 있는 문항 {n_ev}개, 질문 {nq}개)")
    if n["❌"]:
        print("판정: **실패**. ❌ 항목의 단계를 같은 명령으로 다시 실행한다(끝난 설정은 건너뛴다). 해결이 안 되면 멈추고 사람에게 알린다.")
    else:
        print("판정: **통과**" + (" (⚠는 보고서의 '실패·이상 기록'에 적는다)" if n["⚠"] else ""))
    sys.exit(1 if n["❌"] else 0)


if __name__ == "__main__":
    main()
