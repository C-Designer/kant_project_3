# 문맥 한도 실험 실행 안내 (EXP-0020~0023)

사람과 AI(Claude Code, Codex 등) 모두를 위한 순서서다. 이 순서대로 하면 같은 표가 나오게 만들었다. 막히면 추측하지 말고 "문제 해결"을 먼저 본다.

## 무엇을 하나

청크 크기(600·700·800·900) × 문맥 토큰 한도(3000·3400·3800·4200) × k(5~11) × 검색 방식(naive·hybrid·hybrid_rerank)을 Basic 골든 3개 세트(72문항)로 재서, 문맥 한도가 근거 청크를 얼마나 밀어내는지와 그 영향(Recall, 답변, 토큰, 지연 시간, faithfulness)을 본다. 4명이 k를 나눠 맡고 **k는 큰 값부터 역순**으로 돈다. 끝나면 합친다.

| 담당 | 계획 문서 | k (큰 k부터) | `--out` 폴더(예) |
|---|---|---|---|
| 1 | `docs/experiments/search/0020-ctxmax-k-11-5.md` | 11, 5 | `results/exp0020/laptop1` |
| 2 | `docs/experiments/search/0021-ctxmax-k-10-6.md` | 10, 6 | `results/exp0021/laptop2` |
| 3 | `docs/experiments/search/0022-ctxmax-k-9-7.md` | 9, 7 | `results/exp0022/laptop3` |
| 4 | `docs/experiments/search/0023-ctxmax-k-8.md` | 8 | `results/exp0023/laptop4` |

**테스트 조건은 계획 문서에 고정돼 있다. 바꾸지 않는다**(크기, 한도, k, 방식, POOL 20, 질문 세트, 측정 항목). 바꿔야 하면 실행하지 말고 사람에게 묻는다. 각 문서의 "실행 순서"에 담당별 정확한 명령이 있다.

## 준비물 (실행 전 확인)

1. 저장소 최신: `git pull`, 계획 문서가 있는 브랜치(또는 머지된 `main`)에서 시작한다.
2. 데이터: `data/shipping/documents/`와 `data/shipping/evaluation/`(`development`, `additional`, `expansion_validation` 각 `*.json`과 `*_questions.json`). 데이터는 저장소에 없고 따로 받는다.
3. `.env`: `OPENAI_API_KEY`, `OPENAI_BASE_URL`(생성·평가 모델 `gpt-6-luna`). **셸 환경 변수에 다른 값이 이미 있으면 `.env`보다 우선한다.** 의심되면 `env -u OPENAI_API_KEY -u OPENAI_BASE_URL uv run ...`로 실행해 `.env` 값을 쓰게 한다.
4. `uv` 설치. 환경은 `uv run`이 `uv.lock`대로 만든다(`pip install` 금지).
5. **4대 모두 같은 설정**(같은 사양: RTX 5060 Laptop 8GB, 24코어, RAM 약 32GB). 전원 연결, Windows 전원 모드 최고 성능, 다른 무거운 앱·GPU 작업 종료.

GPU용 torch와 모델(E5 small, bge-reranker-v2-m3)은 `check` 단계에서 **없으면 스스로 설치·내려받는다**(처음 한 번 수 분).

## 컴퓨팅 환경 (모든 노트북 공통, 코드가 지킨다)

| 항목 | 값 | 어떻게 지켜지나 |
|---|---|---|
| 장치 | GPU 1개, 프로세스 1개 | GPU 이름에 `RTX 5060`이 없으면 중단(`--expect-gpu`) |
| GPU 메모리 | 프로세스당 50%(약 4.2GB) | 코드에서 직접 제한(`--gpu-fraction`), 단계마다 최대 사용량 기록 |
| CPU | 스레드 8개 + 코어 8개 | 코어를 묶고 적용 여부를 다시 읽어 확인, 못 걸면 중단(`--threads`, `--cpu-cores`) |
| 시작 전 | GPU 사용률 5% 미만, 여유 RAM 8GB 이상, 전원 연결 | `check`에서 중단(`--min-free-ram-gb`, `--allow-battery`는 시험용) |
| 답변 병렬 | 24(키 공유 시 12) | 실패가 5%를 넘으면 절반으로 줄여 실패분만 재시도(`--workers`) |
| 전체 시간 측정 | 검색은 항상 직렬, **LLM 호출은 동시 8개**(`--e2e-workers 8`), 공통 기준점은 직렬 | 단계를 분리. 값은 환경 지문에 들어가 4대가 같아야 한다 |
| 기록 | `env.json`, `usage.json`(단계별 소요 시간, 최대 메모리·GPU, GPU 온도·열 제한) | 자동. 합칠 때 노트북 간 환경이 다르면 ⚠ 표시 |

