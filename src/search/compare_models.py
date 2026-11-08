"""검색 방식·임베딩 모델·청킹 조건을 같은 질문으로 비교해 표를 만든다 (search 영역, 측정용).

실행 예 (저장소 루트에서):
    uv run python -m src.search.compare_models --out results/search-compare.md
    uv run python -m src.search.compare_models --models intfloat/multilingual-e5-small intfloat/multilingual-e5-base
    uv run python -m src.search.compare_models --doc-context on off --max-chars 300 600 900 1300   # 청킹 A/B
    uv run python -m src.search.compare_models --max-chars 500 900 --overlap 0 100 200            # 겹침 A/B

- 색인은 메모리 Qdrant에 새로 만들고 끝나면 사라진다. 팀 서버나 로컬 저장소는 건드리지 않는다.
- 정답(evidence_groups)은 채점에만 쓴다. 검색 입력에는 넣지 않는다.
- 채점은 문서(book_id) 단위다. 같은 문서의 청크가 여럿이어도 한 번만 센다.
    Hit@k    = 기대 문서를 하나라도 찾으면 1
    Recall@k = 찾은 기대 문서 수 / 전체 기대 문서 수
- 참고 문서가 비어 있는 질문은 해당 없음으로 빼고 센다.
- --doc-context, --max-chars, --overlap은 값을 여러 개 받는다. 조합마다 색인을 새로 만들어 한 표에 모은다.
"""

import argparse
import itertools
import json
import statistics
import time
from pathlib import Path

from src import config
from src.search import chunking, embed, index, keyword, rerank, retrieve, store

MODES = ["naive", "hybrid", "hybrid_rerank"]
NL = "\n"


def _reset(model_name: str) -> None:
    """모델이나 청킹 조건이 바뀔 때 이전 색인·모델 캐시를 비운다."""
    config.QDRANT_URL = None
    config.QDRANT_PATH = None  # 메모리 Qdrant
    config.EMBEDDING_MODEL = model_name
    embed._model = None
    store.reset_client()
    keyword.reset()


def _apply_variant(spec: str) -> None:
    """청킹 실험용 스위치를 기본값으로 되돌린 뒤 spec대로 바꾼다.

    spec은 쉼표로 이은 "키=값"이다. 예: "base"(기본), "join=space", "doc=title,split=greedy".
      join  = remove | space                (줄 꺾임을 지움 / 공백으로)
      doc   = title_dept | title | dept     (첫 줄 내용)
      split = balanced | greedy             (긴 쪽 분할: 균등 / 앞에서 채우기)
      para  = off | pack | one              (문단 단위: 안 씀 / 문단 경계에서 균등하게 묶음 / 문단 하나 = 청크 하나)
    """
    chunking.JOIN_WITH = ""
    chunking.DOC_CONTEXT_FORMAT = "title_dept"
    chunking.SPLIT_MODE = "balanced"
    chunking.PARAGRAPH_MODE = "off"
    for part in (p for p in spec.split(",") if p and p != "base"):
        key, val = part.split("=")
        if key == "join":
            chunking.JOIN_WITH = {"remove": "", "space": " "}[val]
        elif key == "doc":
            chunking.DOC_CONTEXT_FORMAT = val
        elif key == "split":
            chunking.SPLIT_MODE = val
        elif key == "para":
            chunking.PARAGRAPH_MODE = val
        else:
            raise ValueError(f"알 수 없는 변형 키: {key}")


def _load_eval(data: Path, questions_file: str, answers_file: str):
    questions = json.loads((data / "evaluation" / questions_file).read_text(encoding="utf-8"))
    answers = {
        a["id"]: a
        for a in json.loads((data / "evaluation" / answers_file).read_text(encoding="utf-8"))
    }
    return questions, answers


def _expected_books(answer: dict) -> set[str]:
    return {e["book_id"] for group in answer.get("evidence_groups", []) for e in group}


def _measure(scored, mode: str, k: int) -> str:
    """한 방식으로 질문 전체를 돌려 표의 한 줄(Hit부터 못 찾은 문항까지)을 만든다."""
    retrieve.retrieve(scored[0][0]["question"], mode, k)  # 모델 로딩을 시간에서 뺀다
    hits, recalls, diversity, latencies, misses = [], [], [], [], []
    for q, ref in scored:
        t = time.perf_counter()
        got = retrieve.retrieve(q["question"], mode, k)
        latencies.append((time.perf_counter() - t) * 1000)
        found = {c.metadata.book_id for c in got}
        hits.append(bool(found & ref))
        recalls.append(len(found & ref) / len(ref))
        diversity.append(len(found))
        if not found & ref:
            misses.append(q["id"])
    return (
        f"{sum(hits) / len(hits):.3f} ({sum(hits)}/{len(hits)}) "
        f"| {statistics.mean(recalls):.3f} | {statistics.mean(diversity):.2f} "
        f"| {statistics.mean(latencies):.0f} | {', '.join(misses) or '-'}"
    )


