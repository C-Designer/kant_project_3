# EXP-0001 실행 프롬프트 템플릿 (메모리가 큰 장치 한 대에서 전부 실행)

메모리가 넉넉한 장치(가능하면 GPU도) 한 대에서 EXP-0001(청크 크기 100~900 × 오버랩 0·10·20% × k=4~7 × naive·hybrid·hybrid_rerank)을 처음부터 끝까지 돌리는 프롬프트다. 아래 코드 블록을 Claude Code에 통째로 붙여 넣는다. 채울 값은 없다. 장치 사양에 따라 `{{PROCS}}`(병렬 검색 프로세스 수)만 정한다.

- 프로세스 하나는 임베딩 모델(E5)과 리랭커(bge-reranker-v2-m3)를 각각 올리므로 메모리를 수 GB 쓴다(실측 전. 이 PC에서 검색 프로세스 하나가 약 0.5GB로 시작해 리랭커를 올리면 늘어난다).
- 권장: 메모리 16GB는 1~2개, 32GB 이상은 4개. CPU만 있으면 코어 수가 프로세스 수를 제한한다(코어를 나눠 쓰므로 프로세스를 늘려도 총 속도는 비슷하다). GPU가 있으면 1~2개로 충분하다.
- 조합 파일이 `data/crag_exp/chunk_overlap/` 아래에 조합마다 하나씩 생기고, 이미 있는 조합은 건너뛰므로 중단 후 같은 명령으로 이어 돌릴 수 있다.

## 붙여 넣을 프롬프트

```text
너는 RAG 실험 EXP-0001을 처음부터 끝까지 실행하는 작업자다. 코드와 문서는 고치지 않는다. 실행하고 결과를 모아 보고한다.

[준비]
1. 저장소를 받고 브랜치 `claude/chunk-overlap-experiment-b73dbe`를 체크아웃한다. 먼저 읽을 것: AGENTS.md, docs/experiments/0001-chunk-overlap-k.md.
2. `uv sync` (Python 3.12. pip install 금지).
3. 저장소 루트 기준으로 아래 파일이 있어야 한다. 없으면 만들거나 추측하지 말고 사용자에게 요청한다.
   - data/shipping_basic/documents/*.pdf (15개)
   - data/shipping_basic/evaluation/ (development.json, additional.json, expansion_validation.json 및 각 *_questions.json)
   - results/questions-2.json (질문 15개 선택 파일. git에 없다)
4. 답변 생성에는 `.env`의 OPENAI_API_KEY, OPENAI_BASE_URL이 필요하다. 키 값은 출력하지 않는다. 검색 단계는 키가 필요 없다.

[지켜야 할 것]
- 공용 Qdrant에 색인하지 않는다. 스크립트가 QDRANT_URL과 Langfuse 키를 비우고 메모리 색인을 쓰므로 아래 명령 그대로 실행한다. `src.search.index`를 직접 실행하지 않는다.
- data/는 git 제외다. 결과·청크·정답이 든 파일을 커밋하거나 외부에 올리지 않는다.
- 로그의 Langfuse "No scheme supplied" 오류는 트레이스를 일부러 끈 것이라 무시한다.
- 중간에 멈췄으면 같은 명령을 다시 실행한다. 끝난 조합은 건너뛴다.

[실행] 검색은 크기를 나눠 {{PROCS}}개 프로세스로, 생성은 한 프로세스로 동시에 백그라운드로 돌린다. 아래는 {{PROCS}}=4일 때의 예이다. 다른 값이면 크기 100~900을 프로세스 수만큼 시간이 고르게 나뉘도록(큰 크기와 작은 크기를 섞어서) 묶는다. 모든 크기가 정확히 한 프로세스에 들어가야 한다.
uv run python scripts/chunk_overlap_experiment.py retrieve --sizes 900,100 > retrieve1.log 2>&1 &
uv run python scripts/chunk_overlap_experiment.py retrieve --sizes 800,200 > retrieve2.log 2>&1 &
uv run python scripts/chunk_overlap_experiment.py retrieve --sizes 700,300 > retrieve3.log 2>&1 &
uv run python scripts/chunk_overlap_experiment.py retrieve --sizes 600,500,400 > retrieve4.log 2>&1 &
uv run python scripts/chunk_overlap_experiment.py generate > generate.log 2>&1 &
(Windows PowerShell이면 각각 Start-Process나 별도 터미널로 돌린다.)
generate는 검색이 끝난 조합부터 이어서 생성하고 27개가 모두 끝나면 종료한다. 호출은 약 4,860회(27조합 × 3방식 × 15문항 × k 4개)이며, 스크립트가 6개 스레드로 보낸다. 느리거나 한도 오류가 나면 사용자에게 알린다.
진행은 retrieve*.log의 `s<크기>_o<오버랩>: chunks=N ...초` 줄과 generate.log의 `answers s<크기>_o<오버랩>` 줄로 센다(조합 27개). 폴링하지 말고 백그라운드 종료 알림을 기다린다.

[끝난 뒤]
1. data/crag_exp/chunk_overlap/retrieval/ 와 answers/ 에 각각 파일이 27개(s100_o0 ... s900_o20)인지 센다. 모자라면 어느 조합인지 적고 해당 명령을 다시 실행한다.
2. `uv run python scripts/chunk_overlap_experiment.py report` 를 실행한다. 표는 data/crag_exp/chunk_overlap/tables.md, 원자료는 rows.json에 쌓인다.
3. answers 파일에서 status가 "error"인 기록 수를 세고 원인을 정리한다(timeout, 키, 한도, 출력 검증 실패). 5%를 넘으면 재실행 전에 사용자에게 묻는다.
4. 보고한다: 조합별 청크 수·검색 시간(retrieve 로그), 오류 건수, 실패·이상, 장치 사양(CPU/GPU/메모리)과 프로세스 수, tables.md 경로. 결과 해석은 하지 않는다.
```

## 사람이 하는 일

- 위 프롬프트를 쓰려면 `scripts/chunk_overlap_experiment.py`와 이 문서가 브랜치에 커밋·푸시돼 있어야 한다.
- 실행이 끝나면 `data/crag_exp/chunk_overlap/` 폴더를 이 PC로 가져와 `report`를 다시 돌리거나, 그 장치에서 만든 `tables.md`로 보고서의 "결과" 칸을 채운다.
- 보고서의 "실패·이상 기록"에 실행 장치(CPU/GPU/메모리)와 프로세스 수를 적는다. 리랭크 점수는 장치마다 부동소수점 차이로 미세하게 다를 수 있다.
