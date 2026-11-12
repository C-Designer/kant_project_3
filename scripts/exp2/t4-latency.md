<task>
[T4 LLM 없는 순차 검색 지표 하니스] 브랜치 exp/exp2-latency.
scripts/exp_retrieval_bench.py를 만든다. LLM·Langfuse 없이 로컬 검색만 **순차로** 돌려 아래를 질문 × 방식 단위로 CSV에 남긴다(열 이름은 interface_contract 그대로: label, variable, value, mode, question_id, hit, recall, retrieve_ms, n_chunks, context_tokens, dropped_chunks, truncated).
- 질문: scripts/lf_experiment.py가 쓰는 공식 15문항과 같은 선택을 쓴다(`src.metrics.questions.select_questions`를 같은 인자로 호출: DEFAULT_QUOTA, DEFAULT_SEED, DEFAULT_MIN_PER_SOURCE, DEFAULT_MIN_DOCS. lf_experiment.py의 `pick` 부분을 읽고 같게). 정답은 hit/recall 계산에만 쓰고 검색 입력에는 질문 문장만 넣는다.
- 인자: `--modes naive,hybrid,hybrid_rerank`(기본), `--repeats 3`(기본), `--variable <이름> --value <값>`(CSV의 variable·value 열에 그대로 적는 라벨), `--out <csv>`.
- 시작할 때 `scripts.exp_config.apply()`를 src import보다 먼저 호출한다(T1이 만든다. 이 브랜치에 없으면 try/except ImportError로 경고를 stderr에 내고 기본 config로 돌려 보되, exp_config.py를 직접 만들지 않는다).
- 측정: 방식마다 워밍업 호출 1회(모델 로딩 시간 제외) 후, 질문마다 `repeats`번 `src.search.retrieve.retrieve(question, mode, config.K)`를 `time.perf_counter()`로 재서 retrieve_ms를 낸다. CSV는 반복마다 한 행이 아니라 질문당 반복의 **중앙값**을 retrieve_ms로, 반복 간 최대−최소를 `retrieve_ms_range`(열 추가 허용)로 적는다.
- hit·recall: `src.metrics.retrieval_metrics.hit_recall(evidence_book_ids, retrieved_book_ids, config.K)`. 근거 목록이 비어 hit·recall이 None인 질문은 빈 칸(0 아님).
- 문맥 지표: 검색 결과로 `src.answer.context.build_context(chunks, token_limit=config.CONTEXT_TOKEN_LIMIT)`를 호출해 context_tokens(문맥 토큰 합, 같은 모듈의 토큰 세는 함수 사용), dropped_chunks(한도 때문에 버려진 청크 수), truncated(버려졌거나 첫 청크가 잘렸으면 1, 아니면 0)를 낸다. build_context의 코드(src/answer/context.py)를 읽고 잘림 판정을 코드와 같게 한다. build_context는 트레이스 스팬을 열 수 있으니 Langfuse 키가 없을 때 no-op인지 확인하고 보고한다.
</task>

<completeness_contract>
점검: 인자 파싱, 중앙값·범위 계산, hit/recall의 None 처리, truncated 판정을 가짜 입력으로 assert. 실제 색인이 있으면(data/shipping/qdrant, 읽기 전용) `QDRANT_URL`을 비운 채 질문 3개 × naive 1방식으로 한 번 돌려 CSV 모양을 보고한다. 로컬 Qdrant는 한 프로세스만 열 수 있으니 이미 열린 경우(잠금 오류)는 그대로 보고하고 다른 폴더를 만들거나 잠금 파일을 지우지 않는다.
</completeness_contract>
