# platform spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 김창동(리드). 짝: `metrics`(`run_query()` 호출). 뼈대(contracts, config, naive E2E)도 여기서 만든다.

## 범위

- 책임: 재현·관측·운영. FastAPI 라우터와 요청·오류 응답, 요청 ID, `config.py`(동결 대상 설정의 단일 출처), LLM 호출 래퍼(timeout·재시도·토큰·시간 측정), Langfuse 트레이스, JSONL 보조 기록, `.env.example`, README 설치·실행 절, 교차 재실행 검증, 보안 비교 4개 실행, 발표 시연(FastAPI docs + Langfuse) 준비와 녹화 백업.
- 책임 아님: 검색(`search`), 프롬프트와 판단(`answer`), 실행·집계(`metrics`), 채점(`judge`).

## 동작

API
- `GET /health` → `{"status": "ok"}`.
- `POST /query`: 빈 질문·지원하지 않는 `retrieval_mode` → 422. `request_id` 생성 → `run_query()` → 응답. `answer`가 `ValidationFailed`를 올리거나 timeout·재시도 소진이면 `status: error`, `reason` 코드(`model_timeout`, `output_validation`, …), `citations: []`. HTTP 상태는 요청 형식 오류만 422이고, 처리된 요청은 `status: error`여도 200이다(2026-11-08 확정, #38). 실패 여부는 `status`·`reason`으로 본다. reason 코드: `model_timeout`, `model_error`, `output_validation`, `index_missing`, `mode_not_implemented`, `internal_error`. 내부 오류의 원문 메시지는 응답에 싣지 않는다.

설정(`src/config.py`)
- 동결 대상을 한 곳에: `k`, `context_token_limit`, 생성 모델·temperature, timeout, 재시도 횟수, 임베딩 모델, 컬렉션 이름, 하이브리드·리랭커 설정, 평가 모델. 확정값(2026-11-05 킥오프): `k = 5`(세 방식 공통), 평가 모델 = `gpt-6-luna`(생성 모델과 같음, `kind="eval"`로 별도 호출). temperature는 지정하지 않는다(`None`, 2026-11-08): `gpt-6-luna`가 기본값 1 외의 값을 거부한다. 담당 영역이 확정한 값: 청크 900·overlap 0, hybrid RRF, 리랭커 `BAAI/bge-reranker-v2-m3`·후보 20(search, #86), `context_token_limit` 3000(answer, #18), LLM timeout 30초·재시도 2회(platform, 2026-11-09). 리드 확정(2026-11-10 동결, #41): 임베딩 `intfloat/multilingual-e5-small`·컬렉션 `shipping_basic`(#14), 재생성 1회(#20). 동결 후 변경은 `[interface]` PR + 전체 재실행.

LLM 래퍼(`platform.llm.call(messages, *, kind="service"|"eval")`)
- timeout·재시도 적용, 입력·출력 토큰과 시간 측정, Langfuse generation 기록. 측정 못 한 값은 `None`. 재시도 사용량도 합산.
- `kind="eval"`은 별도 트레이스로 서비스 지표에 섞지 않는다.

트레이스(`platform.tracing`)
- Langfuse·Qdrant는 리드의 **Mac Studio에서 Docker Compose로 셀프호스트**한다(2026-11-09 현황 확인). 공용 서비스는 이 둘뿐이고 Cloudflare Tunnel로 HTTPS 주소를 제공한다. FastAPI는 각자 로컬에서 띄운다(2026-11-09 공용 API 운영 중단, 발제상 클라우드 배포는 범위 밖). Langfuse 화면은 Google 로그인(2026-11-09부터 Cloudflare를 거치지 않는 직접 연동)으로, 리드가 Google 테스트 사용자와 Langfuse 조직 멤버로 함께 등록한 계정만 들어간다. 새 팀원은 리드에게 두 가지 등록을 요청한다. Qdrant는 API 키 인증을 사용한다. 주소는 README, 키는 각자 `.env`에만 둔다. 다른 PC는 `config.QDRANT_API_KEY`로 공용 Qdrant에 접속하고(`search.store.get_client()`가 전달).
- 트레이스 `query`에 `request_id`, `user_id`, 태그 `api`/`eval`. `user_id`는 누가 썼는지를 Langfuse Users 화면에서 보려는 값이다. API 요청은 Cloudflare Access가 붙이는 `Cf-Access-Authenticated-User-Email` 헤더의 `@` 앞부분이고, 헤더가 없으면(공용 API를 내린 2026-11-09 이후의 로컬 API 요청) `TRACE_USER`로 채운다. 그 외 `run_query` 호출과 `kind="eval"` 평가 호출은 각자 `.env`의 `TRACE_USER`(없으면 user_id 없음)를 쓴다. 표시용이지 인증이 아니다(터널을 거치지 않고 서버에 직접 붙으면 헤더를 꾸밀 수 있다). 태그는 API 요청이 `api`, 나머지가 `eval`이다. 스팬 `retrieve` → `build_context` → `generate` → `validate`. `retrieve` 출력에는 검색 청크의 본문·점수·메타데이터를, `build_context` 출력에는 최종 문맥을 남겨 "못 찾음"과 "찾았지만 잘림"을 구분한다.
- 트레이스 id는 `trace_id_for(request_id)`로 `request_id`에서 결정적으로 만든다(값은 서로 다르다). 스팬은 SDK가 5초 간격으로 묶어 보내고, 정상 종료 때 SDK가 atexit으로 남은 것을 보낸다. 그래서 API·일괄 실행 코드에서 따로 `tracing.flush()`를 부르지 않는다. kill 같은 강제 종료는 이 전송을 건너뛰어 마지막 스팬과 루트 `query`가 유실되고, 코드로 막을 수 없다(2026-11-09 MacBook 확인). README대로 응답 후 기다렸다가 Ctrl+C로 종료한다.
- `record_score(request_id, name, value, comment)`로 평가 점수를 트레이스에 붙인다.
- 셀프호스트 Langfuse 서버는 **v4(4.76.0)**다. SDK `langfuse` 5.x는 v4 서버가 필요하다. 3.x 서버는 SDK가 배열로 보내는 점수를 400("expected object, received array")으로 거절해 점수가 비었다(#34). 2026-11-09에 볼륨 백업 후 3.227.0 → 4.76.0으로 올렸고 `record_score`로 대표 트레이스에 점수 저장을 확인했다.
- 비밀값·API 키는 트레이스에 넣지 않는다.
- `uv run python -m src.platform.check_connections`는 공용 Qdrant 컬렉션 존재 여부와 Langfuse 키 인증을 읽기 전용으로 점검한다. 둘 다 성공하면 종료 코드 0, 미설정·실패·컬렉션 없음은 1. `QDRANT_URL`이 없으면 로컬 저장소를 열지 않는다. 키·응답 본문은 출력하지 않는다. 팀원의 화면 권한·4개 스팬 확인·평가 점수 연결은 별도이며 README의 #40 확인표에 기록한다.
- 2026-11-09 확인: 대표 트레이스의 4개 스팬과 검색 결과·최종 문맥 출력은 조회 가능. 리드 MacBook에서 `QDRANT_API_KEY`로 공용 Qdrant에 접속해 `check_connections` 두 서비스 `ok`(README). Langfuse v4 업그레이드 후 `record_score` 점수 저장 확인. 팀원 PC 접속과 judge 실제 채점 점수 연결(#34)은 아직이다.

보안 비교(`src/platform/security.py`, 미구현 #42)
- 최종 구성 하나, 보안 질문 2개. 한 번 검색한 `final_context`를 저장 → `answer.generate(defense=False)` → 같은 문맥으로 `generate(defense=True)`. 결과 4개를 `results/security.md`에 공격 노출·추종·업무 정확성·과잉 거절로 나눠 기록.

재현
- `README` 설치·실행 절, `.env.example`, Qdrant 실행 방법(Mac Studio의 서버를 `QDRANT_URL`로 쓴다. `QDRANT_URL`을 비우면 `search.store.get_client()`가 로컬 폴더 `data/shipping/qdrant`를 연다. 로컬 `docker run qdrant/qdrant`를 쓰려면 `QDRANT_URL=http://localhost:6333`). 11/11 구현 안 한 팀원이 README대로 설치·실행. 안 되면 README를 고친다.
- 시연 경로(API 호출 → Langfuse 대표 요청) 11/11 녹화.

남은 확인: 팀원 PC의 공용 서비스 접속, judge 실제 채점 1건의 점수 연결(#34), Mac Studio 재부팅 복구. (HTTP 상태 정책·셀프호스트 Langfuse·Qdrant 서버·k=5·평가 모델 gpt-6-luna·Python 3.12/uv는 확정.)

코드 위치: `src/platform/` (`query.py`, `llm.py`, `tracing.py`, `jsonl.py`, `check_connections.py`; `security.py`는 #42에서 추가), `src/api/` (`main.py`; 요청·응답 모델은 `contracts.py`에 있어 `schemas.py`는 두지 않는다), `src/config.py`, `src/contracts.py`

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

def run_query(question: str, mode: RetrievalMode, *, request_id: str | None = None, question_id: str = "",
              channel: str = "eval", user_id: str | None = None) -> RunRecord
```

- `run_query`는 API와 `metrics` 러너가 공유하는 단일 경로다. 검색 → 문맥 → 생성 → 검증 → 측정 → 트레이스를 여기서 묶는다. `channel`은 트레이스 태그(API는 `"api"`), `user_id`는 Langfuse user_id다(위 트레이스 절).
- `llm.call`, `tracing.span`, `record_score`는 다른 영역이 쓰는 유일한 측정·기록 진입점이다.

## 관련 ADR

- 0001, 0002, 0003, 0005
