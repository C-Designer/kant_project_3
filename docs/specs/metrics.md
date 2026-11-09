# metrics spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 오주헌. 짝: `judge`(실행 결과를 넘기고 채점 결과를 받음), `platform`(`run_query()` 호출).

## 범위

- 책임: 실험 자동화. 평가 JSON 로더, 질문 선택과 기록, 질문 × 3방식 일괄 실행 러너, Hit@k·Recall@k, 운영 지표 집계(측정값은 `platform`이 남긴 것), `judge` 결과를 합친 비교표 생성. 채점 규칙은 [docs/evaluation.md](../evaluation.md).
- 책임 아님: 답변 생성(`answer`), 측정·트레이스(`platform`), RAGAS·Judge 채점과 사람 대조(`judge`), 보안 비교(`platform`).

## 동작

1. **로더**: `data/shipping/evaluation/*.json`을 읽어 질문(`id`, `question`)과 정답(`evidence_groups`, `expected_action`, 채점 기준)을 분리한다. **보안 질문**(`security_questions.json`·`security_tasks.json`, 2개)은 `load_security()`로 **일반 질문과 분리**해서 읽는다(일반 평균·오류율에 섞지 않는다. 실행·비교는 `platform`). `attack_text` 등 공격 필드는 `rubric`에만 두고 `Question`에는 넣지 않는다. 정답 쪽은 `judge`와 검색 지표 계산에만 넘긴다. 절대 `run_query()` 입력에 섞지 않는다. `judge`에 넘기는 `GroundTruth.rubric`에는 `evidence_groups`의 **원문(`quote`)·`page`·그룹 구조를 원본 그대로** 담는다(원문 대조용). `evidence_book_ids`는 검색 지표용으로 평탄화·중복 제거한 목록이다.
2. **질문 선택**: 고른 `id`와 이유를 `results/questions.json`에. 답변 가능 / 추가 확인 / 보류 문항을 섞는다. **15개 = 답변 9 / 추가 확인 3 / 보류 3**(Basic은 `expected_action`이 answer 57 · abstain 8 · clarify 7로 쏠려 있어 유형별 개수로 고정). 유형 안에서 **근거 문서가 2개 이상인 질문(복수)의 비율을 전체 풀 비율에 맞춘다**(단일 근거만 쏠리면 Hit와 Recall이 같아져 방식 간 차이가 안 드러난다. 첫 초안은 복수 근거가 4/15(27%)로 풀의 67%에 크게 못 미쳤다). 그 위에 **구조 조건**만 건다: 평가 파일(development / additional / expansion_validation)마다 4개 이상, 근거로 나오는 문서가 15개 중 13가지 이상. 시도 `seed-번호`로 뽑아 조건을 처음 만족하는 목록을 쓴다(Basic 기준 시드 20261105의 89번째 시도). 검색 결과는 선택에 쓰지 않는다. 알아둘 점: 근거 문서가 7개인 질문(S-DEV-06, S-FINAL-06)은 청크 5개로는 Recall이 최대 약 0.71이다. 세 방식에 똑같이 적용되어 비교는 공정하지만 절대값은 낮게 나온다. `questions.json`에는 시드·유형별 개수(`quota`)·실제로 고른 분포(`distribution`)·고를 수 있던 전체 분포(`pool`)·선택 조건(`rule`)·질문별 이유를 적는다. 이미 있는 `questions.json`은 덮어쓰지 않는다. `expected_action`은 선택 기록에만 남기고 실행 입력(`Question`: `id`, `question`)에는 넣지 않는다.
3. **러너**(`run.py`): 질문 × 3방식을 `platform.run_query(question, mode)`로 실행(질문 문장과 방식만 넘긴다). 반환된 `RunRecord`의 `question_id`·`question`·`retrieval_mode`는 러너가 입력 값으로 덮어쓴다. 호출이 예외로 끝나면 `status="error"`(시간은 러너가 잰 값, 토큰은 `None`)로 기록하고 계속 간다. `--mock`은 platform 없이 가짜 `run_query`로 연습 실행. 실행 폴더에 `run_meta.json`(방식·질문 id·시작/끝 시각)도 남긴다. `results/runs/<run_id>/<mode>.jsonl`에 `RunRecord` 한 줄씩. `run_id`는 타임스탬프(`YYYYMMDD-HHMMSS`, 선택적으로 `--label` 덧붙임). 재실행 시 같은 `run_id`에 덮어쓰지 않는다.
4. **검색 지표**(`retrieval_metrics.hit_recall`): `evidence_groups`를 평탄화·중복 제거한 `book_id` 집합 vs `retrieved_book_ids[:k]`(같은 문서는 한 번). 참고 목록이 비면 `hit_at_k = recall_at_k = None`, `not_applicable`에 이유. 검색 결과가 비어도 참고 문서가 있으면 0점.
5. **운영 지표**: `RunRecord`의 `latency_ms`, `input_tokens`, `output_tokens`, `status == "error"`에서 정상 요청 평균 응답 시간과 건수, 오류율과 실패 건수, 토큰 합계와 확인 요청 수. `None`은 분모에서 뺀다.
6. **비교표**(`report.py`): `judge`가 돌려준 `EvalRecord`를 `question_id` + `retrieval_mode`로 합쳐 `results/runs/<run_id>/`에 세 파일을 쓴다. `comparison_detail.csv`(질문 × 방식 한 행, 모든 지표), `comparison_summary.csv`(방식별 평균과 `*_n` 평가 대상 수, 해당 없음·평가 불가·오류 건수, 운영 지표), `comparison.md`(발표용). 방식 순서는 naive, hybrid, hybrid_rerank. 평가 호출 토큰은 `eval_*` 별도 열. **집계 범위는 `run_meta.json`의 질문 id**(일반 평가 질문)뿐이다. 그 밖의 실행(보안 비교·모의 오류 시험)은 일반 평균·오류율에서 빼고 표 상단에 `집계 제외 N건`만 남긴다. `comparison.md` 상단 `## 실행 조건`에 run_id, k, 방식, 질문 수, 집계 제외 건수, 질문 선택 시드·유형별 개수, `config.py` 동결값(대문자 상수를 읽음. 파일이 없으면 "없음")을 기록한다. 측정 못 한 값은 CSV에서 빈 칸(0 아님). 해당 없음·평가 불가 이유(`not_applicable`·`unscorable`)는 judge와 합의한 **`"<항목>: <이유>"` 형식**이다. 항목은 `faithfulness`·`facts`·`conditions`·`evidence`·`decision` 중 하나이고 첫 콜론 앞을 항목으로 읽는다. 항목을 알 수 없거나 형식이 아니면 `unclassified`(미분류)로 세어 버리지 않는다. `comparison_detail.csv`에는 원문 이유(`not_applicable`·`unscorable`)와 항목 목록(`not_applicable_items`·`unscorable_items`)을, `comparison_summary.csv`에는 항목별 레코드 수(`not_applicable_<항목>`·`unscorable_<항목>`; 한 레코드에서 같은 항목이 여러 번 나와도 1)를 쓰고, `comparison.md`에 `빈칸 이유` 표를 둔다. 기존 레코드 단위 합계(`not_applicable_records`·`unscorable_records`)도 유지한다.

