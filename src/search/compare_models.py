"""검색 방식·임베딩 모델·청킹 조건을 같은 질문으로 비교해 표를 만든다 (search 영역, 측정용).

실행 예 (저장소 루트에서):
    uv run python -m src.search.compare_models --out results/search-compare.md
    uv run python -m src.search.compare_models --models intfloat/multilingual-e5-small intfloat/multilingual-e5-base
    uv run python -m src.search.compare_models --doc-context off --max-chars 100000   # 청킹 A/B

- 색인은 메모리 Qdrant에 새로 만들고 끝나면 사라진다. 팀 서버나 로컬 저장소는 건드리지 않는다.
- 정답(evidence_groups)은 채점에만 쓴다. 검색 입력에는 넣지 않는다.
- 채점은 문서(book_id) 단위다. 같은 문서의 청크가 여럿이어도 한 번만 센다.
    Hit@k    = 기대 문서를 하나라도 찾으면 1
    Recall@k = 찾은 기대 문서 수 / 전체 기대 문서 수
- 참고 문서가 비어 있는 질문은 해당 없음으로 빼고 센다.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from src import config
from src.search import chunking, embed, index, keyword, rerank, retrieve, store

MODES = ["naive", "hybrid", "hybrid_rerank"]


def _reset(model_name: str) -> None:
    """모델이나 청킹 조건이 바뀔 때 이전 색인·모델 캐시를 비운다."""
    config.QDRANT_URL = None
    config.QDRANT_PATH = None  # 메모리 Qdrant
    config.EMBEDDING_MODEL = model_name
    embed._model = None
    store.reset_client()
    keyword.reset()


def _load_eval(data: Path, questions_file: str, answers_file: str):
    questions = json.loads((data / "evaluation" / questions_file).read_text(encoding="utf-8"))
    answers = {
        a["id"]: a
        for a in json.loads((data / "evaluation" / answers_file).read_text(encoding="utf-8"))
    }
    return questions, answers


def _expected_books(answer: dict) -> set[str]:
    return {e["book_id"] for group in answer.get("evidence_groups", []) for e in group}


def run(args) -> str:
    data = Path(args.data)
    questions, answers = _load_eval(data, args.questions_file, args.answers_file)
    config.RERANK_CANDIDATES = args.rerank_candidates
    config.CHUNK_SIZE = args.max_chars
    original_extract = chunking.extract_pages
    chunking.extract_pages = lambda p, **kw: original_extract(
        p, include_doc_context=(args.doc_context == "on")
    )

    scored = [(q, _expected_books(answers[q["id"]])) for q in questions]
    scored = [(q, ref) for q, ref in scored if ref]
    skipped = len(questions) - len(scored)

    sections: list[str] = []
    try:
        for model_name in args.models:
            _reset(model_name)
            t0 = time.perf_counter()
            report = index.build_index(data / "documents")
            index_sec = time.perf_counter() - t0
            rows = []
            for mode in args.modes:
                retrieve.retrieve(scored[0][0]["question"], mode, args.k)  # 모델 로딩을 시간에서 뺀다
                hits, recalls, diversity, latencies, misses = [], [], [], [], []
                for q, ref in scored:
                    t = time.perf_counter()
                    got = retrieve.retrieve(q["question"], mode, args.k)
                    latencies.append((time.perf_counter() - t) * 1000)
                    found = {c.metadata.book_id for c in got}
                    hits.append(bool(found & ref))
                    recalls.append(len(found & ref) / len(ref))
                    diversity.append(len(found))
                    if not found & ref:
                        misses.append(q["id"])
                rows.append(
                    f"| {mode} | {sum(hits) / len(hits):.3f} ({sum(hits)}/{len(hits)}) "
                    f"| {statistics.mean(recalls):.3f} | {statistics.mean(diversity):.2f} "
                    f"| {statistics.mean(latencies):.0f} | {', '.join(misses) or '-'} |"
                )
            sections.append(
                f"### {model_name}\n\n"
                f"청크 {report['chunks']}개, 실패 {len(report['failed'])}개, 색인 {index_sec:.0f}초\n\n"
                f"| 방식 | Hit@{args.k} | Recall@{args.k} | 상위 {args.k}개의 서로 다른 문서 수(평균) "
                f"| 질문당 시간(ms) | 못 찾은 문항 |\n|---|---|---|---|---|---|\n" + "\n".join(rows)
            )
    finally:
        chunking.extract_pages = original_extract

    conditions = (
        f"- 데이터: `{args.data}` (문서 {report['documents']}개, {report['pages']}쪽)\n"
        f"- 질문: `{args.questions_file}` {len(scored)}개 평가, 해당 없음 {skipped}개 제외\n"
        f"- 청킹: 제목·부서 첫 줄 {args.doc_context}, 한 청크 최대 {args.max_chars}자\n"
        f"- 검색: k={args.k}, hybrid 후보 각 {retrieve.POOL}개(RRF K={retrieve.RRF_K}), "
        f"리랭커 `{config.RERANKER_MODEL}` 후보 {args.rerank_candidates}개\n"
        "- 채점: 문서(book_id) 단위. 정답 근거는 채점에만 사용\n"
        "- 속도는 이 PC의 CPU 기준이며 첫 호출(모델 로딩)은 뺐다\n"
    )
    return (
        "# 검색 비교 결과 (잠정)\n\n## 측정 조건\n\n" + conditions
        + "\n## 결과\n\n" + "\n\n".join(sections)
        + "\n\n질문 수가 적어 작은 차이는 우연일 수 있다. 청킹이 바뀌면 다시 잰다.\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", default=str(config.DATA_DIR), help="문서와 evaluation/이 든 폴더")
    ap.add_argument("--models", nargs="+", default=[config.EMBEDDING_MODEL])
    ap.add_argument("--modes", nargs="+", default=MODES, choices=MODES)
    ap.add_argument("--k", type=int, default=config.K)
    ap.add_argument("--questions-file", default="development_questions.json")
    ap.add_argument("--answers-file", default="development.json")
    ap.add_argument("--doc-context", choices=["on", "off"], default="on", help="청크 첫 줄에 제목·부서")
    ap.add_argument("--max-chars", type=int, default=config.CHUNK_SIZE, help="한 청크 최대 글자 수")
    ap.add_argument("--rerank-candidates", type=int, default=config.RERANK_CANDIDATES)
    ap.add_argument("--out", help="결과를 쓸 md 파일. 없으면 화면에만 출력")
    args = ap.parse_args()

    text = run(args)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