## 실행 순서

```bash
# 저장소 루트에서. 아래는 담당 1 예시. 담당별 k와 --out은 각 계획 문서의 명령을 그대로 쓴다.
uv run python scripts/experiments/search/grid_kset.py --k 11,5 --k-order desc \
  --sizes 600,700,800,900 --pcts 0 --context-max 3000,3400,3800,4200 \
  --ragas-sizes 600,700,800,900 --e2e-modes naive,hybrid,hybrid_rerank --e2e-workers 8 \
  --out results/exp0020/laptop1
```

기본은 모든 단계(`check` → `retrieval` → `answers` → `e2e` → `ragas`)를 순서대로 돈다. 시간은 각 계획 문서의 표(추정)를 본다. 단계별로 나눠 돌리려면 `--stages check,retrieval` 처럼 쓴다.

| 단계 | 하는 일 | LLM | 결과 |
|---|---|---|---|
| `check` | 환경 점검, 모델 설치, GPU 메모리 점검 | 없음 | `env.json` |
| `retrieval` | 색인, **선별 과정 기록**(E5·BM25·RRF·리랭크 순위·점수·내부 단계 시간), Hit·Recall 3단계, 검색 시간(`retrieve()`), 한도별 사용 청크, 청크 본문 | 없음 | `retrieval/<크기>_<오버랩%>.json` |
| `answers` | 답변 생성(병렬), 행동 일치율, 토큰, 재생성. **문맥이 같은 한도는 재사용** | 있음 | `answers/<크기>_<오버랩%>.json` |
| `e2e` | 전체 시간(**검색 + 문맥 + LLM 답변**)을 `--e2e-modes` 방식마다(검색 직렬, LLM 동시 `--e2e-workers`개) + 공통 기준점(직렬). 큰 한도는 전 문항, 나머지는 문맥이 달라진 문항만 다시 호출 | 있음 | `e2e/<크기>_0.json`, `e2e/anchor_*.json` |
| `ragas` | faithfulness(3회 평균, 채점 토큰 기록). 문맥이 같으면 한 번만 채점 | 있음 | `ragas/<방식>_<크기>_<오버랩>_k<k>.json` |

### 지표 (표에는 아래 이름을 그대로 쓴다)

Recall과 Hit를 **3단계로 따로** 적는다. 뒤로 갈수록 엄격하다.

| 단계 | 뜻 | Recall | Hit |
|---|---|---|---|
| ① 문서(book_id) | 근거 문서의 청크를 가져왔는가(id만) | 공식 정의: 모든 그룹의 모든 대안 문서 중 찾은 비율 | 근거 문서를 하나라도 |
| ② 쪽(book_id+page) | 그 문서의 **근거 쪽** 청크까지 | 그룹 단위: 충족한 그룹 ÷ 전체 그룹(그룹 안 대안 하나면 충족) | 근거 쪽을 하나라도 |
| ③ 쪽+인용문(page+quote) | 그 쪽에서 **quote가 든 청크**까지(인용문 앞 40자, 공백·`|` 제거) | 그룹 단위 | quote가 든 청크를 하나라도 |

모든그룹 충족률(①②③): 모든 그룹이 충족인 문항의 비율. 근거 있는 문항만 대상이다. 지연 시간은 **검색**(`retrieve()`와 내부 단계), **LLM 답변**, **합계**를 따로 적는다. 토큰은 답변(입력·출력)과 faithfulness 채점을 따로 센다.

### 옵션

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--k` | (필수) | 이 담당의 k. 예: `11,5` |
| `--k-order` | `asc` | `desc`면 큰 k부터 돈다 |
| `--sizes`, `--pcts` | 100~900, 0,10,20 | 크기·오버랩. 이 실험은 `600,700,800,900`, `0` |
| `--context-max` | `3000` | 문맥 토큰 한도 목록 |
| `--modes` | 3방식 | 검색 방식 |
| `--e2e-modes` | `hybrid_rerank` | 전체 시간을 재는 방식. 이 실험은 3방식 모두 |
| `--e2e-workers` | 1 | 전체 시간 측정에서 LLM 호출을 동시에 내보내는 수(검색은 항상 직렬). 이 실험은 **8**(4대 모두 같은 값) |
| `--ragas-sizes` | `500,900` | faithfulness를 재는 크기 |
| `--ragas-sample` | `odd` | `odd` = 세트마다 홀수 번째 문항, `all` = 전체 |
| `--workers`, `--ragas-workers` | 24, 8 | 병렬 수 |
| `--threads`, `--cpu-cores`, `--gpu-fraction` | 8, 8, 0.5 | 컴퓨팅 한도(위 표). 바꾸면 노트북 간 비교가 안 된다 |
| `--limit-q N` | 0 | **시험 실행용**: 세트마다 앞 N문항만 |

**시험 실행 먼저(권장, 몇 분)** — 각 계획 문서에 담당별 명령이 있다. 예:
```bash
uv run python scripts/experiments/search/grid_kset.py --k 11,5 --k-order desc --sizes 900 --pcts 0 \
  --context-max 3000,4200 --ragas-sizes 900 --e2e-modes naive,hybrid,hybrid_rerank --e2e-workers 8 --limit-q 1 --out results/smoke
