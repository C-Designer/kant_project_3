# kant_project_3

KANT 3차 프로젝트 (proj_3rd): PDF 기반 RAG 질의응답 서비스와 세 가지 검색 방식 비교.

- 제출 **2026-11-13 (금) 13:00**, 당일 오후 발표
- 분야·난이도: 미정 (11/5 미팅에서 결정)
- 팀: 김창동(리드), 천희재, 윤승환, 오주헌, 김경민

## 문서

| 문서 | 내용 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | 발제 요약: 필수 4과제, 데이터 규칙, API 형식, 상태값, 산출물, 완료 기준 |
| [docs/evaluation.md](docs/evaluation.md) | 채점 규칙: Hit@k·Recall@k, RAGAS, Judge 4항목, 해당 없음 처리, 운영 지표, 보안 비교 |
| [docs/work-plan.md](docs/work-plan.md) | 역할 분담, 일정(M0~M6), 코드 리뷰·상호 공유·발표 준비, Issue 골격, 미팅 안건 |
| [docs/branch-strategy.md](docs/branch-strategy.md) | 브랜치·PR 규칙 |
| [docs/documentation.md](docs/documentation.md) | ADR과 spec 규약 |
| [AGENTS.md](AGENTS.md) | 사람·에이전트 공통 작업 규칙 |
| [docs/adr/](docs/adr/) | 설계 결정 (0002 관심사 분할·뼈대, 0003 스택) |
| [docs/specs/](docs/specs/) | 영역별 현재 동작과 인터페이스 |

## 코드 구조

영역은 레이어가 아니라 관심사로 나눈다 ([ADR 0002](docs/adr/0002-areas-by-concern.md)). 영역 하나당 담당 1명, spec 1개. 영역 간 계약은 `src/contracts.py`, 동결 설정은 `src/config.py`.

| 영역 | 책임 | 코드 | 담당 |
|---|---|---|---|
| `search` | 검색 품질: 청킹·E5 임베딩·Qdrant 색인, `naive` / `hybrid` / `hybrid_rerank` | `src/search/` | 미정 |
| `answer` | 답변 품질: 문맥 조립, 프롬프트·판단, gpt-6-luna 호출, 출력 JSON 검증, 출처 매핑 | `src/answer/` | 미정 |
| `evaluation` | 비교표: 질문 선택, 3방식 일괄 실행, Hit/Recall·RAGAS·Judge, 운영 지표 집계 | `src/evaluation/` | 미정 |
| `platform` | 재현·관측·운영: FastAPI, `config.py`, LLM 래퍼(timeout·측정), Langfuse, README·재실행, 보안 4개, 시연 | `src/platform/`, `src/api/`, `src/evaluation/security.py` | 미정 |

요청 흐름: `/query` → `platform.run_query()` → `search.retrieve()` → `answer.build_context()` → `answer.generate()`(→ `platform.llm.call()`) → 응답. `evaluation`은 같은 `run_query()`를 일괄 호출해 채점한다. 전 구간이 `request_id` 하나로 Langfuse에 남는다.

뼈대(`naive` 1문항 end-to-end + contracts + config)는 리드가 11/6 오전까지 머지한다. 그 뒤 각자 자기 영역을 깊이 판다. 에이전트 작업 규칙은 [AGENTS.md](AGENTS.md).

스택: Python, pypdf, LangChain, 로컬 E5, Qdrant, FastAPI, Langfuse, RAGAS. 결정은 [ADR 0003](docs/adr/0003-stack.md).

## 설치·실행

미정. 스택 확정 후 작성한다. 데이터셋은 `data/`에 두고 커밋하지 않는다. 키는 `.env`에만 둔다(`.env.example` 참고).

## Langfuse 확인 방법

미정. 프로젝트·필터·대표 요청 ID를 여기 적는다.

## 최종 선택과 한계

미정. 비교 결과는 `results/comparison.md`.

## 팀원별 기여

미정. 제출 전 작성.
