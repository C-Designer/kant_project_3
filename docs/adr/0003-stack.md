# 0003. 강의 권장 구성(pypdf · LangChain · 로컬 E5 · Qdrant · FastAPI · Langfuse)을 스택으로 고정한다

- 상태: 채택
- 날짜: 2026-11-05

## 배경

발제의 공통 환경은 "강의에서 사용한 개발 환경을 이어서 사용"이고, 답변 생성 모델은 `gpt-6-luna`로 지정돼 있다. 제출까지 8일이라 새 도구를 익힐 여유가 없다.

## 결정

| 역할 | 선택 | 비고 |
|---|---|---|
| 언어 | Python (강의 환경) | 가상환경·의존성 관리 방식은 `README`에 |
| PDF 추출 | `pypdf` | 출처는 LangChain `Document.metadata`에 |
| 문서·프롬프트·체인 | LangChain (`Document`, `ChatPromptTemplate`, LCEL/Runnable) | |
| 임베딩 | 로컬 E5 계열 | 정확한 모델명은 `specs/ingestion.md`에서 고정. 세 방식 동일 |
| 벡터스토어 | Qdrant | 로컬 실행. 컬렉션 스키마는 `specs/ingestion.md` |
| 키워드 검색 | 미정 (BM25 계열 또는 Qdrant sparse) | `retrieval` 담당이 `specs/retrieval.md`에서 고정 |
| 리랭커 | 미정 (로컬 cross-encoder 계열) | `retrieval` 담당이 고정 |
| API | FastAPI + Pydantic | `/health`, `/query` |
| 생성 모델 | `gpt-6-luna` | 발제 지정 |
| 트레이싱 | Langfuse | Cloud / 셀프호스트는 `specs/observability.md`에서 고정 |
| 평가 | RAGAS (Faithfulness) + 자체 Judge 스크립트 | 평가 LLM은 `specs/evaluation.md`에서 고정 |

설정값(API 키, Langfuse 키, 호스트)은 환경 변수로만 넣는다. `.env`는 커밋하지 않고 `.env.example`만 둔다.

## 이유와 대안

- 다른 벡터스토어(Chroma, pgvector 등): 발제가 허용하지만 강의에서 쓴 Qdrant가 하이브리드(sparse) 지원까지 있어 바꿀 이유가 없다.
- 외부 임베딩 API: 비용과 호출 한도가 비교 결과에 섞인다. 로컬 E5로 세 방식 조건을 같게 두기 쉽다.
- LangGraph 등 상위 프레임워크: 도구 호출·메모리가 선택 사항이라 과하다.

## 영향

팀원 전원이 같은 로컬 환경(Python 버전, Qdrant 실행 방법)을 맞춰야 한다. 재실행 가능성이 완료 기준이므로 `README`의 설치·실행 절차를 11/12까지 깨끗한 환경에서 검증한다. 관련 spec: `docs/specs/*.md`.