k는 5로 확정(`src/config.py`의 `K`). 미정 항목 없음.

코드 위치: `src/metrics/` (`loader.py`, `questions.py`, `run.py`, `retrieval_metrics.py`, `ops_metrics.py`, `report.py`, `aggregate.py`(뼈대의 `None` 제외 평균 `mean_excluding_none`. `tests/test_rules.py`가 규칙으로 고정)). 타입은 `src/contracts.py`를 그대로 쓴다. 테스트는 `tests/metrics/` (`uv run pytest tests/metrics`).

## 파일별 역할과 연결

### 전체 흐름

```
평가 JSON (data/shipping/evaluation/*.json)
      │
      ▼
 ┌─────────┐   Question 목록         ┌──────────────┐
 │ loader  │ ───────────────────────▶│ questions    │ → results/questions.json
 │         │   GroundTruth 목록      │ (15개 선택)   │
 └─────────┘ ─────┐                  └──────┬───────┘
                  │                         │ 고른 id
                  │                         ▼
                  │                  ┌──────────────┐
                  │                  │ run          │ ← platform.run_query()
                  │                  │ (질문×3방식)  │
                  │                  └──────┬───────┘
                  │                         │ RunRecord JSONL
                  │                         │ results/runs/<run_id>/<mode>.jsonl
                  │            ┌────────────┴─────────────┐
                  ▼            ▼                          ▼
          ┌──────────────────────┐              ┌──────────────┐
          │ retrieval_metrics    │              │ ops_metrics  │
          │ Hit@k, Recall@k      │              │ 시간·토큰·오류│
          └──────────┬───────────┘              └──────┬───────┘
                     │      judge의 EvalRecord          │
                     │      (RunRecord+GroundTruth를    │
                     │       넘기고 채점 결과를 받음)    │
                     └──────────────┬──────────────────┘
                                    ▼
                             ┌─────────────┐
                             │ report      │ → comparison_detail.csv
                             │ (표 합치기)  │   comparison_summary.csv
                             └─────────────┘   comparison.md
```

