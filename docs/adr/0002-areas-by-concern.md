# 0002. 작업 영역을 레이어가 아니라 관심사 네 개로 나누고, 공용 뼈대 위에서 깊이 판다

- 상태: 채택
- 날짜: 2026-11-05

## 배경

ADR 0001과 함께 만든 영역(`ingestion`, `retrieval`, `agent`, `masking`, `observability`)은 발제를 읽기 전, 사람이 코드를 쓰는 속도가 병목이라는 전제로 잡은 레이어 분할이다. 두 가지가 바뀌었다.

- 발제([docs/requirements.md](../requirements.md))를 확인하니 `masking`은 "개인정보 없으면 해당 없음"이라 필수가 아니고, `agent`의 도구 호출·메모리는 선택이며, 정작 필수 과제 4(평가)를 맡는 영역이 없다.
- 팀원 4명 전원이 Claude Code·Codex 같은 에이전트 도구로 개발한다. 코드 양은 병목이 아니다. 병목은 (1) 네 사람의 에이전트가 서로 다른 컨벤션으로 짠 코드의 통합, (2) 청킹·프롬프트 판단·지표 정의 같은 품질 판단이다. 레이어로 나누면 각자 반나절 만에 자기 레이어를 끝내고 통합에서 막힌다.

## 결정

1. **뼈대를 먼저 하나 만든다.** 리드가 11/5 저녁~11/6 오전에 Claude Code로 `naive` 1문항 end-to-end(PDF 1개 색인 → 검색 → 생성 → 출처 → Langfuse)와 공용 계약 `src/contracts.py`(Pydantic), 공용 설정 `src/config.py`를 만들어 머지한다. 리드의 구현은 이것 하나로 끝낸다.
2. **영역은 관심사 네 개.** 실무 4명이 하나씩 맡아 뼈대 위에서 깊이 판다.

| 영역 | 책임 | 코드 | 발제 과제 |
|---|---|---|---|
| `search` | 검색 품질. 청킹·임베딩·색인과 `naive` / `hybrid` / `hybrid_rerank` 세 방식. 청킹과 검색은 같이 돌려봐야 품질이 나오므로 한 사람 | `src/search/` | 1, 2 |
| `answer` | 답변 품질. 문맥 조립(자료 ID, 토큰 한도), 프롬프트와 판단 순서, LLM 호출 체인, 출력 JSON 검증, 자료 ID → 출처 매핑, 되묻기·보류 | `src/answer/` | 1, 3 |
| `evaluation` | 질문 선택, 세 방식 일괄 실행, Hit@k·Recall@k, RAGAS, Judge, 운영 지표 집계, 비교표 | `src/evaluation/` | 4 |
| `platform` | 재현·관측·운영. FastAPI 라우터와 오류 응답, `config.py`(동결 설정), Langfuse 트레이스, 응답 시간·토큰 측정, timeout·재시도, `.env`·README·교차 재실행, 보안 비교 4개, 발표 시연 | `src/platform/`, `src/api/`, `src/evaluation/security.py` | 3, 4 |

3. **공용 계약은 코드다.** 영역 간 인터페이스는 `src/contracts.py`의 타입으로 고정한다. spec의 "인터페이스" 절은 그 타입을 설명한다. 바꾸려면 `[interface]` PR로 의존 영역 담당자 확인을 받는다.
4. **AI 에이전트 규약**은 `AGENTS.md`에 둔다. 각자의 에이전트가 작업 전에 읽을 문서 순서와 금지 사항을 적는다.

## 이유와 대안

- 레이어 분할 유지: 폴더와 1:1이라 단순하지만 11/7까지 아무도 end-to-end를 못 돌리고, 청킹(ingestion)과 검색(retrieval)을 다른 사람이 들면 검색 품질 튜닝 루프가 두 사람에 걸친다.
- 검색 방식별 분할(naive/hybrid/rerank를 한 사람씩): 서비스 코드가 세 벌이 되고 발제의 "공통 설정" 조건을 지키기 어렵다.
- 리드가 뼈대를 만들지 않고 팀원에게: 발제·레포 컨텍스트가 가장 많은 사람이 반나절에 끝내는 것이 가장 싸다. 리드의 실무는 이 한 번으로 제한한다.

## 영향

`masking`, `ingestion`, `retrieval`, `service`, `observability` spec과 폴더를 지우고 네 영역으로 다시 만든다. 뼈대가 11/6 오전까지 머지되지 않으면 각자 mock으로 시작하고, 뼈대 머지 후 리베이스한다. 관련 spec: `docs/specs/{search,answer,evaluation,platform}.md`, 공용 계약 `src/contracts.py`.
