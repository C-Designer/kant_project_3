# 0005. Python 3.12 · uv · LangChain 0.3으로 실행 환경을 팀 전체에 고정한다

- 상태: 채택
- 날짜: 2026-11-05

## 배경

ADR 0003은 언어를 "Python(강의 환경)"으로만 정하고 가상환경·의존성 관리는 README에 맡겼다. 채점에 쓰는 RAGAS 0.4.3을 붙여 보니 두 가지가 맞지 않았다. RAGAS가 쓰는 `scikit-network`가 Python 3.14에서 빌드되지 않고(많은 PC의 기본 Python이 3.14), 최신 `langchain-community`(0.4.x)에서는 `import ragas`가 실패한다. 사람마다 버전이 다르면 완료 기준인 README 재실행 검증에서 실패한다.

## 결정

- Python **3.12**: `.python-version`, `pyproject.toml`의 `requires-python = "==3.12.*"`.
- 설치·실행은 **uv**만: `uv sync`, `uv run ...`. 정확한 버전은 `uv.lock`. 패키지 추가는 `uv add`로 하고 `pyproject.toml`·`uv.lock`을 같은 PR에(`[interface]`).
- LangChain은 **0.3 계열**(`langchain` 0.3.x, `langchain-core` 1.0 미만, `langchain-community==0.3.27`), RAGAS `0.4.3`. 코드는 LangChain 0.3 문서 기준으로 쓴다(#53).

## 이유와 대안

- 문서로만 안내: 설치 도구가 막지 않으면 누군가는 3.14·1.x로 설치한다. uv와 lock 파일은 잘못된 버전을 설치 단계에서 거부한다.
- LangChain 1.x + RAGAS 대신 다른 평가 도구: 발제가 RAGAS Faithfulness를 지정한다.

## 영향

LangChain 1.x 전용 기능(`langchain_classic`, `langchain.agents.create_agent` 등)은 쓸 수 없다. 버전을 올려야 하면 judge 담당과 먼저 상의한다. 0.3에서 확인된 import 경로는 `AGENTS.md`, 근거는 `docs/specs/judge.md` "실행 환경 제약", 설치 절차는 `README.md`. 환경 확인 테스트 `tests/test_environment.py`.
