<task>
[T1 변수 주입과 Langfuse 실험 스크립트 확장] 브랜치 exp/exp2-inject.
1. scripts/exp_config.py를 위 interface_contract대로 만든다(apply()).
2. scripts/lf_experiment.py(이미 있음, 읽고 구조를 유지)를 다음처럼 확장한다.
   - 시작할 때 `exp_config.apply()`를 src import보다 먼저 호출한다. 적용된 값 dict를 run 이름 접미사(예: `<stamp>-<mode>-<label>`)와 run metadata에 넣어 Langfuse에서 설정별로 구분되게 한다. EXP_LABEL이 없으면 "baseline".
   - `--no-judge` 옵션: 평가 함수에서 Judge 4항목을 호출하지 않고 Faithfulness(score_one의 faithfulness)와 평가 토큰만 낸다. 지금은 `quality`가 Judge까지 부른다. score_one은 Judge를 따로 끄는 인자가 없으므로, src/judge는 고치지 말고 `src.judge.ragas_eval.faithfulness_repeated`를 직접 부르는 방법을 쓴다(src/judge/score.py:55-95의 score_one이 호출하는 방식을 읽고 같은 반복·토큰 합산 규칙을 따른다). 실행 중인 이벤트 루프에서 RAGAS가 실패하는 문제 때문에 기존 `ThreadPoolExecutor` 우회는 그대로 둔다.
   - 결과를 `results/exp2/<label>.csv`에도 저장한다(방식당 한 행: label, mode, n, hit, recall, action_match, faithfulness, error_rate, latency_ms_mean, input_tokens_sum, output_tokens_sum, eval_input_tokens_sum, eval_output_tokens_sum). None은 빈 칸(0 아님).
   - 데이터셋 이름은 그대로(`kant-exp-basic15`). 정답·기대 동작은 expected_output으로만 넘기는 기존 규칙을 지킨다.
3. 위 문맥 지표(context_tokens, dropped_chunks, truncated)와 검색 시간은 이 작업이 아니라 T4가 만든다. 여기서 만들지 않는다.
</task>

<completeness_contract>
exp_config.apply()를 직접 호출하는 assert 자가 점검: 환경 변수를 바꿔 config 값이 바뀌는지, QDRANT_URL이 설정된 상태에서 RuntimeError가 나는지, index_meta.json이 어긋날 때 RuntimeError가 나는지. 실제 LLM·Langfuse는 부르지 않으므로 lf_experiment.py 전체 실행은 하지 않고, 집계·CSV 부분은 가짜 결과 객체로 점검한다. 기존 `summarize`·`table`의 점검 방식을 따른다.
</completeness_contract>