핵심 원칙: **정답은 채점 쪽으로만 흐른다.** `GroundTruth`는 `run`으로 가지 않고 `retrieval_metrics`와 `judge`로만 간다.

### 파일별 역할

| 파일 | 입력 → 출력 | 하는 일 |
|---|---|---|
| `loader.py` | 평가 JSON → `Question(id, question)` + `GroundTruth` | 질문(실행용, 정답 정보 없음)과 정답(채점용)을 분리한다. `evidence_book_ids`는 `evidence_groups`를 평탄화·중복 제거한 목록, `rubric`에는 필수 사실·금지 주장·채점 설명·`evidence_groups` 원본을 담는다. part01/part02의 평가 JSON은 동일하므로 한쪽만 읽고, 같은 `id` 중복은 처리한다. |
| `questions.py` | `Question` + `GroundTruth` → `results/questions.json` | `expected_action` 유형별(답변 9 / 추가 확인 3 / 보류 3)로, 근거 문서 수(단일/복수) 비율을 풀에 맞춰 시드 고정 층화 무작위로 15개를 고르고 이유와 함께 기록한다. |
| `run.py` | `questions.json` → `RunRecord` JSONL | 질문 × 3방식을 `platform.run_query()`로 실행한다. 실패도 `status="error"`로 기록, `run_id`는 타임스탬프이며 덮어쓰지 않는다. `--mock`이 아니면 `src.platform.query.run_query`를 부른다. |
| `retrieval_metrics.py` | `evidence_book_ids`, `retrieved_book_ids`, k → `(hit, recall, 해당 없음 사유)` | 상위 k개를 문서 단위로 중복 제거해 Hit@k·Recall@k를 계산한다. 참고 목록이 비면 `None`, 검색 결과가 비어도 참고 문서가 있으면 0점. |
| `ops_metrics.py` | `RunRecord` 목록 → 방식별 집계 | 정상 요청 평균 응답시간·건수, 오류율·실패 건수, 입·출력 토큰 합계·확인 요청 수. `None`은 분모에서 빼고 0으로 바꾸지 않는다. 추가 확인·보류는 오류가 아니다. |
| `report.py` | 검색·운영 지표 + `EvalRecord` → CSV 2개 + md | `question_id` + `retrieval_mode`로 조인해 `comparison_detail.csv`, `comparison_summary.csv`, `comparison.md`를 만든다. 해당 없음·평가 불가는 평균에서 제외, 0점은 포함. 평가 호출 토큰은 `eval_*` 별도 열. |

### 협업 접점

| 상대 | 주고받는 것 |
|---|---|
| `platform` | metrics가 `run_query()`를 호출하고, 시간·토큰 측정값은 platform이 `RunRecord`에 채운다. |
| `judge` | metrics가 `RunRecord` + `GroundTruth`를 넘기고 `EvalRecord`를 받는다. |
| `contracts.py` | `RunRecord`, `GroundTruth`, `EvalRecord`의 기준. 바꾸려면 `[interface]` PR. |

### 구현 순서

`loader` → `retrieval_metrics` → `ops_metrics` → `report` → `questions` → (뼈대 머지 후) `run`. 앞의 네 개는 서로 독립적이라 mock으로 테스트할 수 있고, `run`만 `platform`에 의존한다. 여섯 개 모두 구현됐다(#69, 질문 선택 보강 #88, pandas 제거 #79).

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

- 명령(`uv run python -m ...`으로 실행. 테스트는 `uv run pytest tests/metrics`. `pyproject.toml`의 `pythonpath`로 `src`를 찾는다, #57):
  - 질문 선택: `python -m src.metrics.questions` → `results/questions.json` (기본 15개, 시드 20261105, `--min-per-source 4 --min-docs 13`)
  - 일괄 실행: `python -m src.metrics.run --questions results/questions.json [--modes naive,hybrid,hybrid_rerank] [--label x] [--results-dir results] [--mock]`
  - 비교표: `python -m src.metrics.report --run <run_id> --k <k>` (`results/runs/<run_id>/eval.jsonl`이 있으면 합치고, 없으면 평가 열은 빈 칸)
- `judge`에 넘기는 것: `RunRecord` 목록 + `GroundTruth` 목록. 받는 것: `EvalRecord` 목록(`question_id`, `retrieval_mode`로 조인).
- 집계 함수는 `None`을 분모에서 뺀다. 단위 테스트로 고정.

## 관련 ADR

- 0001, 0002, 0003
