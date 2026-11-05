# kant_project_3

KANT 3차 프로젝트 (proj_3rd): PDF 기반 RAG 질의응답 서비스와 세 가지 검색 방식 비교.

- 제출 **2026-11-13 (금) 13:00**, 당일 오후 발표
- 분야·난이도: **해운 · Basic** (15 PDF). 데이터는 `data/shipping/`에 두고 커밋하지 않는다
- 팀: 김창동(리드·platform), 윤승환(search), 천희재(answer), 오주헌(metrics), 김경민(judge)

## 문서

| 문서 | 내용 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | 발제 요약: 필수 4과제, 데이터 규칙, API 형식, 상태값, 산출물, 완료 기준 |
| [docs/evaluation.md](docs/evaluation.md) | 채점 규칙: Hit@k·Recall@k, RAGAS, Judge 4항목, 해당 없음 처리, 운영 지표, 보안 비교 |
| [docs/work-plan.md](docs/work-plan.md) | 역할 분담, 일정, 코드 리뷰·머지, 상호 공유, 발표 준비, Issue·보드 운영 |
| [docs/kickoff/](docs/kickoff/) | 킥오프 자료. clone 후 `docs/kickoff/index.html` 한 파일을 브라우저로 연다(상단 탭으로 7장 이동). 안건 순서 자료, GitHub 초보용 안내, 구조·레포·운영·일정 그림 |
| [Project 보드](https://github.com/users/C-Designer/projects/1) | 진행 상황. Issue는 [여기](https://github.com/C-Designer/kant_project_3/issues) |
| [docs/branch-strategy.md](docs/branch-strategy.md) | 브랜치·PR 규칙 |
| [docs/documentation.md](docs/documentation.md) | ADR과 spec 규약 |
| [AGENTS.md](AGENTS.md) | 사람·에이전트 공통 작업 규칙 |
| [docs/adr/](docs/adr/) | 설계 결정 (0002 관심사 5분할·뼈대, 0003 스택) |
| [docs/specs/](docs/specs/) | 영역별 현재 동작과 인터페이스 |

## 코드 구조

영역은 레이어가 아니라 관심사로 나눈다 ([ADR 0002](docs/adr/0002-areas-by-concern.md)). 영역 하나당 담당 1명, spec 1개. 영역 간 계약은 `src/contracts.py`, 동결 설정은 `src/config.py`.

| 영역 | 담당 | 책임 | 코드 |
|---|---|---|---|
| `search` | 윤승환 | 검색 품질: 청킹·E5 임베딩·Qdrant 색인, `naive` / `hybrid` / `hybrid_rerank` | `src/search/` |
| `answer` | 천희재 | 답변 품질: 문맥 조립, 프롬프트·판단, gpt-6-luna 호출, 출력 JSON 검증, 출처 매핑 | `src/answer/` |
| `metrics` | 오주헌 | 실험 자동화: 평가 JSON 로더, 질문 선택, 3방식 일괄 실행, Hit/Recall, 운영 지표 집계, 비교표 | `src/metrics/` |
| `judge` | 김경민 | LLM 평가: RAGAS Faithfulness, Judge 4항목, `null` 규칙, 원문 대조·사람 확인 | `src/judge/` |
| `platform` | 김창동 | 재현·관측·운영: 뼈대, FastAPI, `config.py`, LLM 래퍼(timeout·측정), Langfuse, README·재실행, 보안 4개, 시연 | `src/platform/`, `src/api/` |

요청 흐름: `/query` → `platform.run_query()` → `search.retrieve()` → `answer.build_context()` → `answer.generate()`(→ `platform.llm.call()`) → 응답. `metrics`가 같은 `run_query()`를 일괄 호출해 `RunRecord`를 만들고, `judge`가 채점해 `EvalRecord`를 붙이고, `metrics`가 비교표로 합친다. 전 구간이 `request_id` 하나로 Langfuse에 남는다.

짝(서로 변경을 먼저 알려주는 사이): `search`↔`answer`, `metrics`↔`judge`, `platform`↔`metrics`. 리뷰·머지는 리드가 한다.

뼈대(`naive` 1문항 end-to-end + contracts + config)는 리드가 11/5에 머지한다. 그 뒤 각자 자기 영역을 깊이 판다. 에이전트 작업 규칙은 [AGENTS.md](AGENTS.md).

스택: Python, pypdf, LangChain, 로컬 E5, Qdrant, FastAPI, Langfuse, RAGAS. 결정은 [ADR 0003](docs/adr/0003-stack.md).

## 설치·실행

데이터셋은 `data/`에 두고 커밋하지 않는다. 키는 `.env`에만 둔다(`.env.example` 참고).

### Python 환경 (전원 동일, 강제)

Python 버전과 패키지 버전은 레포 파일로 고정돼 있다. **[uv](https://docs.astral.sh/uv/)로만 설치한다.**

| 파일 | 고정하는 것 |
|---|---|
| `.python-version` | Python **3.12**. PC 기본 Python이 3.14여도 uv가 3.12를 받아서 쓴다 |
| `pyproject.toml` | `requires-python = "==3.12.*"`. 다른 버전으로 설치하려 하면 에러로 거부된다 |
| `uv.lock` | 모든 패키지의 정확한 버전. 전원 같은 버전이 깔린다 |

**처음 한 번: uv 설치** (이미 있으면 건너뛴다. `uv --version`으로 확인)

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**설치와 확인** (레포 폴더에서)

```bash
uv sync                                   # .venv 생성, Python 3.12와 고정된 패키지 설치
uv run pytest tests/test_environment.py   # 환경 확인: 4 passed가 나와야 한다
uv run pytest -q                          # 이후 실행은 모두 uv run으로
```

**스켈레톤 실행** (`.env`에 키를 채운 뒤)

```bash
cp .env.example .env                          # 키는 .env에만 둔다
uv run python -m src.search.index             # PDF 색인 (옵션: --only FB01.pdf)
uv run uvicorn src.api.main:app               # API 서버
curl -X POST localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question": "질문", "retrieval_mode": "naive"}'
```

**이미 다른 Python(3.13·3.14 등)으로 가상환경을 만들어 둔 경우**: 레포 안의 `.venv` 폴더를 지우고 `uv sync`를 다시 실행한다. 다른 곳에 만든 venv·conda 환경은 이 프로젝트에 쓰지 않는다. VS Code 등 에디터의 Python 인터프리터도 레포의 `.venv`로 바꾼다.

**에디터나 AI 도구에서 import 오류가 나면** 먼저 `uv run pytest tests/test_environment.py`를 돌린다. 실패하면 환경이 어긋난 것이고, 메시지가 원인을 알려 준다.

- **LangChain은 0.3 계열로 고정한다** (`langchain` 0.3.x, `langchain-core` 1.0 미만). RAGAS 0.4.3이 LangChain 1.x와 맞지 않기 때문이다. 1.x가 필요한 패키지를 `uv add`하면 uv가 설치를 거부한다. 그때는 judge 담당과 먼저 상의한다. 코드는 LangChain 0.3 문서 기준으로 쓰고, 확인된 import 경로는 [AGENTS.md](AGENTS.md)에 있다.
- **이 고정 위에서 설치·동작을 확인한 패키지** (2026-11-05, `uv add`로 추가하면 0.3과 맞는 버전이 자동 선택된다):

  | 영역 | 패키지 (자동 선택된 버전) |
  |---|---|
  | search | `pypdf`, `qdrant-client` 1.20, `langchain-qdrant` 0.2.1, `langchain-huggingface` 0.3.1, `langchain-text-splitters` 0.3.11, `sentence-transformers` 6.2, `rank-bm25`, `fastembed` 0.9 |
  | platform | `fastapi` 0.162, `uvicorn[standard]`, `langfuse` 5.1, `python-dotenv` |
  | metrics | `pandas` 3.1, `tabulate` |

  실제 실행으로 확인한 기능: 프롬프트→모델→파서 연결(LCEL), 청킹과 출처 메타데이터 유지, BM25 검색, Qdrant 저장·검색, hybrid 결합(EnsembleRetriever), FastAPI `/health`, Langfuse LangChain 콜백 import. E5 모델 실제 추론은 다운로드 용량 때문에 확인하지 않았다(설치만 확인).
- **3.14는 쓸 수 없다.** RAGAS 의존성(`scikit-network`)이 3.14에서 빌드에 실패한다. 근거는 [docs/specs/judge.md](docs/specs/judge.md) "실행 환경 제약".
- 패키지를 추가할 때는 `pip install` 대신 `uv add <패키지>`를 쓰고, 바뀐 `pyproject.toml`과 `uv.lock`을 같은 PR에 넣는다. 의존성 변경은 다른 영역에도 영향을 주므로 PR 제목에 `[interface]`를 붙인다.
- `pip install`이나 다른 가상환경으로 따로 설치하지 않는다. 버전이 어긋나 재실행 검증(11/11)에서 실패한다.

### 데이터셋 받기

원본 ZIP은 레포에 넣지 않고 [Releases](https://github.com/C-Designer/kant_project_3/releases)에 난이도별로 둔다 (Notion 원본, 파일명·내용 수정 없음). Basic만 받으면 된다. Intermediate·Advanced는 Basic을 끝내고 여유가 있을 때만 쓴다.

| 태그 | 내용 | ZIP |
|---|---|---|
| `data-basic-v1` | 해운 Basic, PDF 15개 (360쪽) | 2개 |
| `data-intermediate-v1` | 해운 Intermediate, PDF 50개 (3,750쪽) | 4개 |
| `data-advanced-v1` | 해운 Advanced, PDF 120개 (18,000쪽) | 9개 |

```bash
mkdir -p data/shipping && cd data/shipping
gh release download data-basic-v1 -R C-Designer/kant_project_3 -p '*.zip' -p 'SHA256SUMS*'
shasum -a 256 -c SHA256SUMS_Basic.txt
for z in *.zip; do unzip -oq "$z"; done
ls documents | wc -l   # 15
```

- ZIP을 **같은 폴더에 각각** 푼다. 이어붙이지 않는다. 중복된 `evaluation/*.json`은 동일하므로 덮어써도 된다.
- 다른 난이도는 별도 폴더(`data/shipping-intermediate/` 등)에 푼다. 섞지 않는다.
- `gh`가 없으면 Release 페이지에서 직접 받는다.

## Langfuse 확인 방법

미정. 프로젝트·필터·대표 요청 ID를 여기 적는다.

## 최종 선택과 한계

미정. 비교 결과는 `results/comparison.md`.

## 팀원별 기여

미정. 제출 전 작성.
