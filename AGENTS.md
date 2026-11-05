# AGENTS.md

사람과 에이전트(Claude Code, Codex 등) 모두에게 적용되는 규칙이다. `CLAUDE.md`는 이 파일을 끌어오기만 한다(`@AGENTS.md`). 규칙은 여기 한 곳에서 고친다.

## 작업 전에 읽는 순서

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

## 에이전트에게

- 작업 시작 시 위 문서를 읽고, spec과 다르게 만들어야 하면 먼저 사람에게 말한다.
- 없는 메타데이터나 출처를 만들지 않는다. 모르면 `None`과 이유.
- 다른 영역 폴더는 읽되 고치지 않는다. 고쳐야 하면 그 영역 담당자에게 Issue나 PR 코멘트로.
- 담당자는 에이전트가 쓴 코드를 발표에서 직접 설명할 수 있어야 한다. 설명 못 할 코드는 머지하지 않는다.
