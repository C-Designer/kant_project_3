# answer spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: 답변 품질 전체. 검색 결과를 받아 문맥을 조립하고(자료 ID `S1`·`S2`, 토큰 한도), 프롬프트로 `gpt-6-luna`를 호출하고, 출력 JSON을 검증하고, 자료 ID를 출처로 바꾼다. 되묻기(`needs_clarification`)와 보류(`abstained`) 판단이 질문에 맞게 나오도록 프롬프트를 다듬는다. 보안 비교용 방어 프롬프트 변형.
- 책임 아님: HTTP 라우팅·오류 응답 형식·timeout·재시도 정책·트레이스(`platform`), 검색(`search`), 채점(`evaluation`).
- 개인정보: 교육용 가상 자료. 데이터셋 확인 후 "해당 없음" 여부를 여기 한 줄로 기록(미확인).

## 동작

1. `retrieve()` 결과에 `S1`, `S2`, … 자료 ID를 붙이고 `source_id → ChunkMeta` 대응표를 요청 안에서 보관한다.
2. 입력 토큰 한도 안에서 문맥을 자른다. 잘라도 대상, 적용일, 단위, 정정 내용, 출처는 남긴다. 잘린 청크를 기록한다.
3. 프롬프트는 서비스 지시 / 질문 / 검색 자료를 구분한다. 판단 순서는 [requirements.md](../requirements.md) "프롬프트와 출력 검증". 본문은 `src/answer/prompts/*.md` 파일.
4. LLM 호출은 `platform.llm.call()`을 통해서만 한다(여기서 timeout·재시도·토큰 측정·트레이스가 붙는다).
5. 출력 검증: JSON 파싱, `status ∈ {answered, needs_clarification, abstained}`, 필수 필드, `source_ids ⊆ 문맥의 자료 ID`. 실패 시 정한 횟수 안에서 재생성, 그래도 실패면 `ValidationFailed`를 올린다(`platform`이 `error`로 변환).
6. `citations` = `source_ids`를 대응표로 변환. LLM이 문서명·페이지를 만들지 않는다.
7. 검색 결과가 비면 "검색한 자료에서 확인하지 못했다"로 `abstained`, `source_ids = []`.

미정: `k` 기본값과 문맥 토큰 한도(`config.py`에서 동결), 생성 설정, 재생성 횟수, 프롬프트 v1 본문, 방어 문장.

코드 위치: `src/answer/` (`context.py`, `chain.py`, `validate.py`, `prompts/`)

## 인터페이스

```python
class ContextChunk(BaseModel):
    source_id: str          # "S1"
    text: str
    metadata: ChunkMeta

class LLMOutput(BaseModel):  # 모델이 내는 JSON
    status: Literal["answered", "needs_clarification", "abstained"]
    answer: str
    reason: str
    source_ids: list[str]

class Citation(BaseModel):
    source_id: str
    book_id: str
    file_name: str
    page: int

def build_context(chunks: list[RetrievedChunk], *, token_limit: int) -> list[ContextChunk]
def generate(question: str, context: list[ContextChunk], *, defense: bool = False) -> tuple[LLMOutput, list[Citation]]
```

- `generate`는 순수하게 "문맥 → 답변"만 한다. 보안 비교는 `platform`이 저장한 문맥으로 `generate(..., defense=True/False)`를 두 번 부른다.
- 프롬프트 파일을 바꾸는 PR은 되묻기 1문항·보류 1문항·정상 1문항의 실행 결과를 PR에 붙인다.

## 관련 ADR

- 0001, 0002, 0003