```
`results/smoke/`에 "결과 파일 구조"의 파일이 모두 생기고 `DONE`이 나오면 환경이 맞다. 시험 결과는 문서에 쓰지 않는다.

## 끊기면

같은 명령을 그대로 다시 실행한다. 끝난 설정(파일이 있는 것)은 건너뛰고 이어서 한다. 인터넷이 끊겨 오류가 5%를 넘은 설정은 저장하지 않으니 다시 실행하면 그 설정만 다시 한다.

**주의: 스크립트나 `src/`가 바뀐 뒤에 같은 `--out`으로 다시 돌리면 옛 파일을 건너뛴다.** 코드를 바꿨다면 그 단계의 결과 폴더(`answers/` 등)를 지우고 다시 실행한다.

## 결과 채우기 (끝난 뒤)

```bash
# 1) 이 담당의 계획 문서 "결과" 칸을 표로 채운다(상태가 '실행 중'이 됨)
uv run python scripts/experiments/search/merge_grid_results.py \
  --in results/exp0020/laptop1 \
  --doc docs/experiments/search/0020-ctxmax-k-11-5.md
```

표(검색 / 답변 품질 / 운영 지표 / 확정값 대비 후보)와 오류 건수는 자동으로 채워진다. **아래는 사람이나 AI가 직접 쓴다.**

1. `## 해석·한계` — 결과가 말해주는 것(문서 "좋아졌다고 판단할 기준" 4개와 표를 대조), 말해주지 못하는 것, 조건이 달랐던 점, 우연인지 확인한 방법
2. `## 결정·후속 작업` — 채택 | 기각 | 보류와 이유 한 줄. 최종 결정은 4개를 합친 뒤에 내리므로 담당별 문서에서는 "보류(합친 뒤 결정)"로 둘 수 있다
3. `## 실패·이상 기록` — 오류 원인, 다시 돌린 설정, 제외한 것
4. `- 담당 노트북:`(CPU·GPU·RAM), `git_commit`/`git_dirty`(`env.json` 값), `정답·expected_action은 채점에만 썼다: 예`
5. 상태를 `완료`로 바꾸고 `docs/experiments/README.md`의 해당 행(상태·결정)을 고친다.

```bash
# 2) 네 담당이 모두 끝난 뒤(폴더 4개를 한 곳에 모은다) 전체를 합친다
uv run python scripts/experiments/search/merge_grid_results.py \
  --in results/exp0020/laptop1 results/exp0021/laptop2 results/exp0022/laptop3 results/exp0023/laptop4 \
  --out results/merged
```
`results/merged/merged.md`로 한도별 영향을 보고 요약 문서를 새로 쓴다.

## 사례 보고서와 질문별 파일

```bash
# 한 설정의 모든 문항을 한 파일로(선별 과정, 청크 전문, 골든 quote·골든 답변, LLM 답변 비교, faithfulness)
uv run python scripts/experiments/search/make_case_report.py --in results/exp0020/laptop1 --mode hybrid_rerank --size 900 --k 11 --only-dropped
# 질문마다 파일을 나눠서(가져온 청크 k개의 본문·메타데이터, 골든 book_id·page·quote, 골든→청크 매핑, 원본 쪽 .md)
uv run python scripts/experiments/search/export_question_md.py --in results/exp0020/laptop1 --mode hybrid_rerank --size 900 --k 5
```

질문별 파일은 `index.md`(질문 목록·판정 요약·한도별 밀려난 청크 수), `questions/<세트>_<문항>.md`, `source_pages/<book>-p<쪽>.md`(원본 쪽 텍스트)가 생긴다. 질문 파일에는 **질문 ↔ 골든 데이터셋 매핑**, 골든 기대와 원본 쪽(접는 블록), **한도별로 밀려나는 청크**(상위 k개 전부 ✅/❌), 청크 본문·메타데이터, LLM 답변 vs 골든 답변이 들어 있다. GPU·LLM이 필요 없다.

