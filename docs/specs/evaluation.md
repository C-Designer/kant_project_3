# evaluation spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: 평가 질문 선택과 기록, 세 방식 일괄 실행, Hit@k·Recall@k, RAGAS Faithfulness, LLM-as-a-Judge 4항목, 운영 지표 집계, 보안 비교 4개, 비교표 생성. 채점 규칙은 [docs/evaluation.md](../evaluation.md).
- 책임 아님: 서비스 로직(`service`), Langfuse 트레이스 자체(`observability`. 단, 점수를 트레이스에 붙이는 건 여기서 호출).

## 동작

1. **질문 선택**: `evaluation/*_questions.json`에서 고른 `id` 목록과 선택 이유를 `results/questions.json`에 기록. 답변 가능 / 추가 확인 / 보류 문항을 섞는다.
2. **일괄 실행**: 질문 × 3방식을 `service.answer()`로 실행. 실패도 기록. 결과를 `results/runs/<run_id>/<mode>.jsonl`에 저장(실행 레코드 아래).
3. **검색 지표**: `evidence_groups`의 `book_id` 집합 vs 상위 k 청크의 `book_id` 집합. 참고 목록이 빈 문항은 해당 없음.
4. **RAGAS**: `user_input`, `response`, `retrieved_contexts`(= `final_context`). 사실 주장 없는 응답은 해당 없음.
5. **Judge**: facts / conditions / evidence / decision 각 0·1·null + reason. 참고 정답·기준은 별도 항목으로 전달.
6. **운영 지표**: 정상 요청 평균 응답 시간과 건수, 오류율과 실패 건수, 입력·출력 토큰 합계와 확인 요청 수. 채점 호출 사용량은 별도.
7. **보안 비교**: 최종 구성 하나, 보안 질문 2개. 한 번 검색한 문맥을 저장 → `service.answer_with_context(defense=False)` → 같은 문맥으로 `defense=True`. 공격 노출 여부, 추종 여부, 업무 답변 정확성, 불필요한 거절을 나눠 기록.
8. **비교표**: 질문별 + 방식별 평균을 `results/comparison.md`(+ CSV)로 생성. 평균 옆에 평가 대상 수, 해당 없음, 평가 불가, 오류 건수.

미정: 질문 수, k, 평가 LLM, RAGAS 버전, Judge 프롬프트 파일 위치, 사람 확인 결과 기록 형식.

코드 위치: `src/evaluation/`. 결과는 `results/`(git에 올린다. 발표 근거).

## 인터페이스

실행 레코드 (한 줄 = 질문 하나 × 방식 하나):

```json
{
  "question_id": "dev-001",
  "request_id": "uuid",
  "retrieval_mode": "hybrid",
  "question": "…",
  "status": "answered",
  "answer": "…",
  "reason": "…",
  "citations": [ { "source_id": "S2", "book_id": "FB01", "file_name": "FB01.pdf", "page": 3 } ],
  "retrieved_book_ids": ["FB01", "FB03"],
  "final_context": [ { "source_id": "S1", "book_id": "FB01", "page": 3, "text": "…" } ],
  "latency_ms": 1234,
  "input_tokens": 1500,
  "output_tokens": 120,
  "error": null
}
```

평가 레코드 (실행 레코드에 덧붙임):

```json
{
  "hit_at_k": 1, "recall_at_k": 0.5,
  "faithfulness": 0.9,
  "judge": { "facts": {"score": 1, "reason": "…"}, "conditions": {…}, "evidence": {…}, "decision": {…} },
  "eval_tokens": { "input": 800, "output": 200 },
  "not_applicable": [], "unscorable": []
}
```

- `null`은 해당 없음 또는 평가 불가. 이유를 `not_applicable` / `unscorable`에 적는다. 0으로 바꾸지 않는다.
- 명령(예시, 확정 후 갱신): `python -m src.evaluation.run --questions results/questions.json --modes naive,hybrid,hybrid_rerank`, `python -m src.evaluation.score --run <run_id>`, `python -m src.evaluation.security --mode <final_mode>`, `python -m src.evaluation.report --run <run_id>`.

## 관련 ADR

- 0001, 0002, 0003
