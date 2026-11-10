"""대표 사례 원문 대조 시트 만들기 (docs/specs/judge.md 12번: 사람 확인).

자동 채점이 끝난 뒤, 사람이 PDF 원문과 대조할 만한 사례를 골라 한 장의 문서로 만든다.
사례마다 질문·답변·채점 결과·서비스가 인용한 쪽의 PDF 원문·정답지 근거 쪽을 한 곳에 모아,
PDF를 일일이 열지 않고도 "자동 채점이 맞았나"를 판단할 수 있게 한다. 판단은 사람이 한다.

고르는 기준 (우선순위 순)
1. 기대 동작과 달라 보이는데 판단 1점 / 기대 동작과 같은데 판단 0점   → 채점이 놓치거나 과하게 깎았을 수 있음
2. Faithfulness가 낮은데(≤0.5) 4칸이 모두 1점                          → 두 채점이 어긋남
3. Faithfulness가 높은데(≥0.8) 사실·조건에 0점                          → 문맥에는 충실하지만 틀림 (옛 안내를 따른 경우 등)
4. 같은 질문에서 검색 방식끼리 결과가 갈림                               → 방식 비교의 대표 사례
5. 해당 없음·평가 불가가 나온 답안                                       → 빈칸 규칙이 의도대로 동작하는지

실행 예
  python -m src.judge.review_sheet --run <run_id>

결과는 data/judge_review/ 아래(git 제외)에 저장한다. 최종 기록은 사람이 results/review.md에 쓴다.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from src.contracts import EvalRecord, GroundTruth, RunRecord
from src.judge.rules import JUDGE_ITEMS
from src.judge.score import DEFAULT_EVAL_DIR, MODES, load_ground_truths, read_jsonl, read_run_folder

ACTION_TO_STATUS = {"answer": "answered", "clarify": "needs_clarification", "abstain": "abstained"}
ITEM_KO = {"facts": "사실", "conditions": "조건", "evidence": "근거", "decision": "판단"}
PDF_SNIPPET_CHARS = 1200

Pairs = dict[tuple[str, str], tuple[RunRecord, EvalRecord]]  # (question_id, mode) → (답안, 채점)


@dataclass
class Candidate:
    label: str
    qid: str
    modes: list[str] = field(default_factory=list)


def build_pairs(runs: list[RunRecord], evals: list[EvalRecord]) -> Pairs:
    by_key = {(e.question_id, e.retrieval_mode): e for e in evals}
    return {(r.question_id, r.retrieval_mode): (r, by_key[(r.question_id, r.retrieval_mode)])
            for r in runs if (r.question_id, r.retrieval_mode) in by_key}


def _score(e: EvalRecord, item: str):
    return e.judge[item].score if e.judge and item in e.judge else None


def select_candidates(pairs: Pairs, truths: dict[str, GroundTruth], max_n: int = 12) -> list[Candidate]:
    picked: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    def add(label: str, qid: str, modes: list[str]) -> None:
        fresh = [m for m in modes if (qid, m) not in seen]
        if fresh:
            picked.append(Candidate(label, qid, fresh))
            seen.update((qid, m) for m in fresh)

    items = sorted(pairs.items())
    # 1. 기대 동작과 판단 점수가 어긋남
    for (qid, mode), (run, ev) in items:
        truth = truths.get(qid)
        if truth is None or run.status == "error":
            continue
        same = run.status == ACTION_TO_STATUS[truth.expected_action]
        d = _score(ev, "decision")
        if not same and d == 1:
            add("기대 동작과 다른데 판단 1점 (채점이 놓쳤나?)", qid, [mode])
        elif same and d == 0:
            add("기대 동작과 같은데 판단 0점 (과하게 깎였나?)", qid, [mode])
    # 2. Faithfulness 낮은데 4칸 모두 1점
    for (qid, mode), (_, ev) in items:
        if ev.faithfulness is not None and ev.faithfulness <= 0.5 and all(_score(ev, i) == 1 for i in JUDGE_ITEMS):
            add("Faithfulness는 낮은데 4칸이 모두 1점 (두 채점이 어긋남)", qid, [mode])
    # 3. Faithfulness 높은데 사실·조건 0점
    for (qid, mode), (_, ev) in items:
        if ev.faithfulness is not None and ev.faithfulness >= 0.8 and (_score(ev, "facts") == 0 or _score(ev, "conditions") == 0):
            add("Faithfulness는 높은데 사실·조건 0점 (문맥에는 충실하나 틀림)", qid, [mode])
    # 4. 같은 질문에서 방식끼리 결과가 갈림
    by_q: dict[str, list[str]] = {}
    for (qid, mode) in pairs:
        by_q.setdefault(qid, []).append(mode)
    for qid, modes in sorted(by_q.items()):
        sigs = {(pairs[(qid, m)][0].status, tuple(_score(pairs[(qid, m)][1], i) for i in JUDGE_ITEMS)) for m in modes}
        if len(modes) >= 2 and len(sigs) > 1:
            # 방식 비교는 모든 방식을 한 사례에 같이 보여 줘야 의미가 있다. 앞에서 방식 하나만 골랐던 사례는 이 사례로 합친다.
            covered = [c for c in picked if c.qid == qid]
            notes = "; ".join(f"`{m}`는 '{c.label}'에도 해당" for c in covered for m in c.modes)
            picked[:] = [c for c in picked if c.qid != qid]
            seen.difference_update((qid, m) for m in modes)
            add("같은 질문에서 검색 방식끼리 결과가 갈림" + (f" ({notes})" if notes else ""),
                qid, sorted(modes, key=lambda m: MODES.index(m) if m in MODES else len(MODES)))
    # 5. 해당 없음·평가 불가 규칙 확인
    for (qid, mode), (_, ev) in items:
        if ev.not_applicable or ev.unscorable:
            add("해당 없음·평가 불가가 나온 답안 (빈칸 규칙 확인)", qid, [mode])
    return picked[:max_n]


# --- PDF 원문 ----------------------------------------------------------------

_readers: dict[Path, PdfReader] = {}


def pdf_page_text(book_id: str, page: int, documents_dir: Path) -> str:
    """PDF의 쪽(1부터) 원문. 줄바꿈 때문에 끊긴 공백은 그대로 둔다(원문 대조용)."""
    path = documents_dir / f"{book_id}.pdf"
    if not path.exists():
        return f"(PDF 없음: {path})"
    reader = _readers.setdefault(path, PdfReader(str(path)))
    if not 1 <= page <= len(reader.pages):
        return f"(쪽 범위 밖: {book_id}.pdf 는 {len(reader.pages)}쪽)"
    text = re.sub(r"\s+", " ", reader.pages[page - 1].extract_text() or "").strip()
    return text[:PDF_SNIPPET_CHARS] + (" …" if len(text) > PDF_SNIPPET_CHARS else "")


# --- 문서 만들기 -----------------------------------------------------------------


def _fmt(v) -> str:
    return "-" if v is None else str(v)


def render_case(n: int, cand: Candidate, pairs: Pairs, truths: dict[str, GroundTruth], documents_dir: Path) -> str:
    truth = truths.get(cand.qid)
    first_run = pairs[(cand.qid, cand.modes[0])][0]
    out = [f"## 사례 {n}. {cand.label}", "", f"- 질문 ID: `{cand.qid}`",
           f"- 질문: {first_run.question}"]
    if truth:
        out += [f"- 기대 동작: `{truth.expected_action}`", f"- 참고 답변: {truth.reference_answer}",
                f"- 필수 사실: {truth.rubric.get('required_facts', [])}", f"- 금지 주장: {truth.rubric.get('forbidden_claims', [])}"]
    for mode in cand.modes:
        run, ev = pairs[(cand.qid, mode)]
        out += ["", f"### 방식: `{mode}`  (서비스 상태 `{run.status}`)", "", f"**서비스 답변**: {run.answer}", "",
                "**서비스가 인용한 곳**: " + (", ".join(f"{c.source_id}={c.book_id} {c.page}쪽" for c in run.citations) or "(인용 없음)"),
                "**모델이 실제로 본 문맥**: " +(", ".join(f"{c.source_id}={c.metadata.book_id} {c.metadata.page}쪽" for c in run.final_context) or "(없음)"),
                "", "| 항목 | 점수 | 이유 |", "|---|---|---|",
                f"| Faithfulness | {_fmt(ev.faithfulness if ev.faithfulness is None else round(ev.faithfulness, 2))} | |"]
        for item in JUDGE_ITEMS:
            j = (ev.judge or {}).get(item)
            out.append(f"| {ITEM_KO[item]} ({item}) | {_fmt(j.score) if j else '-'} | {j.reason if j else '(채점 없음)'} |")
        if ev.not_applicable:
            out.append(f"\n해당 없음: {ev.not_applicable}")
        if ev.unscorable:
            out.append(f"\n평가 불가: {ev.unscorable}")
        cited = list(dict.fromkeys((c.book_id, c.page) for c in run.citations))
        if cited:
            out += ["", "**인용한 쪽의 PDF 원문** (이 쪽이 답변의 주장을 뒷받침하나?)"]
            out += [f"- `{b}.pdf` {p}쪽: {pdf_page_text(b, p, documents_dir)}" for b, p in cited]
    if truth:
        groups = truth.rubric.get("evidence_groups", [])
        refs = list(dict.fromkeys((e["book_id"], e["page"]) for g in groups for e in g))
        if refs:
            out += ["", "**정답지가 가리키는 근거 쪽** (참고)"]
            for b, p in refs[:6]:
                quote = next((e["quote"].strip() for g in groups for e in g if e["book_id"] == b and e["page"] == p), "")
                out.append(f"- `{b}.pdf` {p}쪽: {quote[:300]}")
    out += ["", "**사람 판정** (직접 채운다)", "",
            "- 원문 확인 결과:", "- 자동 채점이 맞나:  [ ] 맞음   [ ] 틀림", "- 틀렸다면: 원래 점수 → 수정 점수 / 수정 이유:",
            "- 발표 ④⑥ 사례로 쓸까:  [ ] 예   [ ] 아니오", "", "---", ""]
    return "\n".join(out)


def build_sheet(pairs: Pairs, truths: dict[str, GroundTruth], documents_dir: Path, max_n: int = 12, title: str = "") -> str:
    cands = select_candidates(pairs, truths, max_n)
    head = [f"# 대표 사례 원문 대조 시트 {title}".rstrip(), "",
            f"- 채점 결과 {len(pairs)}건 중 사람이 볼 만한 사례 {len(cands)}건을 골랐다 (기준: 파일 맨 위 설명 참고).",
            "- 이 시트는 후보일 뿐이다. 자동 채점이 맞는지는 **PDF 원문을 보고 사람이 판정**한다.",
            "- 자동 채점 오류를 찾으면 원래 점수와 수정 이유를 함께 남기고, 최종 기록은 `results/review.md`에 쓴다.", "", "---", ""]
    if not cands:
        head.append("(고를 만한 사례가 없다. 채점 결과가 비어 있거나 모두 일치한다.)")
    return "\n".join(head + [render_case(i, c, pairs, truths, documents_dir) for i, c in enumerate(cands, 1)])


def main() -> None:
    p = argparse.ArgumentParser(description="대표 사례 원문 대조 시트 만들기")
    p.add_argument("--run", required=True, help="metrics 러너의 run_id (results/runs/<run_id>/ 의 세 방식 파일과 eval.jsonl)")
    p.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR)
    p.add_argument("--documents", type=Path, default=Path("data/shipping/documents"))
    p.add_argument("--max", type=int, default=12)
    p.add_argument("--out", type=Path)
    a = p.parse_args()

    folder = Path("results/runs") / a.run
    runs = read_run_folder(folder)
    evals = read_jsonl(folder / "eval.jsonl", EvalRecord)
    out = a.out or Path("data/judge_review") / f"{a.run}.md"
    sheet = build_sheet(build_pairs(runs, evals), load_ground_truths(a.eval_dir), a.documents, a.max, f"({a.run})")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet, encoding="utf-8", newline="\n")
    print(f"시트 저장: {out}  ({sheet.count('## 사례')}건)")


if __name__ == "__main__":
    main()
