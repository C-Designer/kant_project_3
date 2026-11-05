# service spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: FastAPI `/health`, `/query`. 요청 검증, 검색 호출, 문맥 조립(자료 ID 부여, 토큰 한도), 프롬프트, `gpt-6-luna` 호출, 출력 JSON 검증, 자료 ID → 출처 매핑, 상태·오류 처리, timeout·재시도. 요청 ID 생성.
- 책임 아님: 검색 알고리즘(`retrieval`), 트레이스 저장(`observability`), 채점(`evaluation`).
- 개인정보 처리: 교육용 가상 자료. 데이터셋 확인 후 "해당 없음" 여부를 여기 한 줄로 기록한다(미확인).

## 동작

1. `/query` 요청 검증: 빈 질문, 지원하지 않는 `retrieval_mode` → 422.
2. `request_id` 생성(UUID). 이후 모든 기록에 붙인다.
3. `retrieval.retrieve(question, mode, k)`.
4. 문맥 조립: 청크에 `S1`, `S2`, … 자료 ID를 붙이고 `source_id → (book_id, file_name, page)` 대응표를 메모리에 둔다. 입력 토큰 한도 안에서 자른다. 자를 때도 대상, 적용일, 단위, 정정 내용, 출처는 남긴다.
5. 프롬프트: 서비스 지시 / 질문 / 검색 자료를 구분. 판단 순서는 [requirements.md](../requirements.md) "프롬프트와 출력 검증".
6. LLM 호출. timeout·최대 재시도 미정(실행 전 고정).
7. 출력 검증: JSON 파싱, `status ∈ {answered, needs_clarification, abstained}`, 필수 필드, `source_ids ⊆ 문맥의 자료 ID`. 실패하면 정한 횟수 안에서 재생성, 그래도 실패하면 `status: error`, `reason: output_validation`.
8. `citations` 구성: `source_ids`를 대응표로 변환. LLM이 문서명·페이지를 만들지 않는다.
9. 응답 반환. 전 과정을 `observability`로 기록(요청 ID, 질문, 검색 결과, 최종 문맥, 실제 모델 입출력, 상태, 인용, 시간, 토큰, 오류).

미정: `k` 기본값, 문맥 토큰 한도, 생성 설정(temperature 등), timeout, 재시도 횟수, 프롬프트 본문(`src/service/prompts/`에 파일로 둔다).

코드 위치: `src/service/`

## 인터페이스

`GET /health` → `{ "status": "ok" }`

`POST /query`

```json
{ "question": "string (비어 있으면 422)", "retrieval_mode": "naive | hybrid | hybrid_rerank" }
```

```json
{
  "request_id": "uuid",
  "status": "answered | needs_clarification | abstained | error",
  "answer": "답변, 되물을 내용, 보류 설명, 또는 오류 안내",
  "reason": "판단 이유 (error면 model_timeout / output_validation / … 코드)",
  "citations": [ { "source_id": "S2", "book_id": "FB01", "file_name": "FB01.pdf", "page": 3 } ]
}
```

- `error`일 때 `citations`는 `[]`. HTTP는 200(요청은 처리됨) 또는 5xx 중 하나로 고정(미정).
- LLM 출력 스키마(내부): `{ "status", "answer", "reason", "source_ids": ["S2"] }`.
- `evaluation`이 일괄 실행에 쓰는 내부 함수도 같은 결과를 돌려준다:

```python
def answer(question: str, mode: RetrievalMode, *, request_id: str | None = None) -> QueryResult
```

`QueryResult`는 API 응답 + `final_context`(실제 모델에 넘긴 문맥), `retrieved`(검색 결과), `latency_ms`, `input_tokens`, `output_tokens`, `error`. 측정 못 한 값은 `None`.

보안 비교용: 검색을 건너뛰고 저장된 문맥으로 생성만 하는 진입점이 필요하다.

```python
def answer_with_context(question: str, final_context: list[ContextChunk], *, defense: bool) -> QueryResult
```

## 관련 ADR

- 0001, 0002, 0003
