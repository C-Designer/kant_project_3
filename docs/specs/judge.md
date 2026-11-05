# judge spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 김경민. 짝: `metrics`(실행 결과를 받고 채점 결과를 넘김).

## 범위

- 책임: LLM 평가. RAGAS Faithfulness 연동, LLM-as-a-Judge 4항목(사실·조건·근거·판단) 채점 프롬프트와 파싱, 해당 없음/평가 불가 `null` 규칙, 자동 채점 결과를 Langfuse 트레이스에 점수로 붙이기, 대표 사례 원문 대조와 사람 확인 기록. 채점 규칙은 [docs/evaluation.md](../evaluation.md).
- 책임 아님: 실행·집계·표(`metrics`), 보안 비교(`platform`), 답변 생성(`answer`).

## 동작

1. 입력은 `metrics`가 만든 `RunRecord` + `GroundTruth`. 채점은 답변이 만들어진 **뒤**에만 한다.
2. **RAGAS Faithfulness**: `user_input` = 질문, `response` = 답변, `retrieved_contexts` = `final_context`의 텍스트. 참고 정답을 `retrieved_contexts`에 덧붙이지 않는다. 사실 주장이 없는 응답(조건만 되물음)은 `None` + `not_applicable`.
3. **Judge 4항목**: 프롬프트 골격은 [docs/evaluation.md](../evaluation.md) "채점 프롬프트". 입력은 질문, 답변, 상태, 인용, 실제 최종 문맥, 참고 정답과 기준(별도 항목). 출력 `facts / conditions / evidence / decision` 각 `{score: 0|1|null, reason}`. `null`은 이유에서 해당 없음과 평가 불가를 구분한다.
4. **규칙**: 필수 사실·인용 누락은 `0`(해당 없음 아님). 서비스 `error`면 `decision = 0`, 나머지는 `unscorable`. 채점 호출 실패는 `unscorable` + 사유. **`null`을 0이나 1로 바꾸지 않는다.** 단위 테스트로 고정.
5. 평가 호출은 `platform.llm.call(kind="eval")`로만. 서비스 사용량과 섞이지 않는다. 호출 토큰은 `eval_tokens`에.
6. 점수는 `platform.tracing.record_score(request_id, ...)`로 Langfuse 트레이스에 붙인다.
7. **사람 확인**: 대표 사례(좋아진·나빠진 것, 영역당 2~3건)를 PDF 원문과 대조해 `results/review.md`에. 자동 채점 오류를 발견하면 원래 점수와 수정 이유를 함께 남긴다. 사람 확인이 자동 평가를 대신하지 않는다.

미정: 평가 LLM(생성 모델과 같아도 됨, `config.py`), RAGAS 버전, Judge 프롬프트 파일(`src/judge/prompts/`), 재시도 정책.

코드 위치: `src/judge/` (`ragas_eval.py`, `judge.py`, `prompts/`, `review.md` 템플릿)

## 인터페이스

`src/contracts.py`:

```python
class JudgeItem(BaseModel):
    score: Literal[0, 1] | None
    reason: str

class TokenUsage(BaseModel):
    input: int | None
    output: int | None

class EvalRecord(BaseModel):     # judge가 만들고 metrics가 합친다
    question_id: str
    retrieval_mode: RetrievalMode
    faithfulness: float | None
    judge: dict[str, JudgeItem] | None   # facts, conditions, evidence, decision
    eval_tokens: TokenUsage | None
    not_applicable: list[str]            # 해당 없음 이유
    unscorable: list[str]                # 평가 불가 이유

def score(runs: list[RunRecord], truths: list[GroundTruth]) -> list[EvalRecord]
```

- 명령(예시): `python -m src.judge.score --run <run_id>` → `results/runs/<run_id>/eval.jsonl`.
- 세 방식에 같은 평가 모델·프롬프트·설정. 설정은 `config.py`에 기록.

## 관련 ADR

- 0001, 0002, 0003