세 명령 모두 `--out`/`--out-dir`을 생략하면 결과 폴더의 `report/` 안에 저장된다(결과가 한 폴더에 모인다). 네 노트북을 합칠 때만 `--out results/merged`처럼 따로 지정한다. Recall·Hit 계산법은 `RECALL_EXPLAINED.md`에 있다.

## 지켜야 할 것

- `src/`와 `data/`는 고치지 않는다. 정답·`expected_action`·`reference_answer`·근거는 채점·보고에만 쓴다(스크립트가 이미 그렇게 한다).
- 숫자를 만들어 쓰지 않는다. 표에 없는 값은 "확인 불가"로 적는다. 측정하지 못한 값은 0이 아니라 `None`/`-`.
- 공용 Qdrant에 색인하지 않는다(스크립트가 `QDRANT_URL`을 비워 메모리 Qdrant만 쓴다).
- 키·`.env`·`data/`·`results/`의 원자료를 커밋하지 않는다. 문서에 내 PC 경로를 적지 않는다.
- `완료`된 문서의 본문(가설·조건)은 고치지 않는다. 결과가 이상하면 "실패·이상 기록"에 적는다.
- push와 PR은 사람이 시킬 때만 한다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `점검 실패: ...GPU 사용률이 N%` | 다른 GPU 작업을 끈다. 5% 미만에서 시작해야 시간이 흔들리지 않는다 |
| `배터리로 실행 중이다` | 전원을 연결한다(시험이면 `--allow-battery`) |
| `GPU가 기준과 다르다` | 같은 GPU 노트북에서만 돌린다. 다른 GPU면 시간을 다른 노트북과 비교하지 않는다(`--expect-gpu ""`) |
| `CPU 코어 제한을 걸지 못했다` | 보안 프로그램·권한을 확인하거나 `--cpu-cores 24`(제한 없음, 다른 노트북과 같게 맞춘다) |
| `GPU 메모리 상한에서 리랭커가 메모리 부족` | `--gpu-fraction 0.6`으로 올린다(모든 노트북이 같아야 한다) |
| `OPENAI_API_KEY가 없다` | `.env`를 확인한다. 셸의 잘못된 값이 우선하면 `env -u OPENAI_API_KEY ...`로 실행 |
| 답변 단계 `오류 ... 5%를 넘어 저장하지 않는다` | 429·인터넷 문제. 자동으로 병렬을 절반으로 줄여 한 번 더 시도한다. 그래도 안 되면 `--workers`를 12나 6으로 낮춰 같은 명령 재실행 |
| 모델 내려받기 실패 | 인터넷 연결 후 같은 명령. 3번 재시도한다 |
| `먼저 retrieval 단계를 돌려야 한다` | 단계 순서대로 돌린다(`--stages`로 뺐다면 앞 단계부터) |
| GPU torch 설치가 안 됨 | `uv`가 있는지 확인. 없으면 `--device cpu`(시간 측정은 다른 노트북과 비교하지 않는다) |
| 합친 표에 "노트북 사이 환경이 다른 항목" ⚠ | 시간·토큰 비교에 주의한다. 같은 설정으로 다시 돌리는 것을 권한다 |

## 결과 파일 구조

```
results/expNNNN/laptopN/
  env.json              환경(CPU·RAM·GPU·torch·스레드·적용 코어·전원·git 커밋·시작 GPU 사용률)
  usage.json            단계별 소요 시간, 최대 메모리·GPU 사용량, GPU 온도·열 제한 여부
  questions.json        질문 + 골든(reference_answer, 필수 사실, 금지 주장, 근거 quote)
  emb_cache.pkl         문서 임베딩 캐시(결과와 무관, 지워도 됨)
  retrieval/<크기>_<오버랩%>.json   문항·방식별 선별 과정(순위·점수·내부 단계 시간), 상위 청크 본문, 한도·k별 사용 청크, Hit·Recall 3단계
  answers/<크기>_<오버랩%>.json     문항·방식·k·한도별 답변, 상태 일치, 토큰, LLM 시간, 호출 수
  e2e/<크기>_0.json, anchor_start.json, anchor_end.json   전체 시간(검색·문맥·LLM·합계)
  ragas/<방식>_<크기>_<오버랩>_k<k>.json   faithfulness, 채점 토큰
  report/               보고서(아래 명령을 --out 없이 실행하면 여기에 모인다)
    merged.md, merged.json                     합친 표 (merge_grid_results.py)
    cases/<방식>_<크기>_<오버랩>_k<k>.md      사례 보고서 (make_case_report.py)
    questions_md/<방식>_<크기>_<오버랩>_k<k>/   질문별 파일 (export_question_md.py)
```
