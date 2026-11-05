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
| [docs/work-plan.md](docs/work-plan.md) | 역할 분담안, 일정(M0~M6), Issue 골격, 미팅 안건 |
| [docs/branch-strategy.md](docs/branch-strategy.md) | 브랜치·PR 규칙 |
| [docs/documentation.md](docs/documentation.md) | ADR과 spec 규약 |
| [docs/adr/](docs/adr/) | 설계 결정 (0002 영역 재편, 0003 스택) |
| [docs/specs/](docs/specs/) | 영역별 현재 동작과 인터페이스 |

## 코드 구조

영역 하나당 `src/<영역>/`과 `docs/specs/<영역>.md`가 1:1. 영역을 맡으면 spec의 미정 항목부터 채운다.

| 영역 | 역할 | 담당 |
|---|---|---|
| `ingestion` | PDF 추출 → 청킹 → E5 임베딩 → Qdrant 색인. 출처(`book_id`, `page`) 보존 | 미정 |
| `retrieval` | `naive` / `hybrid` / `hybrid_rerank` 검색. 공통 `k` | 미정 |
| `service` | FastAPI `/health` `/query`, 프롬프트, gpt-6-luna 호출, 출력 JSON 검증, 자료 ID → 출처 매핑, 오류 처리 | 미정 |
| `evaluation` | 질문 선택, 3방식 일괄 실행, 검색·답변 지표, 운영 지표, 보안 4개, 비교표 | 미정 |
| `observability` | Langfuse 트레이스(요청 ID로 전 구간 연결), JSONL 보조 기록 | `service` 담당 겸임 |

요청 흐름: 사용자 → `service` → `retrieval` → `service`(문맥 조립·생성·검증) → 응답. `observability`가 전 구간을 요청 ID로 기록하고, `evaluation`이 `service`를 일괄 호출해 채점한다.

스택: Python, pypdf, LangChain, 로컬 E5, Qdrant, FastAPI, Langfuse, RAGAS. 결정은 [ADR 0003](docs/adr/0003-stack.md).

## 설치·실행

미정. 스택 확정 후 작성한다. 데이터셋은 `data/`에 두고 커밋하지 않는다. 키는 `.env`에만 둔다(`.env.example` 참고).

## Langfuse 확인 방법

미정. 프로젝트·필터·대표 요청 ID를 여기 적는다.

## 최종 선택과 한계

미정. 비교 결과는 `results/comparison.md`.

## 팀원별 기여

미정. 제출 전 작성.
