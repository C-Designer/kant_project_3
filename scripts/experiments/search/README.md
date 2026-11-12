# 격자 실험 실행 안내 (EXP-0016~0019)

사람과 AI(Claude Code, Codex 등) 모두를 위한 순서서다. 이 순서대로 하면 같은 표가 나오게 만들었다. 막히면 추측하지 말고 "문제 해결"을 먼저 본다.

## 무엇을 하나

청크 크기(100~900, 100 단위) × 오버랩(0·10·20%) × k × 검색 방식(naive·hybrid·hybrid_rerank)을 Basic 골든 3개 세트(72문항)로 재서, 최적의 k·크기·오버랩을 고른다. 4명이 k를 나눠 맡고, 끝나면 합친다.

| 담당 | 계획 문서 | k | `--out` 폴더(예) |
|---|---|---|---|
| 1 | `docs/experiments/search/0016-grid-k-4-11.md` | 4, 11 | `results/exp0016/laptop1` |
| 2 | `docs/experiments/search/0017-grid-k-5-10.md` | 5, 10 | `results/exp0017/laptop2` |
| 3 | `docs/experiments/search/0018-grid-k-6-9.md` | 6, 9 | `results/exp0018/laptop3` |
| 4 | `docs/experiments/search/0019-grid-k-7-8.md` | 7, 8 | `results/exp0019/laptop4` |

**테스트 조건은 계획 문서에 고정돼 있다. 바꾸지 않는다**(크기, 오버랩, k, POOL 20, 질문 세트, 측정 항목). 바꿔야 하면 실행하지 말고 사람에게 묻는다.

## 준비물 (실행 전 확인)

1. 저장소 최신: `git pull`, 계획 문서가 있는 브랜치(또는 머지된 `main`)에서 시작한다.
2. 데이터: `data/shipping/documents/`와 `data/shipping/evaluation/`(`development`, `additional`, `expansion_validation` 각 `*.json`과 `*_questions.json`). 데이터는 저장소에 없고 따로 받는다.
3. `.env`: `OPENAI_API_KEY`, `OPENAI_BASE_URL`(생성·평가 모델 `gpt-6-luna`). **셸 환경 변수에 다른 값이 이미 있으면 `.env`보다 우선한다.** 의심되면 `env -u OPENAI_API_KEY -u OPENAI_BASE_URL uv run ...`로 실행해 `.env` 값을 쓰게 한다.
4. `uv` 설치. 환경은 `uv run`이 `uv.lock`대로 만든다(`pip install` 금지).
5. NVIDIA GPU 노트북(참고 사양: RTX 5060 Laptop 8GB, 24코어, RAM 32GB). 전원 연결, Windows 전원 모드 최고 성능, 다른 무거운 앱·GPU 작업 종료.

GPU용 torch와 모델(E5 small, bge-reranker-v2-m3)은 `check` 단계에서 **없으면 스스로 설치·내려받는다**(처음 한 번 수 분).

## 실행 순서

```bash
# 저장소 루트에서. 아래는 담당 1 예시. k와 --out만 자기 담당으로 바꾼다.
uv run python scripts/experiments/search/grid_kset.py --k 4,11 --out results/exp0016/laptop1
```

기본은 모든 단계(`check` → `retrieval` → `answers` → `e2e` → `ragas`)를 순서대로 돈다. 약 4.7시간(추정). 단계별로 나눠 돌리려면 `--stages check,retrieval` 처럼 쓴다.

| 단계 | 하는 일 | LLM | 결과 폴더 |
|---|---|---|---|
| `check` | 환경 점검, 모델 설치, GPU 메모리 상한 점검 | 없음 | `env.json` |
| `retrieval` | 색인, Hit·Recall(book_id, page+quote), 검색 시간 | 없음 | `retrieval/<크기>_<오버랩%>.json` |
| `answers` | 답변 생성(병렬), 행동 일치율, 토큰, 재생성 | 있음 | `answers/<크기>_<오버랩%>.json` |
| `e2e` | 전체 시간(검색~답변, **직렬**) + 공통 기준점 | 있음 | `e2e/<크기>_0.json`, `e2e/anchor_*.json` |
| `ragas` | faithfulness(3회 평균), 일부 설정·36문항 | 있음 | `ragas/<방식>_<크기>_<오버랩>_k<k>.json` |

옵션(바꿔도 되는 것: 컴퓨팅 한도만):

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--workers` | 24 | 답변 병렬 수. 키를 다른 노트북과 공유하면 12 |
| `--ragas-workers` | 8 | RAGAS 병렬 수 |
| `--threads` | 8 | CPU 스레드 |
| `--gpu-fraction` | 0.5 | GPU 메모리 상한 비율(8GB 기준 4GB) |
| `--limit-q N` | 0 | **시험 실행용**: 세트마다 앞 N문항만. 진짜 실행에서는 쓰지 않는다 |
| `--sizes`, `--pcts` | 100~900, 0,10,20 | 시험용으로만 줄인다 |

**시험 실행 먼저(권장, 몇 분):**
```bash
uv run python scripts/experiments/search/grid_kset.py --k 4,11 --out results/smoke --sizes 500 --pcts 0 --limit-q 1
```
`results/smoke/`에 아래 "결과 파일" 목록이 모두 생기고 `DONE`이 나오면 환경이 맞다. 시험 결과는 문서에 쓰지 않는다.

## 끊기면

같은 명령을 그대로 다시 실행한다. 끝난 설정(파일이 있는 것)은 건너뛰고 이어서 한다. 인터넷이 끊겨 오류가 5%를 넘은 설정은 저장하지 않으니 다시 실행하면 그 설정만 다시 한다.

**주의: 스크립트나 `src/`가 바뀐 뒤에 같은 `--out`으로 다시 돌리면 옛 파일을 건너뛴다.** 코드를 바꿨다면 그 단계의 결과 폴더(`answers/` 등)를 지우고 다시 실행한다.

## 결과 채우기 (끝난 뒤)

```bash
# 1) 이 담당의 계획 문서 "결과" 칸을 표로 채운다(상태가 '실행 중'이 됨)
uv run python scripts/experiments/search/merge_grid_results.py \
  --in results/exp0016/laptop1 --out results/exp0016/report \
  --doc docs/experiments/search/0016-grid-k-4-11.md
