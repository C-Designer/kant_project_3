기준 문서: [docs/specs/judge.md](../../docs/specs/judge.md). 공용 타입은 `src/contracts.py`. 채점 규칙은 [docs/evaluation.md](../../docs/evaluation.md).

## 하는 일

`metrics`가 만든 답안(`RunRecord`)과 정답지(`GroundTruth`)를 받아 `EvalRecord`를 만든다.

```
오류 사전 판정 → RAGAS Faithfulness → Judge 4항목(사실·조건·근거·판단) → 채점표 검사·재시도 → EvalRecord → record_score
```

| 파일 | 하는 일 |
|---|---|
| `rules.py` | AI 없이 코드로 정하는 규칙. 서비스 오류 사전 판정, `None`을 뺀 평균 |
| `judge.py` | 채점관 4항목: 메시지 만들기 → 호출 → JSON 검사 → 1회 재시도 |
| `prompts/judge_v1.md` | 채점관 지시문 |
| `ragas_eval.py` | RAGAS Faithfulness. 주장 없음 → 해당 없음, 호출 실패 → 평가 불가. 보류·되묻기 문장은 채점에서 제외 |
| `score.py` | 위를 묶어 `EvalRecord` 생성. `python -m src.judge.score --run <run_id>` |
| `platform_adapter.py` | platform(`llm.call(kind="eval")`, `record_score`)을 부르는 **유일한 창구** |
| `mock_cases.py`, `calibrate.py`, `stability.py`, `ragas_trial.py`, `brief_demo.py` | 채점관 검증 도구(시험지 생성, 정확도·흔들림 측정, RAGAS 시험, 발제 예시) |

## 실행

```bash
uv sync
uv run pytest tests/judge -q                                   # 규칙·채점표·RAGAS 입력 테스트 (AI 호출 없음)
uv run python -m src.judge.brief_demo                          # 발제 예시 1문항을 실제로 채점 (AI 호출)
uv run python -m src.judge.mock_cases --truths data/shipping/evaluation/development.json --out data/judge_mock
uv run python -m src.judge.calibrate --cases data/judge_mock/cases.jsonl --truths data/shipping/evaluation/development.json --per-kind 5
```

- 실제 AI 호출에는 `.env`의 `OPENAI_API_KEY`가 필요하다(`config.py`가 읽는다).
- 시험지에는 정답 인용문이 들어가므로 `data/` 아래에만 저장한다(커밋 금지).
- 평가 호출은 `platform.llm.call(kind="eval")`로만 나가고, 서비스 사용량과 섞이지 않는 별도 트레이스에 남는다.
