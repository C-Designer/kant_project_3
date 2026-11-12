"""질문마다 .md 파일 하나로 분리해서 내보낸다: 가져온 청크 k개(본문 전문 + 메타데이터) / 골든의 기대 book_id·page·quote / 골든 → 청크 매핑 /
원본 쪽 텍스트(별도 .md). grid_kset.py 결과 폴더가 입력이다. GPU·LLM이 필요 없다(청킹만 다시 한다).

    uv run python scripts/experiments/search/export_question_md.py --in results/<실험>/laptop1 --mode hybrid_rerank --size 900 --k 5 --out-dir results/<실험>/question_md

만드는 것
    <out-dir>/index.md                  질문 목록과 판정 요약(문서 Recall, 쪽+인용문, 밀려난 청크)
    <out-dir>/questions/<세트>_<문항>.md   질문 하나: 골든 기대, 골든→청크 매핑, 가져온 청크 k개(메타데이터 표 + 본문), 판정, LLM 답변
    <out-dir>/source_pages/<book>-p<쪽>.md  골든이 가리키는 원본 쪽 텍스트(그 쪽을 나눈 청크 id 목록 포함)

매핑은 같은 크기·오버랩으로 청킹을 다시 해서 만든다. 결과 파일의 청크 id·본문과 다르면 경고한다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.search import chunking  # noqa: E402

ns = lambda s: re.sub(r"[\s|]+", "", s)  # noqa: E731
STATUS_OF = {"answer": "answered", "clarify": "needs_clarification", "abstain": "abstained"}
tok = lambda t: len(t) // 2 + 1  # noqa: E731  (src/answer/context.py count_tokens와 같은 추정)


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True, help="grid_kset.py 결과 폴더")
    p.add_argument("--mode", required=True, choices=("naive", "hybrid", "hybrid_rerank"))
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--pct", type=int, default=0)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--ctx", type=int, help="문맥 한도(기본: 결과 파일의 가장 큰 한도)")
    p.add_argument("--out-dir", help="기본: 결과 폴더 안의 report/questions_md/<방식>_<크기>_<오버랩>_k<k>/")
    p.add_argument("--qids", nargs="*", help="이 문항만(예: development/S-DEV-01)")
    return p.parse_args()


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def rechunk(size, pct):
    """저장소 청킹 + 오버랩(grid_kset.py와 같은 방식). 반환: ({chunk_id: 정보}, {(book, page): 원본 쪽 글})"""
    ov = round(size * pct / 100)
    chunks, pages_text = {}, {}
    for pdf in sorted((ROOT / "data" / "shipping" / "documents").glob("*.pdf")):
        pages = chunking.extract_pages(pdf)
        for page_no, text in pages:
            pages_text[(pdf.stem, page_no)] = text
        res = chunking.chunk_pages(pdf.name, pages, size=size, overlap=0)
        for i, (text, meta) in enumerate(res):
            if ov and i and res[i - 1][1].book_id == meta.book_id and res[i - 1][1].page == meta.page:
                head, nl, body = text.rpartition("\n")
                tail = res[i - 1][0].rpartition("\n")[2][-ov:]
                sp = tail.find(" ")
                if 0 <= sp < len(tail) - 1:
                    tail = tail[sp + 1:]
                text = head + nl + tail + body
            chunks[meta.chunk_id] = dict(text=text, book=meta.book_id, page=meta.page, file=meta.file_name)
    return chunks, pages_text


def quote_in(chunk_text, quote):
    return ns(quote)[:40] in ns(chunk_text)  # 지표와 같은 규칙: 인용문 앞 40자(공백·| 제거)


def mark(text, snippet):
    """text 안에서 snippet(공백·`|`를 무시하고 비교)이 있는 구간을 <mark>로 감싼다. 읽을 때 골든 quote·청크 위치가 바로 보이게 한다.
    전체가 안 맞으면 앞 40자로 다시 찾고, 그래도 못 찾으면 그대로 돌려준다."""
    idx = [i for i, ch in enumerate(text) if not re.match(r"[\s|]", ch)]
    nt = "".join(text[i] for i in idx)
    s_ = ns(snippet)
    p = nt.find(s_) if s_ else -1
    if p < 0 and len(s_) > 40:
        s_ = s_[:40]
        p = nt.find(s_)
    if p < 0:
        return text
    a_, b_ = idx[p], idx[p + len(s_) - 1] + 1
    return text[:a_] + "<mark>" + text[a_:b_] + "</mark>" + text[b_:]


EVAL_DIR = ROOT / "data" / "shipping" / "evaluation"
_eval_cache = {}


def golden_row(qid):
    """질문 id(`세트/문항`) -> 질문 파일·골든 파일에서의 위치. 두 파일의 질문 글이 같은지도 확인한다."""
    s_, _, gid = qid.partition("/")
    if s_ not in _eval_cache:
        qs = json.loads((EVAL_DIR / f"{s_}_questions.json").read_text(encoding="utf-8"))
        gs = json.loads((EVAL_DIR / f"{s_}.json").read_text(encoding="utf-8"))
        _eval_cache[s_] = (qs, {x["id"]: x for x in gs}, [x["id"] for x in gs])
    qs, gs, gorder = _eval_cache[s_]
    pos = next(i for i, x in enumerate(qs, 1) if x["id"] == gid)
    g = gs[gid]
    groups = [x for x in g.get("evidence_groups", []) if x]
    return dict(set=s_, id=gid, q_file=f"data/shipping/evaluation/{s_}_questions.json", q_pos=pos, q_total=len(qs),
                g_file=f"data/shipping/evaluation/{s_}.json", g_pos=gorder.index(gid) + 1, g_total=len(gorder),
                same_text=qs[pos - 1]["question"] == g.get("question"), g_fields=list(g.keys()), n_groups=len(groups),
                n_items=sum(len(x) for x in groups), expected_action=g["expected_action"])


def main():
    a = parse()
    root = Path(a.inp)
    out = Path(a.out_dir or root / "report" / "questions_md" / f"{a.mode}_{a.size}_{a.pct}_k{a.k}")
    Q = load(root / "questions.json")
    R = load(root / "retrieval" / f"{a.size}_{a.pct}.json")
    ctxs = sorted(R["ctxs"], reverse=True)
    ctx = a.ctx or ctxs[0]
    if str(ctx) not in map(str, ctxs):
        raise SystemExit(f"한도 {ctx}가 결과에 없다: {ctxs}")
    rows = R["modes"][a.mode]
    A = {}
    ap = root / "answers" / f"{a.size}_{a.pct}.json"
    if ap.exists():
        for rec in load(ap)["records"]:
            if rec["mode"] == a.mode and rec["k"] == a.k and rec["ctx"] == ctx:
                A[rec["qid"]] = rec
    G = {}
    gp = root / "ragas" / f"{a.mode}_{a.size}_{a.pct}_k{a.k}.json"
    if gp.exists():
        for qid, res in zip(load(gp)["by_ctx"].get(str(ctx), {}).get("qids", []), load(gp)["by_ctx"].get(str(ctx), {}).get("results", [])):
            G[qid] = res["faithfulness"]

    allc, pages_text = rechunk(a.size, a.pct)
    bad = [cid for cid, c in R["chunks"].items() if cid not in allc or allc[cid]["text"] != c["text"]]
    if bad:
        print(f"경고: 결과 파일의 청크 {len(bad)}개가 다시 만든 청킹과 다르다(청킹 설정·코드가 달랐을 수 있다): {bad[:3]}")
    by_page = {}
    for cid, c in allc.items():
        by_page.setdefault((c["book"], c["page"]), []).append(cid)

    (out / "questions").mkdir(parents=True, exist_ok=True)
    (out / "source_pages").mkdir(parents=True, exist_ok=True)
    written_pages, index = set(), []

    def loc(cid):
        """청크 본문이 원본 쪽 글(extract_pages 결과)의 몇 번째 글자에서 시작하는지. 청크의 마지막 줄(본문) 앞부분으로 찾는다. 못 찾으면 None."""
        c = allc[cid]
        page_text = pages_text.get((c["book"], c["page"]), "")
        body = c["text"].rpartition("\n")[2]
        i = page_text.find(body[:40]) if body else -1
        return None if i < 0 else (i + 1, min(len(page_text), i + len(body)), len(page_text))

    def write_page(book, page):
        """원본 쪽 .md(질문과 무관하게 쪽마다 하나). 그 쪽을 나눈 청크 표(글자 수, 쪽 안 위치)와 원본 쪽 글이 들어간다. 파일명 = <book>-p<쪽>.md"""
        key = (book, page)
        if key in written_pages or key not in pages_text:
            return
        written_pages.add(key)
        ids = by_page.get(key, [])
        rows_ = "\n".join(f"| `{c}` | {len(allc[c]['text'])}자 | " + (lambda L_: f"{L_[0]}~{L_[1]}번째 글자 (쪽 글 {L_[2]}자)" if L_ else "-")(loc(c)) + " |" for c in ids)
        (out / "source_pages" / f"{book}-p{page}.md").write_text(
            f"# {book} · {page}쪽 (원본 쪽 텍스트)\n\n- 파일: `{allc[ids[0]]['file'] if ids else book + '.pdf'}` / book_id: `{book}` / 쪽: {page}\n"
            f"- 청킹: 크기 {a.size}자 · 오버랩 {a.pct}%. 이 쪽은 청크 {len(ids)}개로 나뉜다.\n\n"
            f"## 이 쪽 → 청크 매핑\n\n| 청크 id | 길이 | 원본 쪽 안 위치 |\n|---|---|---|\n{rows_}\n\n"
            f"(오버랩이 있으면 청크 앞부분이 앞 청크 끝과 겹쳐 위치가 앞 청크의 끝 쪽으로 잡힌다. 위치는 청크 본문 앞 40자를 원본 쪽 글에서 찾은 값이다.)\n\n"
            f"## 원본 쪽 글\n\n아래 글은 청킹 입력(`extract_pages`가 쪽을 정리한 글, 첫 줄은 문서 제목과 담당 팀)이다.\n\n---\n\n{pages_text[key]}\n", encoding="utf-8", newline="\n")

    qids = a.qids or list(rows)
    for qid in qids:
        q, row = Q[qid], rows[qid]
        gm = golden_row(qid)
        top_all = row["top_ids"]
        top = top_all[: a.k]
        used = set(row["k"][str(a.k)]["ctx"][str(ctx)]["ids"])
        used_by = {lim: set(row["k"][str(a.k)]["ctx"][str(lim)]["ids"]) for lim in ctxs}
        chunks = R["chunks"]
        st_ = row["stages"]
        rank_of = lambda lst, cid: next((i + 1 for i, x in enumerate(lst) if x[0] == cid), None)  # noqa: E731
        score = {c: s for c, s in st_["final"]}
        entries = [(gi, e) for gi, g in enumerate(q["evidence_groups"], 1) for e in g]
        # 골든 -> 청크 매핑(인덱스 전체에서 quote가 든 청크)
        mapping = []
        for gi, e in entries:
            cand = [cid for cid in by_page.get((e["book_id"], e["page"]), []) if quote_in(allc[cid]["text"], e["quote"])]
            mapping.append((gi, e, cand))
            write_page(e["book_id"], e["page"])
        golds = [(e["book_id"], e["page"], e["quote"]) for _, e in entries]
        is_gold = lambda cid: any(chunks[cid]["book_id"] == b and chunks[cid]["page"] == p and quote_in(chunks[cid]["text"], qt) for b, p, qt in golds)  # noqa: E731
        ref_docs = sorted({e["book_id"] for _, e in entries})
        got_docs = {chunks[c]["book_id"] for c in top if c in used}
        recall = len(got_docs & set(ref_docs)) / len(ref_docs) if ref_docs else None
        group_hit = {}
        for gi, e, cand in mapping:
            group_hit[gi] = group_hit.get(gi, False) or any(c in used and c in top for c in cand)
        pq = sum(group_hit.values()) / len(group_hit) if group_hit else None
        dropped = [c for c in top if c not in used]
        drop_txt = " / ".join(f"{lim}: {len([c for c in top if c not in used_by[lim]])}" for lim in ctxs)  # 한도별 밀려난 청크 수

        L = [f"# {qid}", "", f"**질문**: {q['question']}", "",
             f"- 세트: {q['set']} / 기대 동작: `{q['expected_action']}`",
             f"- 설정: 방식 `{a.mode}` · 청크 크기 {a.size}자 · 오버랩 {a.pct}% · k={a.k} · 문맥 한도 {ctx}토큰",
             f"- 판정: Recall(문서) {'-' if recall is None else f'{recall:.2f}'} ({len(got_docs & set(ref_docs))}/{len(ref_docs)}문서) · 쪽+인용문(그룹) {'-' if pq is None else f'{pq:.2f}'} ({sum(group_hit.values())}/{len(group_hit)}그룹) · 한도로 밀려난 청크(상위 {a.k}개 중) " + ", ".join(f"한도 {lim}: {len([c for c in top if c not in used_by[lim]])}개" for lim in ctxs) + f" (위 판정은 한도 {ctx} 기준)", "",
             "## 0. 질문 ↔ 골든 데이터셋 매핑", "",
             "| 항목 | 값 |", "|---|---|",
             f"| 질문 id | `{gm['id']}` (세트 `{gm['set']}`, 이 폴더의 문항 키 `{qid}`) |",
             f"| 질문 파일 | `{gm['q_file']}` — {gm['q_total']}문항 중 **{gm['q_pos']}번째** |",
             f"| 골든 파일 | `{gm['g_file']}` — {gm['g_total']}항목 중 **{gm['g_pos']}번째**, 같은 id `{gm['id']}` |",
             f"| 질문 글 일치 | {'✅ 질문 파일과 골든 파일의 질문 글이 같다' if gm['same_text'] else '⚠ **두 파일의 질문 글이 다르다**'} |",
             f"| 골든 항목의 필드 | {', '.join(f'`{f_}`' for f_ in gm['g_fields'])} |",
             f"| 기대 동작 | `{gm['expected_action']}` |",
             f"| 골든 근거 | 그룹 {gm['n_groups']}개 · 항목 {gm['n_items']}개(book_id·page·quote) → 아래 1절과 2절 |",
             "| 쓰임 | 질문 글만 검색·답변에 넣는다. 골든의 나머지(정답·기대 동작·근거)는 **채점·보고에만** 쓴다 |", "",
             "## 1. 골든 데이터셋의 기대 (원본)", "",
             "한 그룹 안의 항목은 서로 **대안**이다(하나만 찾아도 그 그룹은 충족). 공식 Recall(문서)은 모든 그룹의 모든 문서를 합쳐 계산한다.", "",
             "| 그룹 | book_id | 쪽 | 원본 쪽 파일 | quote (전문) |", "|---|---|---|---|---|"]
        for gi, e in entries:
            L.append(f"| {gi} | {e['book_id']} | {e['page']} | [{e['book_id']}-p{e['page']}.md](../source_pages/{e['book_id']}-p{e['page']}.md) | {e['quote'].replace('|', '/')} |")
        if not entries:
            L.append("| - | (근거 없음: 되묻기·보류 문항) | | | |")
        # 파일을 따로 열지 않고 바로 읽을 수 있게 원본 쪽 텍스트를 펼침 블록으로 넣는다(골든 quote는 <mark>로 표시)
        for bk, pg in dict.fromkeys((e["book_id"], e["page"]) for _, e in entries):
            ptxt = pages_text.get((bk, pg))
            if ptxt:
                for _, e in entries:
                    if (e["book_id"], e["page"]) == (bk, pg):
                        ptxt = mark(ptxt, e["quote"])
                L += ["", f"<details><summary>📄 원본 {bk} {pg}쪽 텍스트 보기 (골든 quote를 노란 표시) — 파일: [{bk}-p{pg}.md](../source_pages/{bk}-p{pg}.md)</summary>", "",
                      *[("> " + ln if ln.strip() else ">") for ln in ptxt.split("\n")], "", "</details>"]
        L += ["", f"- **골든 답변(reference_answer)**: {q['reference_answer']}", f"- 필수 사실(required_facts): {q['required_facts']}"]
        if q.get("forbidden_claims"):
            L.append(f"- 금지 주장(forbidden_claims): {q['forbidden_claims']}")
        L += ["", "## 2. 골든 → 청크 매핑 (같은 청킹에서 quote가 든 청크, 그리고 이 질문의 검색 결과에서의 위치)", "",
              "| 그룹 | book_id · 쪽 | quote가 든 청크 id | 이 질문의 검색 결과 |", "|---|---|---|---|"]
        for gi, e, cand in mapping:
            where = []
            for c in cand:
                r_ = top_all.index(c) + 1 if c in top_all else None
                where.append(f"`{c}`: " + (f"**상위 {a.k} 안 {r_}위**" + ("" if c in used else " (한도로 밀려남)") if r_ and r_ <= a.k else (f"{r_}위 (k={a.k} 밖)" if r_ else "상위 11개에 없음")))
            L.append(f"| {gi} | {e['book_id']} · {e['page']}쪽 | " + (", ".join(f"`{c}`" for c in cand) or "(이 청킹에서 앞 40자를 담은 청크 없음)") + " | " + ("<br>".join(where) or "-") + " |")
        # 한도마다 어떤 청크가 문맥에 들어가고 어떤 청크가 밀려나는지(상위 k개 전부). 한 한도만 보면 다른 한도에서 밀려나는 청크가 안 보인다.
        cum_, cums = 0, {}
        for cid in top:
            cum_ += tok(chunks[cid]["text"])
            cums[cid] = cum_
        L += ["", f"## 3. 문맥 한도별로 밀려나는 청크 (상위 {a.k}개 전부)", "",
              "한도를 넘는 청크와 **그 뒤의 청크는 전부** 문맥에서 빠진다(청크 본문을 중간에서 자르지는 않는다. 예외: 첫 청크 하나가 한도보다 크면 그 청크를 한도에 맞춰 잘라 넣는다).", "",
              "| 순위 | 청크 id | 토큰 | 누적 토큰 | " + " | ".join(f"한도 {lim}" for lim in ctxs) + " | 골든 |", "|" + "---|" * (5 + len(ctxs))]
        for i, cid in enumerate(top, 1):
            marks_ = " | ".join("✅" if cid in used_by[lim] else "❌" for lim in ctxs)
            L.append(f"| {i} | `{cid}` | {tok(chunks[cid]['text'])} | {cums[cid]} | {marks_} | {'★' if is_gold(cid) else ''} |")
        for lim in ctxs:
            drop_l = [c for c in top if c not in used_by[lim]]
            cut_ = tok(chunks[top[0]]["text"]) > lim
            L.append("")
            L.append(f"- **한도 {lim}**: " + (f"청크 {len(drop_l)}개 밀려남 → " + ", ".join(f"{top.index(c) + 1}위 `{c}`" + ("(★ 골든 근거)" if is_gold(c) else "") for c in drop_l) if drop_l else "밀려난 청크 없음")
                     + (f" · ✂ **1위 청크({tok(chunks[top[0]]['text'])}토큰)가 한도보다 커서 본문이 잘려 들어간다**" if cut_ else ""))
        L += ["", f"## 4. 가져온 청크 {a.k}개 (순위 순, 본문 전문)", ""]
        for i, cid in enumerate(top, 1):
            c = chunks[cid]
            write_page(c["book_id"], c["page"])  # 가져온 청크의 원본 쪽 .md도 만든다(골든이 아니어도)
            ctext = c["text"]
            for b_, p_, qt_ in golds:
                if (b_, p_) == (c["book_id"], c["page"]):
                    ctext = mark(ctext, qt_)  # 이 청크 안의 골든 quote 위치를 표시
            ptxt = pages_text.get((c["book_id"], c["page"]), "")
            drop_lims = [lim for lim in ctxs if cid not in used_by[lim]]
            tag = "✅ 모든 한도에서 사용" if not drop_lims else ("❌ 모든 한도에서 밀려남" if len(drop_lims) == len(ctxs) else f"❌ 한도 {', '.join(map(str, drop_lims))}에서 밀려남")
            match = []
            if c["book_id"] in ref_docs:
                match.append("근거 문서")
            if any(c["book_id"] == b and c["page"] == p for b, p, _ in golds):
                match.append("근거 쪽")
            if is_gold(cid):
                match.append("★ quote 포함")
            L += [f"### {i}위 · `{cid}` · {tag}" + (" · ★ 골든 근거" if is_gold(cid) else ""), "",
                  "| 메타데이터 | 값 |", "|---|---|",
                  f"| chunk_id | `{cid}` |", f"| book_id | {c['book_id']} |", f"| file_name | {c['file_name']} |", f"| page | {c['page']} |",
                  f"| 원본 쪽 파일 | [{c['book_id']}-p{c['page']}.md](../source_pages/{c['book_id']}-p{c['page']}.md) |",
                  "| 원본 쪽 안 위치 | " + (lambda L_: f"{L_[0]}~{L_[1]}번째 글자 (쪽 글 {L_[2]}자)" if L_ else "찾지 못함")(loc(cid)) + " |",
                  f"| 길이 | {len(c['text'])}자 / {tok(c['text'])}토큰 |",
                  f"| 최종 점수 | {score.get(cid, 0):.4f} ({'리랭커' if a.mode == 'hybrid_rerank' else 'RRF' if a.mode == 'hybrid' else '코사인'}) |",
                  f"| E5 순위 / BM25 순위 / RRF 순위 | {rank_of(st_.get('dense', []), cid) or '-'} / {rank_of(st_.get('bm25', []), cid) or '-'} / {rank_of(st_.get('rrf', []), cid) or '-'} |",
                  f"| 골든과 일치 | {', '.join(match) or '없음'} |", "",
                  *[("> " + ln if ln.strip() else ">") for ln in ctext.split("\n")], "",
                  f"<details><summary>📄 이 청크가 있는 원본 {c['book_id']} {c['page']}쪽 보기 (청크 위치를 노란 표시)</summary>", "",
                  *[("> " + ln if ln.strip() else ">") for ln in mark(ptxt, c["text"].rpartition("\n")[2]).split("\n")], "", "</details>", ""]
        L += ["## 5. 놓친 근거 청크 (quote가 든 청크 중 상위 k에 못 든 것)", ""]
        missed = sorted({c for _, _, cand in mapping for c in cand if c not in top})
        if not missed:
            L.append("없음 (quote가 든 청크가 모두 상위 k에 있거나, 이 청킹에 해당 청크가 없다)")
        for cid in missed:
            r_ = top_all.index(cid) + 1 if cid in top_all else None
            L += [f"- `{cid}` ({'k 밖 ' + str(r_) + '위' if r_ else '상위 11개에 없음'}, {len(allc[cid]['text'])}자)", "",
                  *[("  > " + ln if ln.strip() else "  >") for ln in mark(allc[cid]["text"], next((qt_ for b_, p_, qt_ in golds if (b_, p_) == (allc[cid]["book"], allc[cid]["page"]) and quote_in(allc[cid]["text"], qt_)), "")).split("\n")], ""]
        rec_ = A.get(qid)
        L += ["## 6. 최종 LLM 답변", ""]
        if rec_ and rec_.get("answer"):
            an = rec_["answer"]
            exp = STATUS_OF.get(q["expected_action"], q["expected_action"])
            facts = [(f_, all(ns(w) in ns(an["answer"]) for w in f_.split())) for f_ in q["required_facts"]]
            L += [f"- 상태: `{an['status']}` (기대 `{exp}` → {'일치' if an['status'] == exp else '**불일치**'})", f"- LLM 답변: {an['answer']}", f"- 이유: {an['reason']}",
                  f"- 인용 출처: {[rec_['source_map'].get(s) for s in an['source_ids']]}", f"- 골든 답변: {q['reference_answer']}",
                  "- 필수 사실 포함(단어 기준): " + (", ".join(f"{'✓' if ok else '✗'} {f_}" for f_, ok in facts) or "해당 없음"),
                  f"- RAGAS faithfulness: {'-' if G.get(qid) is None else f'{G[qid]:.3f}'}"]
        else:
            L.append("(answers 단계를 아직 돌리지 않았거나 오류)")
        fname = qid.replace("/", "_") + ".md"
        (out / "questions" / fname).write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
        index.append((qid, q["expected_action"], sorted(got_docs), recall, pq, drop_txt, fname, ", ".join(ref_docs), gm))

    I = [f"# 질문별 청크 내보내기: {a.mode} · {a.size}자 · 오버랩 {a.pct}% · k={a.k} · 한도 {ctx}", "",
         f"질문 {len(index)}개. 각 파일에 가져온 청크 {a.k}개(본문·메타데이터), 골든 기대(book_id·page·quote), 골든→청크 매핑, 원본 쪽 텍스트(접힌 블록과 링크)가 있다.", "",
         "**질문 ↔ 골든 매핑**: 질문 id는 `세트/문항`이고, 질문 파일(`<세트>_questions.json`)과 골든 파일(`<세트>.json`)의 같은 id 항목이 짝이다. 아래 표에 두 파일에서의 순번과 질문 글 일치 여부를 적었다. 기계가 읽는 형태는 `question_golden_map.json`.", "",
         "| 문항 | 질문 파일 순번 | 골든 파일 순번 | 질문 글 일치 | 기대 | 골든 근거 문서 | 가져온 문서(사용) | Recall(문서) | 쪽+인용문(그룹) | 한도별 밀려난 청크(상위 k 중) | 파일 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for qid, exp, got, rc, pq, nd, fname, refs, gm_ in index:
        I.append(f"| {qid} | {gm_['q_pos']}/{gm_['q_total']} | {gm_['g_pos']}/{gm_['g_total']} | {'✅' if gm_['same_text'] else '⚠'} | {exp} | {refs or '-'} | {', '.join(got)} | {'-' if rc is None else f'{rc:.2f}'} | {'-' if pq is None else f'{pq:.2f}'} | {nd} | [{fname}](questions/{fname}) |")
    (out / "index.md").write_text("\n".join(I) + "\n", encoding="utf-8", newline="\n")
    (out / "question_golden_map.json").write_text(json.dumps([dict(question_key=r_[0], md_file=f"questions/{r_[6]}", **r_[8]) for r_ in index], ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    P = ["# 원본 쪽 목록 (청크 → 원본 쪽 .md 매핑)", "", "청크 id는 `<book_id>-p<쪽>-c<번호>`라서 청크 id에서 쪽 파일을 바로 알 수 있다: `SB01-p1-c1` → `SB01-p1.md`.", "",
         "| 원본 쪽 파일 | 문서 파일 | 청크 수 | 청크 id |", "|---|---|---|---|"]
    for bk, pg in sorted(written_pages):
        ids_ = by_page.get((bk, pg), [])
        P.append(f"| [{bk}-p{pg}.md]({bk}-p{pg}.md) | {allc[ids_[0]]['file'] if ids_ else bk + '.pdf'} | {len(ids_)} | " + ", ".join(f"`{c}`" for c in ids_) + " |")
    (out / "source_pages" / "index.md").write_text("\n".join(P) + "\n", encoding="utf-8", newline="\n")
    print(f"저장: {out} (질문 {len(index)}개, 원본 쪽 {len(written_pages)}개)")


if __name__ == "__main__":
    main()
