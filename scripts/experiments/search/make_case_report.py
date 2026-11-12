"""grid_kset.py 결과에서 문항별 사례 보고서(마크다운)를 만든다: 질문 -> 청크 선별 과정 -> k개 청크(본문 전문, 문맥 한도에서 사용/밀려남) ->
골든 근거 quote -> 골든 답변(reference_answer)과 최종 LLM 답변 비교 -> faithfulness.

    # 한 설정(방식·크기·k)의 모든 문항
    uv run python scripts/experiments/search/make_case_report.py --in results/<실험>/laptop1 --mode hybrid_rerank --size 900 --k 11 --out results/<실험>/cases/hybrid_rerank_900_k11.md
    # 한도 때문에 청크가 밀려난 문항만
    ... --only-dropped
    # 모든 방식·크기·k를 한 번에(폴더에 파일 여러 개)
    uv run python scripts/experiments/search/make_case_report.py --in results/<실험>/laptop1 --all --out-dir results/<실험>/cases

저장된 값만 보여준다. 없는 값(예: 채점하지 않은 faithfulness)은 '-'. 골든 답변 비교의 '필수 사실 포함'은 사실을 이루는 단어가 답변에 모두 있는지만 보며 의미 일치와 다를 수 있다.
"""
import argparse
import json
import re
from pathlib import Path

ns = lambda s: re.sub(r"[\s|]+", "", s)  # noqa: E731
STATUS_OF = {"answer": "answered", "clarify": "needs_clarification", "abstain": "abstained"}


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True, help="grid_kset.py 결과 폴더")
    p.add_argument("--mode", choices=("naive", "hybrid", "hybrid_rerank"))
    p.add_argument("--size", type=int)
    p.add_argument("--pct", type=int, default=0)
    p.add_argument("--k", type=int)
    p.add_argument("--out")
    p.add_argument("--all", action="store_true", help="폴더에 있는 모든 (방식, 크기, k) 보고서를 --out-dir에 만든다")
    p.add_argument("--out-dir")
    p.add_argument("--only-dropped", action="store_true", help="한도 때문에 청크가 밀려난 문항만")
    p.add_argument("--text", choices=("full", "head"), default="full", help="청크 본문: full = 전문, head = 앞 150자")
    return p.parse_args()


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def tok(text):
    return len(text) // 2 + 1  # src/answer/context.py count_tokens와 같은 추정


