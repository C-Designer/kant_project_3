# AGENTS.md

사람과 에이전트(Claude Code, Codex 등) 모두에게 적용되는 규칙이다. `CLAUDE.md`는 이 파일을 끌어오기만 한다(`@AGENTS.md`). 규칙은 여기 한 곳에서 고친다.

## 작업 전에 읽는 순서

0. 세션 시작 시 표시된 담당 영역을 따른다. 표시가 없으면 `bash scripts/whoami.sh`를 실행해 확인하고, 그래도 미확인이면 사용자에게 묻는다. 추측하지 않는다. (Claude Code는 `.claude/settings.json`의 SessionStart 훅이 자동으로 표시한다. `gh auth login`이 돼 있어야 한다)
1. [docs/branch-strategy.md](docs/branch-strategy.md): 브랜치·PR 규칙
2. [docs/requirements.md](docs/requirements.md): 무엇을 만들어야 하는지. 발제의 고정 규칙
3. 자기 영역 spec `docs/specs/<영역>.md`와 공용 타입 `src/contracts.py`
4. 채점 관련 작업이면 [docs/evaluation.md](docs/evaluation.md)
5. 문서(spec·ADR)를 새로 만들거나 고치면 [docs/documentation.md](docs/documentation.md): 템플릿, 번호, 같은 PR 규칙

## 지켜야 할 것

- **계약은 `src/contracts.py`.** 영역 간에 주고받는 값은 거기 타입으로만. 타입을 바꾸면 PR 제목에 `[interface]`를 붙이고 의존 영역 담당자 확인을 받는다.
- **동결 설정은 `src/config.py`.** k, 토큰 한도, 모델, timeout 같은 값을 코드에 흩뿌리지 않는다.
- **측정 못 한 값은 `None`.** 0으로 바꾸지 않는다. 집계는 `None`을 분모에서 뺀다.
- **`data/evaluation/`의 정답·근거·기대 동작은 채점에만.** 색인, 검색어, 필터, 생성 프롬프트에 넣지 않는다.
- **LLM 호출은 `platform.llm.call()`을 통해서만.** 직접 SDK를 부르지 않는다(측정·트레이스가 빠진다).
- **키·개인정보·`data/`를 커밋하지 않는다.** 설정은 환경 변수. `.env.example`에는 키 이름만.
- **공용 Qdrant에 색인하지 않는다.** `QDRANT_URL`이 공용 주소일 때 `src.search.index`를 실행하면 공용 컬렉션이 지워지고 다시 만들어진다. 색인 실험은 `QDRANT_URL`을 비운 로컬 모드로 하고, 공용 색인은 리드와 정한 뒤 서버에서만 다시 만든다.
- **API 서버는 응답 후 10초 이상 기다렸다가 Ctrl+C(SIGINT)로 끈다.** `kill -9`나 응답 직후 종료는 마지막 스팬과 루트 `query` 트레이스를 잃는다(`docs/specs/platform.md`).
- **동작이나 구조를 바꾸면 같은 PR에서 spec을 고친다.** 미정 항목을 결정했으면 spec의 "미정"을 지우고 값을 적는다.
- **PR에는 실행 증거.** 명령과 결과(또는 캡처)를 PR 본문에 붙인다. 프롬프트를 바꿨으면 정상·되묻기·보류 1문항씩.
- **테스트는 규칙을 고정하는 용도로만.** `None` 집계, `source_ids` 검증, `book_id` 파생 같은 발제 규칙은 단위 테스트로 잠근다. 커버리지 목표는 없다.
- **실행 환경은 `uv`로 고정된 것만 쓴다.** Python 3.12, 패키지는 `uv.lock`. 설치는 `uv sync`, 실행은 `uv run ...`. `pip install`이나 다른 가상환경을 쓰지 않는다. 패키지 추가는 `uv add <패키지>`로 하고 `pyproject.toml`·`uv.lock`을 같은 PR에 넣는다(제목에 `[interface]`).
- **LangChain은 0.3 계열이다(`langchain` 0.3.x, `langchain-core` 1.0 미만).** RAGAS 0.4.3과 맞추기 위한 고정이다(`docs/specs/judge.md` "실행 환경 제약"). 코드는 **LangChain 0.3 문서 기준**으로 쓴다. 1.x 전용 문법(`langchain_classic`, `langchain.agents.create_agent`, `langchain.messages` 등)은 쓰지 않는다. `uv add`가 1.x를 요구하며 실패하면 버전을 올리지 말고 judge 담당과 먼저 상의한다. 0.3에서 확인된 import 경로:

  | 용도 | import |
  |---|---|
  | 문서·프롬프트·파서 | `from langchain_core.documents import Document`, `from langchain_core.prompts import ChatPromptTemplate`, `from langchain_core.output_parsers import StrOutputParser` |
  | 청킹 | `from langchain_text_splitters import RecursiveCharacterTextSplitter` |
  | 키워드 검색 (BM25) | `from langchain_community.retrievers import BM25Retriever` (`rank-bm25` 필요) |
  | 벡터스토어 | `from langchain_qdrant import QdrantVectorStore` |
  | hybrid 결합 | `from langchain.retrievers import EnsembleRetriever` (1.x의 `langchain_classic` 아님) |
  | 임베딩 (E5) | `from langchain_huggingface import HuggingFaceEmbeddings` |
  | 생성 모델 | `from langchain_openai import ChatOpenAI` |
  | Langfuse 연결 | `from langfuse.langchain import CallbackHandler` |