```

표(검색 / 답변 품질 / 운영 지표 / 확정값 대비 후보)와 오류 건수는 자동으로 채워진다. **아래는 사람이나 AI가 직접 쓴다.**

1. `## 해석·한계` — 결과가 말해주는 것(문서 맨 위 "좋아졌다고 판단할 기준" 4개와 표를 대조), 말해주지 못하는 것, 조건이 달랐던 점, 우연인지 확인한 방법
2. `## 결정·후속 작업` — 채택 | 기각 | 보류와 이유 한 줄. 최종 결정은 4개를 합친 뒤에 내리므로 담당별 문서에서는 "보류(합친 뒤 결정)"로 둘 수 있다
3. `## 실패·이상 기록` — 오류 원인, 다시 돌린 설정, 제외한 것
4. `- 담당 노트북:`(CPU·GPU·RAM), `git_commit`/`git_dirty`(`env.json` 값), `정답·expected_action은 채점에만 썼다: 예`
5. 상태를 `완료`로 바꾸고 `docs/experiments/README.md`의 해당 행(상태·결정)을 고친다.

```bash
# 2) 네 담당이 모두 끝난 뒤(폴더 4개를 한 곳에 모은다) 전체를 합친다
uv run python scripts/experiments/search/merge_grid_results.py \
  --in results/exp0016/laptop1 results/exp0017/laptop2 results/exp0018/laptop3 results/exp0019/laptop4 \
  --out results/merged
```
`results/merged/merged.md`로 최적의 k·크기·오버랩을 고르고 요약 문서를 새로 쓴다.

## 지켜야 할 것

- `src/`와 `data/`는 고치지 않는다. 정답·`expected_action`·근거는 채점에만 쓴다(스크립트가 이미 그렇게 한다).
- 숫자를 만들어 쓰지 않는다. 표에 없는 값은 "확인 불가"로 적는다. 측정하지 못한 값은 0이 아니라 `None`/`-`.
- 공용 Qdrant에 색인하지 않는다(스크립트가 `QDRANT_URL`을 비워 메모리 Qdrant만 쓴다).
- 키·`.env`·`data/`·`results/`의 원자료를 커밋하지 않는다. 문서에 내 PC 경로를 적지 않는다.
- `완료`된 문서의 본문(가설·조건)은 고치지 않는다. 결과가 이상하면 "실패·이상 기록"에 적는다.
- push와 PR은 사람이 시킬 때만 한다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `점검 실패: ...GPU 사용률이 N%` | 다른 GPU 작업을 끈다. 5% 미만에서 시작해야 시간이 흔들리지 않는다 |
| `GPU 메모리 상한에서 리랭커가 메모리 부족` | `--gpu-fraction 0.6`으로 올린다(시간 측정에는 영향 없음) |
| `OPENAI_API_KEY가 없다` | `.env`를 확인한다. 셸의 잘못된 값이 우선하면 `env -u OPENAI_API_KEY ...`로 실행 |
| 답변 단계 `오류 ... 5%를 넘어 저장하지 않는다` | 429·인터넷 문제. `--workers`를 12나 6으로 낮춰 같은 명령 재실행 |
| 모델 내려받기 실패 | 인터넷 연결 후 같은 명령. 3번 재시도한다 |
| `먼저 retrieval 단계를 돌려야 한다` | 단계 순서대로 돌린다(`--stages`로 뺐다면 앞 단계부터) |
| GPU torch 설치가 안 됨 | `uv`가 있는지 확인. 없으면 `--device cpu`(시간 측정은 다른 노트북과 비교하지 않는다) |

## 결과 파일 구조

```
results/expNNNN/laptopN/
  env.json              환경(GPU·torch·스레드·git 커밋·시작 GPU 사용률·리랭커 GPU 최대 사용량)
  emb_cache.pkl         문서 임베딩 캐시(결과와 무관, 지워도 됨)
  retrieval/<크기>_<오버랩%>.json   문항·방식·k별 청크 id, 검색 시간, Hit·Recall
  answers/<크기>_<오버랩%>.json     문항·방식·k별 답변, 상태 일치, 토큰, LLM 시간, 호출 수
  e2e/<크기>_0.json, anchor_start.json, anchor_end.json   직렬 전체 시간
  ragas/<방식>_<크기>_<오버랩>_k<k>.json   faithfulness
```