def report(root, mode, size, pct, k, only_dropped, text_mode):
    Q = load(root / "questions.json")
    R = load(root / "retrieval" / f"{size}_{pct}.json")
    chunks = R["chunks"]
    ctxs = sorted(R["ctxs"], reverse=True)
    A = {}
    ap = root / "answers" / f"{size}_{pct}.json"
    if ap.exists():
        for rec in load(ap)["records"]:
            if rec["mode"] == mode and rec["k"] == k:
                A[(rec["qid"], rec["ctx"])] = rec
    G = {}
    gp = root / "ragas" / f"{mode}_{size}_{pct}_k{k}.json"
    if gp.exists():
        for lim, v in load(gp)["by_ctx"].items():
            for qid, res in zip(v["qids"], v["results"]):
                G[(qid, int(lim))] = res["faithfulness"]
    env = load(root / "env.json") if (root / "env.json").exists() else {}
    rows = R["modes"][mode]
    qids = list(rows)
    drop_q = [q for q in qids if any(rows[q]["k"][str(k)]["n_top"] > rows[q]["k"][str(k)]["ctx"][str(c)]["n_used"] for c in ctxs)]
    if only_dropped:
        qids = drop_q
    L = [f"# 사례 보고서: {mode} · 청크 크기 {size}자 · 오버랩 {pct}% · k={k} · 문맥 한도 {', '.join(map(str, ctxs))}\n",
         "## 실험 조건\n",
         f"- 사용 데이터: Basic 문서 `data/shipping/documents`(청크 {R['chunks_total']}개), 골든 데이터셋 3세트(development, additional, expansion_validation) 중 문항 {len(rows)}개",
         f"- 변인: 방식={mode}, 청크 크기={size}자, 오버랩={pct}%, k={k}, 문맥 토큰 한도={ctxs}(토큰=글자÷2+1, 넘는 청크와 뒤 청크는 통째로 제외)",
         "- 고정: 임베딩 E5 small, 리랭커 bge-reranker-v2-m3, POOL 20(후보 20), RRF 상수 60, 생성 모델·프롬프트·설정은 `src/config.py`와 같음",
         f"- computing_env: CPU {env.get('cpu_name') or '-'} / RAM {env.get('ram_total_gb')}GB / GPU {env.get('gpu') or '-'} / torch {env.get('torch') or '-'} / 스레드 {env.get('threads')} / 실행 {env.get('run_at') or '-'} / git {env.get('git_commit') or '-'}",
         f"- 이 보고서에 담은 문항: {len(qids)}개" + (f" (한도 때문에 청크가 밀려난 문항만; 전체 {len(rows)}개 중 {len(drop_q)}개)" if only_dropped else f" (그중 한도 때문에 청크가 밀려난 문항 {len(drop_q)}개)"),
         "- 읽는 법: ✅ = 문맥에 사용, ❌ = 한도를 넘어 밀려남, ★ = 골든 근거(쪽 일치 + 인용문 앞 40자 포함). 한도 열은 큰 값 → 작은 값 순.\n"]
    for n, qid in enumerate(qids, 1):
        q, row = Q[qid], rows[qid]
        st_, top = row["stages"], row["top_ids"][:k]
        kinfo = row["k"][str(k)]
        L.append(f"---\n\n## {n}. {qid}  (기대 동작: {q['expected_action']})\n")
        L.append(f"**질문**: {q['question']}\n")
        # 1) 선별 과정
        n_d, n_b, n_r = len(st_.get("dense", [])), len(st_.get("bm25", [])), len(st_.get("rrf", []))
        flow = {"naive": f"E5 벡터 검색 상위 {len(st_['final'])}개 → 상위 {k}개", "hybrid": f"E5 후보 {n_d}개 + BM25 후보 {n_b}개 → RRF 합침 → 상위 {k}개",
                "hybrid_rerank": f"E5 후보 {n_d}개 + BM25 후보 {n_b}개 → RRF 후보 {n_r}개 → 리랭커 재정렬 → 상위 {k}개"}[mode]
        L.append(f"**청크 선별 과정**: {flow} → 문맥 한도 적용 (검색 시간 {row['retrieval_s'] * 1000:.0f}ms, 선별 기록이 retrieve() 결과와 같음: {st_.get('same_as_retrieve')})\n")
        rank_of = lambda lst, cid: next((i + 1 for i, x in enumerate(lst) if x[0] == cid), None)  # noqa: E731
        score_of = {c: s for c, s in st_["final"]}
        golds = [(e["book_id"], e["page"], e["quote"]) for g in q["evidence_groups"] for e in g]
        is_gold = lambda cid: any(chunks[cid]["book_id"] == b and chunks[cid]["page"] == p and ns(qt)[:40] in ns(chunks[cid]["text"]) for b, p, qt in golds)  # noqa: E731
        head = ["순위", "청크 id", "글자", "토큰", "누적", "E5 순위", "BM25 순위", "RRF 순위", "최종 점수"] + [f"한도 {c}" for c in ctxs] + ["골든"]
        L.append("| " + " | ".join(head) + " |")
        L.append("|" + "---|" * len(head))
        cum = 0
        for i, cid in enumerate(top, 1):
            t = tok(chunks[cid]["text"])
            cum += t
            marks = ["✅" if cid in kinfo["ctx"][str(c)]["ids"] else "❌" for c in ctxs]
            L.append(f"| {i} | {cid} | {len(chunks[cid]['text'])} | {t} | {cum} | {rank_of(st_.get('dense', []), cid) or '-'} | {rank_of(st_.get('bm25', []), cid) or '-'} | "
                     f"{rank_of(st_.get('rrf', []), cid) or '-'} | {score_of.get(cid, 0):.4f} | " + " | ".join(marks) + f" | {'★' if is_gold(cid) else ''} |")
        L.append("")
        # 2) 골든
        L.append("**골든 데이터셋**\n")
        for g_i, g in enumerate(q["evidence_groups"], 1):
            for e in g:
                L.append(f"- 근거 그룹 {g_i}: `{e['book_id']}` {e['page']}쪽 — quote: “{e['quote']}”")
        if not q["evidence_groups"]:
            L.append("- 근거 없음(되묻기·보류 문항)")
        L.append(f"- **골든 답변(reference_answer)**: {q['reference_answer']}")
        L.append(f"- 필수 사실(required_facts): {q['required_facts']}")
        if q.get("forbidden_claims"):
            L.append(f"- 금지 주장(forbidden_claims): {q['forbidden_claims']}")
        L.append("")
        # 3) 청크 본문
        L.append("**가져온 청크 본문** (순위 순, ❌는 문맥에 못 들어간 청크)\n")
        used_min = kinfo["ctx"][str(min(ctxs))]["ids"]
        for i, cid in enumerate(top, 1):
            body = chunks[cid]["text"] if text_mode == "full" else chunks[cid]["text"][:150] + ("…" if len(chunks[cid]["text"]) > 150 else "")
            flag = ("❌ 한도 " + ", ".join(str(c) for c in ctxs if cid not in kinfo["ctx"][str(c)]["ids"]) + "에서 밀려남") if cid not in kinfo["ctx"][str(max(ctxs))]["ids"] or cid not in used_min else "✅ 모든 한도에서 사용"
            L.append(f"<details><summary>{i}위 · {cid} ({chunks[cid]['book_id']} {chunks[cid]['page']}쪽, {len(chunks[cid]['text'])}자) {'★ 골든 근거' if is_gold(cid) else ''} — {flag}</summary>\n\n{body}\n\n</details>\n")
        # 4) LLM 답변 vs 골든 답변 (문맥이 같은 한도는 묶는다)
        L.append("**최종 LLM 답변 vs 골든 답변**\n")
        groups = {}
        for c in ctxs:
            ids = tuple(kinfo["ctx"][str(c)]["ids"])
            groups.setdefault(ids, []).append(c)
        for ids, cs in groups.items():
            rec = A.get((qid, cs[0]))
            title = f"한도 {', '.join(map(str, cs))}" + f" — 문맥 {len(ids)}개 사용(밀려남 {len(top) - len(ids)}개)"
            if not rec or not rec.get("answer"):
                L.append(f"- **{title}**: 답변 없음" + (f" (오류: {rec.get('error')})" if rec else " (answers 단계 미실행)") + "\n")
                continue
            a = rec["answer"]
            exp = STATUS_OF.get(q["expected_action"], q["expected_action"])
            ans_ns = ns(a["answer"])
            facts = [(fct, all(ns(w) in ans_ns for w in fct.split())) for fct in q["required_facts"]]  # 사실을 이루는 단어가 답변에 모두 있는지(통째 문자열 일치는 어순·조사 때문에 정답도 놓친다)
            cited = [rec["source_map"].get(s) for s in a["source_ids"]]
            fa = G.get((qid, cs[0]))
            L.append(f"- **{title}**")
            L.append(f"  - 상태: `{a['status']}` (기대 `{exp}` → {'일치' if a['status'] == exp else '**불일치**'})")
            L.append(f"  - LLM 답변: {a['answer']}")
            L.append(f"  - 이유: {a['reason']}")
            L.append(f"  - 인용 출처: {cited}")
            L.append(f"  - 골든 답변: {q['reference_answer']}")
            L.append(f"  - 필수 사실 포함(단어 기준): " + (", ".join(f"{'✓' if ok else '✗'} {fct}" for fct, ok in facts) if facts else "해당 없음"))
            L.append(f"  - 토큰 입력 {rec.get('input_tokens')} / 출력 {rec.get('output_tokens')}, LLM 시간 {(rec.get('llm_ms') or 0) / 1000:.2f}s, 호출 {rec.get('llm_calls')}회")
            L.append(f"  - RAGAS faithfulness: {'-' if fa is None else f'{fa:.3f}'}\n")
    return "\n".join(L) + "\n"


def main():
    a = parse()
    root = Path(a.inp)
    if a.all:
        out_dir = Path(a.out_dir or root / "report" / "cases")
        out_dir.mkdir(parents=True, exist_ok=True)
        for rp in sorted((root / "retrieval").glob("*.json")):
            R = load(rp)
            for mode in R["modes"]:
                for k in R["ks"]:
                    path = out_dir / f"{mode}_{R['size']}_{R['pct']}_k{k}.md"
                    path.write_text(report(root, mode, R["size"], R["pct"], k, a.only_dropped, a.text), encoding="utf-8", newline="\n")
        print(f"저장: {out_dir} ({len(list(out_dir.glob('*.md')))}개)")
        return
    if not (a.mode and a.size and a.k):
        raise SystemExit("--mode --size --k가 필요하다(또는 --all)")
    a.out = a.out or str(root / "report" / "cases" / f"{a.mode}_{a.size}_{a.pct}_k{a.k}.md")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(report(root, a.mode, a.size, a.pct, a.k, a.only_dropped, a.text), encoding="utf-8", newline="\n")
    print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
