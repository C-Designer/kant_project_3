# search 영역 실험 한눈에 보기

search 담당이 지금까지 한 탐색 실험(EXP-0001~0012)의 결론을 질문별로 모았다. 숫자와 조건은 각 EXP 문서에 있고, 여기에는 결론과 근거 문서만 적는다.

> **읽기 전에.** 모든 값은 `metrics`의 RunRecord·`judge`의 EvalRecord 흐름이 아니라 분석 스크립트로 잰 **탐색용 값**이다(`run_id` 없음). 질문 수가 28~60개라 작은 차이는 우연일 수 있고, 원본이 "잠정"이라 한 것은 그대로 잠정이다. 팀 비교표에 쓰는 값이 아니다. 원본 기록은 저장소 밖 로컬 폴더(`search-notes/`)에 있다.

## 질문별 결론

| 질문 | 결론 | 근거 |
|---|---|---|
| 임베딩 모델은? | E5 small 유지. 큰 모델·한국어 추가 학습·다른 계열이 이긴 적이 없고 small이 가장 빠르다 | [0001](0001-embedding-model-size.md) |
| 청크는 어떻게 나누나? | Basic은 쪽 단위·900자·겹침 0·제목+부서 첫 줄·균등 분할 유지. 겹침은 채택 안 함. Intermediate는 표 한 청크, Advanced는 표 분리·본문 1000자(Intermediate 표 처리는 저장소에 미반영) | [0002](0002-chunking.md) |
| hybrid 파라미터는? | 현재값 유지(POOL 20, RRF 60, 무게 1:1, 2-gram, k1 1.5·b 0.75). Advanced에서만 나은 설정은 rerank에서 이득이 사라져 채택 안 함 | [0003](0003-hybrid-parameters.md) |
| 리랭커 후보 수·모델은? | 후보 20, `bge-reranker-v2-m3` 유지. 후보를 늘리거나 모델·입력을 바꿔도 이득이 없었다 | [0004](0004-reranker.md) |
| k를 늘리면? | k=7~8까지는 3000토큰 한도에 들어가고 Recall이 오르지만, k는 팀 확정값(5)이라 바꾸지 않았다. 판단은 보류 | [0005](0005-k-and-token-limit.md) |
| Advanced 번호 규칙·표 붙이기는? | 번호 일치 우선과 같은 쪽 표 붙이기(합계 1000자)는 Advanced 전용 옵션으로 채택 후보. Intermediate에서는 이득이 없거나 손해 | [0006](0006-advanced-id-and-table-rules.md) |
| 검색 품질을 어떻게 재나? | 공식 Recall 외에 "k개 청크로 답할 재료가 충분한가"(충분/부분/불충분) 판정과 후보 안·밖 근거 진단을 진단 방법으로 채택 | [0007](0007-answerability-and-missed-evidence.md) |
| 후보 뒤 선정을 바꾸면? | 규칙 기반·LLM 분해, 점수 최댓값, LLM 관련도 점수, Jev 필터는 모두 기각(이득 없음 또는 비용·지연) | [0008](0008-query-decomposition-and-scoring-attempts.md) |
| 하위 질문별로 rerank하면? | `hybrid_rerank_subq` 채택(#125, #126). k=5에서 기존 hybrid_rerank 대비 충분이 Basic +7(46→53), Advanced +5~7, Intermediate +1~2(노이즈 범위). 후보는 50에서 20으로 줄임(#128) | [0009](0009-subquestion-alternating-selection.md) |
| 추가 질문에서도 유지되나? | 개발용에서 정한 설정이 추가 질문에서도 크게 어긋나지 않았다. 방식 우열은 말할 근거가 없다 | [0010](0010-additional-questions-and-limits.md) |
| 청크를 작게 하고 k를 키우면? | 3000토큰을 채우면 Basic에서 충분 문항이 늘어나는 경향이 있으나(확정값 hybrid 45에 대해 표 범위 44~51, 100토큰/k=30은 오히려 낮음), 효과가 청크 크기보다 "더 많이 넣은 것"에서 왔을 가능성이 크다. 보류 | [0011](0011-chunk-size-and-k-under-token-limit.md) |
| rerank를 병렬로 돌리면 빨라지나? | 아니다(순차 1.40초, 스레드 1.42초, 배치 8이 1.31초). 후보 수를 줄이는 쪽이 효과가 크다 | [0012](0012-subquestion-rerank-parallel.md) |

## 코드에 반영된 것

- 0009 하나뿐이다. `hybrid_rerank_subq`(`src/contracts.py`의 `RetrievalMode`, `src/search/retrieve.py`, `src/search/subq.py`)와 `SUBQ_CANDIDATES` 20(`src/config.py`)이다.
- 나머지 실험은 모두 현행 설정을 유지하거나 보류했다.

## 열려 있는 것

- 청크 크기×k(0011): Intermediate·Advanced 격자, 판정 반복으로 노이즈 크기 재기, 공식 `metrics`·`judge` 흐름으로 확정 후보 확인.
- k 변경(0005, 0011): 팀 확정값이라 `[interface]` PR과 answer 담당 확인이 필요하다.
- Intermediate 표 처리가 저장소 `chunking.py`에 없다(0002, 0010).
- 모든 방식이 놓치는 문항(예: `S-DEV-30`, `S-FINAL-30`)과 사람 대조가 필요한 문항(`IS-DEV-07`, `AS-ADD17`)은 0009·0010에 있다.

## 문서 읽는 순서

1. 이 문서
2. 관심 있는 주제의 EXP 문서. 각 문서는 "결정·후속 작업"에서 결론을, "해석·한계"에서 말할 수 없는 것을, "실패·이상 기록"에서 정정과 오류를 본다.
3. 목록과 상태는 [../README.md](../README.md)
