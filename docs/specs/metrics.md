# metrics spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 오주헌. 짝: `judge`(실행 결과를 넘기고 채점 결과를 받음), `platform`(`run_query()` 호출).

## 범위

- 책임: 실험 자동화. 평가 JSON 로더, 질문 선택과 기록, 질문 × 3방식 일괄 실행 러너, Hit@k·Recall@k, 운영 지표 집계(측정값은 `platform`이 남긴 것), `judge` 결과를 합친 비교표 생성. 채점 규칙은 [docs/evaluation.md](../evaluation.md).
- 책임 아님: 답변 생성(`answer`), 측정·트레이스(`platform`), RAGAS·Judge 채점과 사람 대조(`judge`), 보안 비교(`platform`).

## 동작

1. **로더**: `data/<분야>/evaluation/*.json`을 읽어 질문(`id`, `question`)과 정답(`evidence_groups`, `expected_action`, 채점 기준)을 분리한다. 정답 쪽은 `judge`와 검색 지표 계산에만 넘긴다. 절대 `run_query()` 입력에 섞지 않는다.
2. **질문 선택**: 고른 `id`와 이유를 `results/questions.json`에. 답변 가능 / 추가 확인 / 보류 문항을 섞는다. 수는 미정.
3. **러너**: 질문 × 3방식을 `platform.run_query()`로 실행. 실패도 기록. `results/runs/<run_id>/<mode>.jsonl`에 `RunRecord` 한 줄씩. 재실행 시 같은 `run_id`에 덮어쓰지 않는다.
4. **검색 지표**: `evidence_groups`의 `book_id` 집합 vs `retrieved_book_ids`. 참고 목록이 비면 `hit_at_k = recall_at_k = None`, `not_applicable`에 이유.
5. **운영 지표**: `RunRecord`의 `latency_ms`, `input_tokens`, `output_tokens`, `status == "error"`에서 정상 요청 평균 응답 시간과 건수, 오류율과 실패 건수, 토큰 합계와 확인 요청 수. `None`은 분모에서 뺀다.
6. **비교표**: `judge`가 돌려준 `EvalRecord`를 `question_id` + `retrieval_mode`로 합쳐 `results/comparison.md`(+ CSV). 질문별 + 방식별 평균. 평균 옆에 평가 대상 수, 해당 없음, 평가 불가, 오류 건수. 평가 호출 토큰은 별도 열.

미정: 질문 수, k(`config.py`), run_id 규칙, CSV 열 순서.

코드 위치: `src/metrics/` (`loader.py`, `questions.py`, `run.py`, `retrieval_metrics.py`, `ops_metrics.py`, `report.py`)

## 인터페이스

`src/contracts.py`:

```python
class RunRecord(BaseModel):      # 질문 하나 × 방식 하나. metrics가 만들고 judge가 읽는다
    question_id: str
    request_id: str
    retrieval_mode: RetrievalMode
    question: str
    status: Literal["answered", "needs_clarification", "abstained", "error"]
    answer: str
    reason: str
    citations: list[Citation]
    retrieved_book_ids: list[str]
    final_context: list[ContextChunk]
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None

class GroundTruth(BaseModel):    # 로더가 judge에 넘기는 정답 측
    question_id: str
    evidence_book_ids: list[str]     # evidence_groups 평탄화·중복 제거
    expected_action: Literal["answer", "clarify", "abstain"]
    reference_answer: str
    rubric: dict                     # 필수 사실, 금지 주장, 채점 설명 등 원본 그대로
```

- 명령(예시): `python -m src.metrics.run --questions results/questions.json --modes naive,hybrid,hybrid_rerank`, `python -m src.metrics.report --run <run_id>`.
- `judge`에 넘기는 것: `RunRecord` 목록 + `GroundTruth` 목록. 받는 것: `EvalRecord` 목록(`question_id`, `retrieval_mode`로 조인).
- 집계 함수는 `None`을 분모에서 뺀다. 단위 테스트로 고정.

## 관련 ADR

- 0001, 0002, 0003
