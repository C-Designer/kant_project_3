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
| [docs/work-plan.md](docs/work-plan.md) | 역할 분담, 일정, 코드 리뷰·머지, 상호 공유, 발표 준비, Issue·마일스톤 운영 |
| [docs/kickoff/](docs/kickoff/) | 킥오프 자료. clone 후 `docs/kickoff/index.html` 한 파일을 브라우저로 연다(상단 탭으로 7장 이동). 안건 순서 자료, GitHub 초보용 안내, 구조·레포·운영·일정 그림 |
| [Issue](https://github.com/C-Designer/kant_project_3/issues) · [마일스톤](https://github.com/C-Designer/kant_project_3/milestones) | 진행 상황 |
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

**스켈레톤 실행** (Basic 자료를 받은 뒤)

처음에만 `.env.example`을 복사하고 `OPENAI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`를 채운다. 키는 별도로 전달받으며 저장소나 로그에 넣지 않는다. 로컬 Qdrant를 쓸 때는 `QDRANT_URL`을 비워 둔다. 질문을 보내면 OpenAI API 사용료가 발생할 수 있다.

```bash
cp -n .env.example .env                       # 기존 .env를 덮어쓰지 않는다
uv run python -m src.search.index             # 기본 실행은 기존 컬렉션을 재생성한다
uv run uvicorn src.api.main:app               # API 서버
curl -X POST localhost:8000/query -H 'Content-Type: application/json' \
  -d '{"question": "선하증권 초안 메일의 수신 확인은 기재 사항에 대한 승인과 같은가요?", "retrieval_mode": "naive"}'
```

**응답을 받은 뒤 API 서버를 강제 종료하지 않는다.** Langfuse SDK는 트레이스를 5초 간격으로 묶어서 보내고, 정상 종료될 때(Ctrl+C, 스크립트 끝) 남은 것을 마저 보낸다. 응답 직후 프로세스를 kill하거나 터미널 창을 닫으면 이 마지막 전송을 건너뛰어 `generate`·`validate`와 루트 `query`가 유실된다. 이때 Langfuse에는 `retrieve`·`build_context`만 있는 이름 없는 트레이스(Unnamed trace)가 남는다. 응답 후 10초 이상 기다렸다가 서버 터미널에서 Ctrl+C로 종료한다.

색인 전에 PDF가 `data/shipping/documents/`에 있는지 확인한다. 기본 색인은 기존 컬렉션을 지우고 다시 만들므로, 이미 색인이 있다면 백업하고 실행한다. 공유 Qdrant는 API 키가 필수이므로 다른 PC에서는 `QDRANT_URL`과 함께 별도로 전달받은 `QDRANT_API_KEY`를 넣는다. 서버 Mac은 키 없이 인증이 필요한 로컬 프록시로 연결한다. **공유 주소를 넣은 상태에서 색인을 실행하면 공용 컬렉션이 지워지고 다시 만들어지므로**, 공용 색인은 리드와 정한 뒤 서버에서만 다시 만든다.

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

1. [팀 Langfuse](https://kant-langfuse.zerocode-studio.com)에 등록된 Google 계정으로 로그인하고 `shipping-rag` 프로젝트를 연다.
2. 아래 대표 요청을 열어 `/query` 응답의 `request_id`와 트레이스의 `query` 메타데이터가 같은지 확인한다. 트레이스 id는 `request_id`와 다르다. 본인 요청은 `uv run python -c 'from src import config; from src.platform.tracing import trace_id_for; print(trace_id_for("<request_id>"))'`로 얻은 id를 Traces에서 찾는다. 이름이 `query`가 아니라 Unnamed trace이면 응답 직후 서버를 강제 종료한 것이다(위 스켈레톤 실행 절).
3. `retrieve`, `build_context`, `generate`, `validate` 스팬과 모델 입출력·토큰을 확인한다. `retrieve` 출력에서 문맥 축소 전 검색 청크의 본문·점수·출처를, `build_context`에서 최종 문맥을 확인한다. 변경 이전의 트레이스에는 검색 청크 본문이 소급 기록되지 않는다.

대표 실행: [선하증권 초안 수신 확인 질문](https://kant-langfuse.zerocode-studio.com/project/shipping-rag/traces/531cd320c331b48e34166711d33663f3) (`request_id`: `e703290cd63e4328a6e2c3c316b01c0f`, `answered`, SB10 17쪽·SB05 20쪽). 수신 확인과 기재 사항 승인은 다르다는 답변을 두 페이지의 원문과 대조했다. Langfuse에 비용이 0으로 표시되더라도 실제 청구액이 0이라는 뜻은 아니다.

### 공용 서비스 연결 점검 (#40)

레포 루트에서 `.env`를 설정한 뒤 실행한다. 애플리케이션과 같은 Qdrant 클라이언트를 사용하며, 컬렉션 존재 여부와 Langfuse 키 인증만 읽기 전용으로 확인한다. 색인·LLM 호출·평가 점수 생성은 하지 않는다.

```bash
uv run python -m src.platform.check_connections
```

두 서비스가 모두 `ok`이면 종료 코드 0, 하나라도 실패하거나 미설정이면 1이다. `QDRANT_URL`이 비어 있으면 로컬 저장소를 열지 않고 `not_configured`로 표시한다. 로컬 검색이 되더라도 공용 Qdrant 접속이 확인됐다는 뜻은 아니다. `collection_missing`이면 담당자에게 색인 상태를 확인하고, 공유 컬렉션에 기본 색인 명령을 실행하지 않는다. 키와 서버 응답 본문은 출력하지 않는다.

2026-11-08 리드 PC 확인: Langfuse 키 인증 성공, 위 대표 트레이스 조회 HTTP 200, `retrieve`·`build_context`·`generate`·`validate` 존재 및 앞 두 스팬의 출력 기록 확인. 해당 트레이스의 평가 점수는 0개로, `record_score`의 실제 점수 연결 증빙은 아직 없다. 공용 Qdrant는 이 PC의 `QDRANT_URL` 미설정으로 확인하지 못했다.

### Mac Studio 서버 확인과 MacBook 점검 (2026-11-09)

공용 서비스는 리드의 Mac Studio에서 Docker Compose와 Cloudflare Tunnel로 운영한다. 공용 서비스는 Langfuse·Qdrant 두 개다. FastAPI는 각자 로컬에서 띄운다(2026-11-09부터 공용 API 주소는 운영하지 않는다).

| 서비스 | 주소 | 인증 |
|---|---|---|
| Langfuse | https://kant-langfuse.zerocode-studio.com | 화면은 허용된 Google 계정, SDK는 프로젝트 키 |
| Qdrant | https://kant-qdrant.zerocode-studio.com | API 키 |

서버 검증: 컨테이너 실행, 로컬 API `/health` 200, 공용 API 비로그인 요청 302(로그인 필요), 공용 Langfuse health 200. 공용 Qdrant는 키 없이 401, 키를 전달하면 컬렉션 조회 200·572개 청크를 확인했다. 서버의 기존 인증 프록시를 적용한 `uv run python -m src.platform.check_connections`는 두 서비스 모두 `ok`였다. 대표 트레이스의 4개 스팬과 출력도 다시 확인했다. 평가 점수는 아직 0개다. 색인을 재생성하지 않았다.

MacBook에서는 다음 순서로 확인한다.

1. 로컬에서 `uv run uvicorn src.api.main:app`으로 API를 띄우고 `http://127.0.0.1:8000/health`와 `/docs` 화면을 확인한다.
2. Langfuse에 Google 로그인해 `shipping-rag` 프로젝트와 위 대표 트레이스를 연다.
3. 저장소 환경은 `uv sync --locked`로 설치한다. `.env`에 위 Langfuse·Qdrant 주소와 별도로 전달받은 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `QDRANT_API_KEY`를 설정한다. `QDRANT_URL`은 `https://kant-qdrant.zerocode-studio.com:443`처럼 포트까지 적는다(포트가 없으면 Qdrant 클라이언트가 6333에 붙어 timeout). 서버 비밀 파일 전체를 복사하지 않는다.
4. `uv run python -m src.platform.check_connections`로 두 서비스의 `ok`를 확인한다.
5. 생성 API 키도 설정한 뒤 로컬 Naive 1문항을 실행하고 request_id로 4개 스팬을 확인한다. 이름·OS·커밋·시각·결과를 기록한다.

2026-11-09 MacBook 확인(리드, macOS 26.5.1, Python 3.12.14, 커밋 `b8301e0`): 키 없이 Qdrant 401, 키 포함 572개 청크, `check_connections` 두 서비스 `ok`·종료 코드 0. 로컬 Naive 1문항은 `answered`(SB05 20쪽·SB10 17쪽 인용). 응답 직후 서버를 강제 종료한 1차 요청은 Unnamed trace로 `retrieve`·`build_context`만 남았다. 15초 뒤 Ctrl+C로 종료한 2차 요청(`request_id`: `997860c5f0fc477aaa310e246354ce71`, [트레이스](https://kant-langfuse.zerocode-studio.com/project/shipping-rag/traces/c009bdb9fd7ec4353dfbec924b6198c5))은 `query` 아래 4개 스팬과 `generate` 안의 모델 호출이 모두 남았다.

서버 API·터널·Docker는 사용자 로그인 후 시작하도록 등록되어 있다. 절전은 꺼져 있다. 실제 재부팅·정전 복구는 검증하지 않았고 정전 후 자동 재시작은 꺼져 있다. MacBook 접속 확인과 judge의 실제 평가 점수 증빙 전에는 #40을 닫지 않는다.

`src/search/store.py:get_client()`는 원격 연결 시 `config.QDRANT_API_KEY`를 전달한다(search 담당 합의). 키가 없으면 전달하지 않으므로 로컬 모드와 서버 Mac의 프록시 연결은 그대로다. 키 값은 코드·문서·로그에 넣지 않는다.

**팀원에게 확인받을 항목**

| 확인 | 실행·증빙 | 완료 기준 |
|---|---|---|
| 공용 Qdrant 접속 | 인증 지원 반영 후 공유 주소·키를 별도로 전달받아 위 명령 실행 | 본인 PC에서 `qdrant: ok` |
| Langfuse 키·화면 권한 | 위 명령 실행 후 Google 계정으로 `shipping-rag` 프로젝트의 대표 트레이스 열기 | `langfuse: ok` 및 화면 열람 가능 (키 인증과 계정 권한은 별개) |
| 본인 요청 추적 | 위 스켈레톤 실행 절의 API 서버·Naive 질의 실행. 공유 색인은 재생성하지 않음 | 응답의 `request_id`에 4개 스팬·실제 모델 입출력이 보이고, 검색 결과와 최종 문맥을 구분할 수 있음 |
| 평가 점수 연결 (judge 담당, #34) | 실제 평가 후 같은 요청의 점수 확인 | 서비스·평가 트레이스 분리 및 점수 연결 캡처 |

확인 결과는 이름·OS·커밋 해시(`git rev-parse HEAD`)·실행 시각·점검 출력·request_id·캡처로 남긴다. `.env`나 키가 보이는 화면은 공유하지 않는다. 팀원 확인과 Qdrant 인증 연결이 끝나기 전에는 #40을 완료 처리하지 않는다.

## 최종 선택과 한계

미정. 비교 결과는 `results/comparison.md`.

## 팀원별 기여

미정. 제출 전 작성.