- 선택 과제(메모리, UI, 고급 RAG)는 구현하지 않는다. 필요하면 Issue로 제안.

## 코드 작성 방식 (ponytail)

[ponytail](https://github.com/DietrichGebert/ponytail)의 "게으른 시니어 개발자" 규칙을 따른다. 가장 좋은 코드는 쓰지 않은 코드다. 문제 전체를 가장 적은 새 코드로 푼다. 위 "지켜야 할 것"과 부딪히면 위 규칙이 이긴다(동결 설정은 `src/config.py`, 계약은 `src/contracts.py`, 단위 테스트는 발제 규칙 고정 용도). ponytail은 그 안에서 가장 작은 변경을 고르는 규칙이다.

**쓰기 전에.** 작업과 그 작업이 건드리는 코드를 읽는다. 변경이 닿아야 하는 곳을 전부 적는다: 호출처, 테스트, 픽스처, 설정, export. 사용자에게 무엇이 깨질 수 있는지 본다: 지워지거나 노출되는 데이터, 멈추는 호출처. 그것이 범위다. 추가 기능은 범위가 아니다.

**가장 작은 완전한 변경.** 완전히 동작하는 첫 번째 선택지를 고른다.

1. 꼭 있어야 하는가? 아무도 요청하지 않은 기능·옵션·유연성은 빼고, 뺐다고 한 줄로 적는다. 막연한 요청("X 만들어줘")에는 핵심만 하는 가장 작은 버전.
2. 이 코드베이스에 이미 있는가(헬퍼, 함수, 패턴)? 주변 코드가 쓰는 방식 그대로 쓴다.
3. 표준 라이브러리나 플랫폼 기능인가? 프로젝트에 자체 것이 없으면 그것을 쓴다.
4. 이미 설치된 의존성인가? 그것을 쓴다. 몇 줄 때문에 의존성을 추가하지 않는다.
5. 한눈에 읽히는 한 줄로 되는가? 한 줄로.
6. 아니면 동작하는 최소한의 코드.

- 해법에는 게으르되 변경 자체에는 게으르지 않는다. 변경이 깨뜨리는 호출처·테스트·픽스처까지 작업에 필요한 모든 부분을 끝낸다.
- 아무도 요청하지 않은 추상화, 래퍼, 타입 변환, 옵션, 설정, 보일러플레이트, "나중을 위한" 코드를 넣지 않는다. 값은 플랫폼이 주는 형태 그대로 둔다. 추가보다 삭제. 코드베이스의 기존 구조(계층, 인터페이스, 관례)를 지킨다.
- 닿아야 할 곳을 다 안 다음에는 가장 짧게 동작하는 diff가 이긴다. 해독이 필요한 한 줄은 짧은 게 아니다.
- 주석은 코드가 보여주지 못하는 "왜"만 한 줄로.
- 버그 수정: 고치기 전에 그 함수의 호출처를 전부 grep하고, 공용 코드에서 근본 원인을 한 번만 고친다.
- 옮기거나 합치는 코드는 에러 처리와 검증을 그대로 가져간다.
- 크기가 같은 선택지 사이에서는 엣지 케이스에 맞는 쪽을 고른다.
- 검증 없는 게으른 코드는 미완성이다. 새 비자명 로직(분기, 반복, 파서, 새 스크립트)에는 작은 assert 자가 점검 하나를 남긴다. 단위 테스트는 위 규칙대로 발제 규칙 고정에만 쓴다. 사소한 변경에는 필요 없다.
- 한계가 있는 지름길에는 `shortcut: <한계>, <언제 올릴지>` 주석을 단다. 나중에 한 번에 모아 본다.

절대 빼지 않는 것: 신뢰 경계의 검증, 데이터 손실을 막는 에러 처리, 보안, 사용자가 요청한 것.

**답변 끝에 한두 줄.** 건너뛴 것·확인 안 한 것, 사용자가 알아야 할 위험. PR 본문 "실행 증거" 옆에도 같이 적는다.

**PR 전 리뷰(선택).** ponytail 플러그인을 설치했다면 PR 올리기 전 `/ponytail-review`로 변경을 한 번 본다. 설치는 Claude Code가 `/plugin marketplace add DietrichGebert/ponytail` 후 `/plugin install ponytail@ponytail`, Codex가 `codex plugin marketplace add DietrichGebert/ponytail` 후 `codex plugin add ponytail@ponytail`. 플러그인은 레벨 전환(`/ponytail lite|full|ultra`)도 준다. 이 섹션의 규칙은 플러그인 없이도 적용된다.

## 에이전트에게

- 작업 시작 시 위 문서를 읽고, spec과 다르게 만들어야 하면 먼저 사람에게 말한다.
- 없는 메타데이터나 출처를 만들지 않는다. 모르면 `None`과 이유.
- 다른 영역 폴더는 읽되 고치지 않는다. 고쳐야 하면 그 영역 담당자에게 Issue나 PR 코멘트로.
- 담당자는 에이전트가 쓴 코드를 발표에서 직접 설명할 수 있어야 한다. 설명 못 할 코드는 머지하지 않는다.
