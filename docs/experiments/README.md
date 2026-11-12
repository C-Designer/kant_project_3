# 실험 기록

RAG 검색·생성·채점 실험을 실험당 한 파일로 쌓는다. 절차와 칸은 [exp_template.md](exp_template.md), 채점 규칙은 [../evaluation.md](../evaluation.md).

## 쓰는 법

1. `exp_template.md`를 `NNNN-<제목>.md`로 복사한다. 번호는 마지막 실험 + 1, 파일명은 영문 소문자·하이픈.
2. **결과를 보기 전에** 가설과 성공 기준, 바꾼 변수 하나를 적는다.
3. 실행한 뒤 `run_id`와 결과 표, 실패·이상까지 그대로 옮긴다.
4. 아래 표에 한 줄 추가한다. `완료` 뒤의 본문은 고치지 않는다. 결과가 뒤집히면 새 실험을 쓰고 `관련`에 잇는다.
5. 채택해서 동작이 바뀌면 같은 PR에서 spec·`src/config.py`를 고친다([../documentation.md](../documentation.md)).

## 목록

| 번호 | 제목 | 상태 | 결정 | run_id |
|---|---|---|---|---|
| [0001](search/0001-embedding-model-size.md) | 임베딩 모델 크기·후보 비교 | 완료 | 기각 (E5 small 유지) | 없음 (탐색용) |
| [0002](search/0002-chunking.md) | 청킹 규칙 비교 (크기·겹침·첫 줄·분할·표 분리) | 완료 | 현행 유지 (잠정) | 없음 (탐색용) |
| [0003](search/0003-hybrid-parameters.md) | hybrid 파라미터 비교 (POOL·RRF·무게·BM25) | 완료 | 현행 유지 (잠정) | 없음 (탐색용) |
| [0004](search/0004-reranker.md) | 리랭커 후보 수·모델·입력 비교 | 완료 | 기각 (후보 20, bge-reranker-v2-m3 유지) | 없음 (탐색용) |
| [0005](search/0005-k-and-token-limit.md) | k 늘리기와 3000토큰 한도 | 완료 | 보류 | 없음 (탐색용) |
| [0006](search/0006-advanced-id-and-table-rules.md) | Advanced 번호 우선·표 붙이기 규칙 | 완료 | 채택 (Advanced 전용 옵션) | 없음 (탐색용) |
| [0007](search/0007-answerability-and-missed-evidence.md) | 답할 재료 충분 판정과 놓친 근거 진단 | 완료 | 채택 (진단 방법) | 없음 (탐색용) |
| [0008](search/0008-query-decomposition-and-scoring-attempts.md) | 질문 분해·LLM 점수·Jev 선정 시도 | 완료 | 기각 | 없음 (탐색용) |
| [0009](search/0009-subquestion-alternating-selection.md) | 하위 질문별 rerank 번갈아 채우기 (`hybrid_rerank_subq`) | 완료 | 채택 (#125, #126, 후보 20 #128) | 없음 (탐색용) |
| [0010](search/0010-additional-questions-and-limits.md) | 추가 질문 검증과 한계 | 완료 | 보류 | 없음 (탐색용) |
| [0011](search/0011-chunk-size-and-k-under-token-limit.md) | 3000토큰 안에서 청크 크기·k 격자 | 완료 | 보류 | 없음 (탐색용) |
| [0012](search/0012-subquestion-rerank-parallel.md) | 하위 질문별 rerank 병렬·배치 | 완료 | 기각 | 없음 (탐색용) |
| [0014](search/0014-chunk-overlap-k-grid-with-answers.md) | 청크 크기×오버랩×k 격자와 답변 행동·RAGAS·토큰·latency | 완료 | 보류 | 없음 (탐색용) |
| [0015](search/0015-latency-breakdown-by-size-k-and-tokens.md) | 검색 시간(크기·k·내부 단계)과 답변 LLM 시간 요인(토큰·문항 유형) 분해 | 완료 | 보류 | 없음 (탐색용) |
| [0016](search/0016-grid-k-4-11.md) | [k 담당 1/4] k = 4·11: 크기·오버랩 격자의 검색 지표·답변 행동·토큰·전체 시간·RAGAS | 계획 | - | 없음 (예정) |
| [0017](search/0017-grid-k-5-10.md) | [k 담당 2/4] k = 5·10: 크기·오버랩 격자의 검색 지표·답변 행동·토큰·전체 시간·RAGAS | 계획 | - | 없음 (예정) |
| [0018](search/0018-grid-k-6-9.md) | [k 담당 3/4] k = 6·9: 크기·오버랩 격자의 검색 지표·답변 행동·토큰·전체 시간·RAGAS | 계획 | - | 없음 (예정) |
| [0019](search/0019-grid-k-7-8.md) | [k 담당 4/4] k = 7·8: 크기·오버랩 격자의 검색 지표·답변 행동·토큰·전체 시간·RAGAS | 계획 | - | 없음 (예정) |

search 영역 실험의 결론 요약은 [search/README.md](search/README.md)에 있다.

search 영역 실험(0001~0012, 0014~0019)은 `main`에 있는 `RunRecord`·`EvalRecord` 흐름이 아니라 분석 스크립트로 잰 탐색용 값을 사후에 정리한 것이다(사전 성공 기준 없음). 팀 비교표에 쓰는 값이 아니다.
