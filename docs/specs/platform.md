# platform spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 김창동(리드). 짝: `metrics`(`run_query()` 호출). 뼈대(contracts, config, naive E2E)도 여기서 만든다.

## 범위

- 책임: 재현·관측·운영. FastAPI 라우터와 요청·오류 응답, 요청 ID, `config.py`(동결 대상 설정의 단일 출처), LLM 호출 래퍼(timeout·재시도·토큰·시간 측정), Langfuse 트레이스, JSONL 보조 기록, `.env.example`, README 설치·실행 절, 교차 재실행 검증, 보안 비교 4개 실행, 발표 시연(FastAPI docs + Langfuse) 준비와 녹화 백업.
- 책임 아님: 검색(`search`), 프롬프트와 판단(`answer`), 실행·집계(`metrics`), 채점(`judge`).

## 동작

API
- `GET /health` → `{"status": "ok"}`.
- `POST /query`: 빈 질문·지원하지 않는 `retrieval_mode` → 422. `request_id` 생성 → `run_query()` → 응답. `answer`가 `ValidationFailed`를 올리거나 timeout·재시도 소진이면 `status: error`, `reason` 코드(`model_timeout`, `output_validation`, …), `citations: []`. HTTP 상태는 200/5xx 중 하나로 고정(미정).

설정(`src/config.py`)
- 동결 대상을 한 곳에: `k`, `context_token_limit`, 생성 모델·temperature, timeout, 재시도 횟수, 임베딩 모델, 컬렉션 이름, 하이브리드·리랭커 설정, 평가 모델. 확정값: `k = 5`(2026-11-05 킥오프, 세 방식 공통). 나머지 값 미정. 11/10 동결 후 변경은 `[interface]` PR.

LLM 래퍼(`platform.llm.call(messages, *, kind="service"|"eval")`)
- timeout·재시도 적용, 입력·출력 토큰과 시간 측정, Langfuse generation 기록. 측정 못 한 값은 `None`. 재시도 사용량도 합산.
- `kind="eval"`은 별도 트레이스로 서비스 지표에 섞지 않는다.

트레이스(`platform.tracing`)
- Langfuse는 **Cloud**(`https://cloud.langfuse.com`, 2026-11-05 확정). 팀 프로젝트 하나를 리드가 만들고 초대. 키는 각자 `.env`.
- 트레이스 `query`에 `request_id`. 스팬 `retrieve` → `build_context` → `generate` → `validate`. `retrieve` 결과와 `build_context` 결과를 둘 다 남겨 "못 찾음"과 "찾았지만 잘림"을 구분할 수 있게.
- `record_score(request_id, name, value, comment)`로 평가 점수를 트레이스에 붙인다.
- 비밀값·API 키는 트레이스에 넣지 않는다.

보안 비교(`src/platform/security.py`)
- 최종 구성 하나, 보안 질문 2개. 한 번 검색한 `final_context`를 저장 → `answer.generate(defense=False)` → 같은 문맥으로 `generate(defense=True)`. 결과 4개를 `results/security.md`에 공격 노출·추종·업무 정확성·과잉 거절로 나눠 기록.

재현
- `README` 설치·실행 절, `.env.example`, Qdrant 실행 방법. 11/12 구현 안 한 팀원이 README대로 설치·실행. 안 되면 README를 고친다.
- 시연 경로(API 호출 → Langfuse 대표 요청) 11/12 녹화.

미정: HTTP 상태 정책, Qdrant 실행 방법(docker / embedded). (Langfuse Cloud·k=5·Python 3.12/uv는 확정.)

코드 위치: `src/platform/` (`llm.py`, `tracing.py`, `jsonl.py`, `security.py`), `src/api/` (`main.py`, `schemas.py`), `src/config.py`, `src/contracts.py`

## 인터페이스

```python
class QueryRequest(BaseModel):
    question: str                 # 비어 있으면 422
    retrieval_mode: RetrievalMode

class QueryResponse(BaseModel):
    request_id: str
    status: Literal["answered", "needs_clarification", "abstained", "error"]
    answer: str
    reason: str
    citations: list[Citation]

def run_query(question: str, mode: RetrievalMode, *, request_id: str | None = None) -> RunRecord
```

- `run_query`는 API와 `metrics` 러너가 공유하는 단일 경로다. 검색 → 문맥 → 생성 → 검증 → 측정 → 트레이스를 여기서 묶는다.
- `llm.call`, `tracing.span`, `record_score`는 다른 영역이 쓰는 유일한 측정·기록 진입점이다.

## 관련 ADR

- 0001, 0002, 0003
