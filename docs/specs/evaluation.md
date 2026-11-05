# evaluation spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: 평가 질문 선택과 기록, 세 방식 일괄 실행, Hit@k·Recall@k, RAGAS Faithfulness, LLM-as-a-Judge 4항목, 운영 지표 집계(측정값은 `platform`이 남긴 것을 모은다), 비교표 생성. 채점 규칙은 [docs/evaluation.md](../evaluation.md).
- 책임 아님: 답변 생성(`answer`), 측정·트레이스(`platform`), 보안 비교 4개(`platform`이 `src/evaluation/security.py`를 소유).

## 동작

1. **질문 선택**: `evaluation/*_questions.json`에서 고른 `id`와 이유를 `results/questions.json`에. 답변 가능 / 추가 확인 / 보류 문항을 섞는다.
2. **일괄 실행**: 질문 × 3방식을 `platform.run_query()`로 실행(API를 거치지 않아도 같은 경로). 실패도 기록. `results/runs/<run_id>/<mode>.jsonl`.
3. **검색 지표**: `evidence_groups`의 `book_id` 집합 vs `retrieved_book_ids`. 참고 목록이 비면 해당 없음.
4. **RAGAS**: `user_input`, `response`, `retrieved_contexts`(= `final_context` 텍스트). 사실 주장 없는 응답은 해당 없음.
5. **Judge**: facts / conditions / evidence / decision 각 0·1·null + reason. 참고 정답·기준은 별도 항목으로. 평가 호출은 `platform.llm.call(kind="eval")`로 서비스 사용량과 분리.
6. **운영 지표**: 정상 요청 평균 응답 시간과 건수, 오류율과 실패 건수, 입력·출력 토큰 합계와 확인 요청 수. 평가 호출 사용량은 별도 열.
7. **비교표**: `results/comparison.md`(+ CSV). 질문별 + 방식별 평균. 평균 옆에 평가 대상 수, 해당 없음, 평가 불가, 오류 건수.
8. **사람 확인**: 대표 사례의 원문 대조 결과와 자동 채점 수정 이력을 `results/review.md`에.

미정: 질문 수, 평가 LLM, RAGAS 버전, Judge 프롬프트 파일, run_id 규칙.

코드 위치: `src/evaluation/` (`questions.py`, `run.py`, `metrics.py`, `ragas_eval.py`, `judge.py`, `report.py`). `security.py`는 `platform` 소유.

## 인터페이스

`src/contracts.py`:

```python
class RunRecord(BaseModel):      # 질문 하나 × 방식 하나
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

class EvalRecord(BaseModel):     # RunRecord에 덧붙임
    hit_at_k: int | None
    recall_at_k: float | None
    faithfulness: float | None
    judge: dict[str, JudgeItem] | None   # facts, conditions, evidence, decision
    eval_tokens: TokenUsage | None
    not_applicable: list[str]
    unscorable: list[str]
```

- `None`은 해당 없음 또는 평가 불가. 어느 쪽인지 `not_applicable` / `unscorable`에 이유. **0으로 바꾸지 않는다.** 집계 함수는 `None`을 분모에서 뺀다. 이 규칙은 단위 테스트로 고정한다.
- 명령(예시): `python -m src.evaluation.run`, `… .score --run <id>`, `… .report --run <id>`.

## 관련 ADR

- 0001, 0002, 0003