def run(args) -> str:
    data = Path(args.data)
    questions, answers = _load_eval(data, args.questions_file, args.answers_file)
    rerank.RERANK_CANDIDATES = args.rerank_candidates
    retrieve.POOL = args.pool  # hybrid가 E5·BM25에서 각각 몇 개까지 후보로 보는지
    original_extract = chunking.extract_pages
    original_max = chunking.MAX_CHUNK_CHARS
    original_overlap = chunking.CHUNK_OVERLAP_CHARS
    original_switches = (
        chunking.JOIN_WITH, chunking.DOC_CONTEXT_FORMAT, chunking.SPLIT_MODE, chunking.PARAGRAPH_MODE
    )

    scored = [(q, _expected_books(answers[q["id"]])) for q in questions]
    scored = [(q, ref) for q, ref in scored if ref]
    skipped = len(questions) - len(scored)

    head = (
        f"| 변형 | 제목·부서 첫 줄 | 청크 최대 글자 | 겹침 글자 | 청크 수 | 색인(초) | 방식 | Hit@{args.k} "
        f"| Recall@{args.k} | 상위 {args.k}개의 서로 다른 문서 수(평균) | 질문당 시간(ms) | 못 찾은 문항 |{NL}"
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    conditions_grid = list(
        itertools.product(args.variant, args.doc_context, args.max_chars, args.overlap)
    )
    sections: list[str] = []
    report: dict = {}
    try:
        for model_name in args.models:
            rows = []
            for variant, ctx, max_chars, overlap in conditions_grid:
                _apply_variant(variant)
                chunking.MAX_CHUNK_CHARS = max_chars
                chunking.CHUNK_OVERLAP_CHARS = overlap
                chunking.extract_pages = lambda p, _ctx=ctx, **kw: original_extract(
                    p, include_doc_context=(_ctx == "on")
                )
                _reset(model_name)
                t0 = time.perf_counter()
                report = index.build_index(data / "documents")
                index_sec = time.perf_counter() - t0
                for mode in args.modes:
                    row = (
                        f"| {variant} | {ctx} | {max_chars} | {overlap} | {report['chunks']} | {index_sec:.0f} "
                        f"| {mode} | {_measure(scored, mode, args.k)} |"
                    )
                    rows.append(row)
                    print(row, flush=True)  # 오래 걸리는 실행이라 한 줄씩 바로 보여 준다
            sections.append(f"### {model_name}{NL}{NL}{head}{NL}" + NL.join(rows))
    finally:
        chunking.extract_pages = original_extract
        chunking.MAX_CHUNK_CHARS = original_max
        chunking.CHUNK_OVERLAP_CHARS = original_overlap
        (
            chunking.JOIN_WITH, chunking.DOC_CONTEXT_FORMAT, chunking.SPLIT_MODE, chunking.PARAGRAPH_MODE
        ) = original_switches

    conditions = (
        f"- 데이터: `{args.data}` (문서 {report.get('documents')}개, {report.get('pages')}쪽){NL}"
        f"- 질문: `{args.questions_file}` {len(scored)}개 평가, 해당 없음 {skipped}개 제외{NL}"
        f"- 검색: k={args.k}, hybrid 후보 각 {retrieve.POOL}개(RRF K={retrieve.RRF_K}), "
        f"리랭커 `{rerank.RERANKER_MODEL}` 후보 {args.rerank_candidates}개{NL}"
        f"- 채점: 문서(book_id) 단위. 정답 근거는 채점에만 사용{NL}"
        f"- 속도는 이 PC의 CPU 기준이며 첫 호출(모델 로딩)은 뺐다{NL}"
    )
    return (
        f"# 검색 비교 결과 (잠정){NL}{NL}## 측정 조건{NL}{NL}" + conditions
        + f"{NL}## 결과{NL}{NL}" + (NL + NL).join(sections)
        + f"{NL}{NL}질문 수가 적어 작은 차이는 우연일 수 있다. 청킹이 바뀌면 다시 잰다.{NL}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", default=str(config.DATA_DIR), help="문서와 evaluation/이 든 폴더")
    ap.add_argument("--models", nargs="+", default=[config.EMBEDDING_MODEL])
    ap.add_argument("--modes", nargs="+", default=MODES, choices=MODES)
    ap.add_argument("--k", type=int, default=config.K)
    ap.add_argument("--questions-file", default="development_questions.json")
    ap.add_argument("--answers-file", default="development.json")
    ap.add_argument(
        "--doc-context", nargs="+", choices=["on", "off"], default=["on"],
        help="청크 첫 줄에 제목·부서 (여러 개 가능)",
    )
    ap.add_argument(
        "--max-chars", nargs="+", type=int, default=[chunking.MAX_CHUNK_CHARS],
        help="한 청크 최대 글자 수 (여러 개 가능)",
    )
    ap.add_argument(
        "--overlap", nargs="+", type=int, default=[chunking.CHUNK_OVERLAP_CHARS],
        help="쪽을 나눌 때 앞 조각 끝 문장을 다음 조각에 겹쳐 붙일 최대 글자 수 (여러 개 가능)",
    )
    ap.add_argument(
        "--variant", nargs="+", default=["base"],
        help='청킹 변형. 예: base join=space doc=title doc=dept split=greedy (쉼표로 이어 여러 개를 동시에도 가능)',
    )
    ap.add_argument(
        "--pool", type=int, default=retrieve.POOL,
        help="hybrid에서 E5·BM25 각각의 후보 수. k가 이보다 크면 k 이상으로 올려야 한다",
    )
    ap.add_argument("--rerank-candidates", type=int, default=rerank.RERANK_CANDIDATES)
    ap.add_argument("--out", help="결과를 쓸 md 파일. 없으면 화면에만 출력")
    args = ap.parse_args()

    text = run(args)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"{NL}저장: {out}")


if __name__ == "__main__":
    main()
