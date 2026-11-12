<context>
저장소: 한국어 RAG 프로젝트(Python 3.12, uv). 작업 시작 전에 저장소의 AGENTS.md와 docs/experiments/0002-param-sweep.md를 읽고 따른다.
이 작업은 EXP-0002의 일부다. 기준 설정에서 chunk_size, overlap, topK, context_size(문맥 토큰 한도), 리랭커 후보 수를 하나씩 바꿔 측정하는 탐색 실험이다. 구현은 전부 scripts/ 아래 새 파일로 하고 src/는 고치지 않는다(src/config.py 동결, src/contracts.py·다른 영역 src/ 수정 금지).

확인된 사실(코드로 확인함. 의심되면 해당 줄을 열어 다시 확인):
- src의 모든 모듈은 `from src import config`로 config.X를 호출 시점에 읽는다. 그래서 진입점에서 `config.X = 값`으로 덮어쓰는 방식이 먹힌다. 선례: src/search/compare_models.py:54-55가 config.RERANK_CANDIDATES·config.CHUNK_SIZE를 덮어쓴다.
- K: src/platform/query.py:40 `search.retrieve(question, mode, config.K)`. 문맥: query.py:41 `build_context(chunks, token_limit=config.CONTEXT_TOKEN_LIMIT)`(src/answer/context.py:10).
- 리랭커 후보 수: src/search/retrieve.py:91 `config.RERANK_CANDIDATES`(hybrid_rerank에만 영향). `retrieve.POOL`(20)·`RRF_K`는 모듈 상수라 이번 실험에서는 바꾸지 않는다.
- 청킹: src/search/index.py:35가 `size=config.CHUNK_SIZE, overlap=config.CHUNK_OVERLAP`로 호출하고, src/search/chunking.py:163-164는 overlap이 0이 아니면 ValueError를 낸다.
- 로컬 Qdrant 경로는 config.QDRANT_PATH(src/search/store.py:23-27). QDRANT_URL이 설정돼 있으면 공용 서버를 쓴다.
</context>

<interface_contract>
네 작업이 병렬로 진행되므로 아래 이름·시그니처를 정확히 지킨다(다른 작업이 이것에 맞춰 쓴다).

환경 변수(모두 선택. 없으면 src/config.py 값 그대로): EXP_CHUNK_SIZE(글자 수), EXP_CHUNK_OVERLAP(글자 수), EXP_TOPK, EXP_CONTEXT_TOKENS, EXP_RERANK_CANDIDATES, EXP_INDEX_DIR(로컬 Qdrant 폴더), EXP_LABEL(실행 이름).

scripts/exp_config.py
  def apply() -> dict
    위 환경 변수를 읽어 config.CHUNK_SIZE, CHUNK_OVERLAP, K, CONTEXT_TOKEN_LIMIT, RERANK_CANDIDATES, QDRANT_PATH(=EXP_INDEX_DIR)를 덮어쓴다. src의 다른 모듈을 import하기 전에 호출한다. 적용된 값(덮어쓰지 않은 것은 기본값)을 {"chunk_size","chunk_overlap","topk","context_tokens","rerank_candidates","index_dir","label"} dict로 돌려준다.
    config.QDRANT_URL이 None이 아니면 RuntimeError("공용 Qdrant는 쓰지 않는다").
    EXP_INDEX_DIR/index_meta.json이 있으면 그 chunk_size·chunk_overlap이 환경 변수와 다를 때 RuntimeError.
    EXP_CHUNK_OVERLAP>0이면 `src.search.chunking.chunk_pages`를 scripts.exp_chunking.chunk_pages로 교체한다(src 파일은 안 고친다).

scripts/exp_chunking.py
  def chunk_pages(file_name: str, pages: list[tuple[int, str]], *, size: int, overlap: int) -> <src.search.chunking.chunk_pages와 같은 반환형>
    overlap>0을 지원한다. overlap=0이면 원본 chunk_pages와 결과가 완전히 같다.

scripts/exp_index.py   (인자: 없음, 환경 변수로만 설정)
  EXP_INDEX_DIR에 새 로컬 색인을 만들고 EXP_INDEX_DIR/index_meta.json {"chunk_size","chunk_overlap","n_chunks","embedding_model","collection"}과 EXP_INDEX_DIR/ingest-report.json을 쓴다.

실험 지표 CSV 열 이름(소문자, 이 이름 그대로): label, variable, value, mode, question_id, hit, recall, retrieve_ms, n_chunks, context_tokens, dropped_chunks, truncated.
</interface_contract>

<action_safety>
- 지정된 작업 폴더(--cwd) 밖에는 쓰지 않는다. 읽기는 된다.
- 실제 LLM(OpenAI)·Langfuse·공용 Qdrant를 호출하지 않는다. .env 값을 읽거나 출력하지 않는다. 검증은 가짜 데이터·assert·로컬 CPU 검색으로만 한다.
- src.search.index를 QDRANT_URL이 설정된 채로 실행하지 않는다. 색인은 EXP_INDEX_DIR의 새 폴더에만 만든다. data/shipping/qdrant와 data/shipping/ingest-report.json은 읽기만 한다.
- 새 의존성을 추가하지 않는다(uv add 금지). 필요하면 멈추고 보고한다.
- git: 지정된 브랜치에서만 작업한다. 필요한 파일만 `git add <파일>`로 명시해 커밋한다(`git add -A`·`git add .` 금지). push, force, reset --hard, 브랜치 삭제 금지.
- 요청하지 않은 기능·옵션·리팩터링을 넣지 않는다. 한계가 있는 지름길에는 `shortcut: <한계>, <언제 올릴지>` 주석을 단다.
</action_safety>

<default_follow_through_policy>
가장 합리적이고 위험이 낮은 해석으로 끝까지 진행한다. 정확성·안전에 영향을 주는 정보가 없을 때만 멈추고 무엇이 필요한지 보고한다.
</default_follow_through_policy>

<missing_context_gating>
저장소 사실을 추측하지 않는다. 필요한 정보는 코드를 열어 확인하고, 확인하지 못한 것은 확인하지 못했다고 적는다.
</missing_context_gating>

<verification_loop>
끝내기 전에 (1) 새 비자명 로직마다 assert 자가 점검을 파일 하단 `if __name__ == "__main__":`에 하나 남기고 실제로 실행해 통과를 확인한다. (2) 변경 파일이 위 인터페이스의 이름·시그니처와 일치하는지 대조한다. (3) `git status`로 의도하지 않은 파일(.env, data/, results/)이 스테이지되지 않았는지 확인한다. 검사가 실패하면 첫 초안을 보고하지 말고 고친다.
</verification_loop>

<structured_output_contract>
마지막 답은 다음 네 항목만, 짧게:
1. 변경 파일과 커밋 해시
2. 실행한 검증 명령과 결과(통과/실패)
3. 확인하지 못한 것·남은 위험
4. 인터페이스에서 어긋난 점(없으면 "없음")
</structured_output_contract>
