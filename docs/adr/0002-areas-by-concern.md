# 0002. 작업 영역을 레이어가 아니라 관심사 다섯 개로 나누고, 공용 뼈대 위에서 깊이 판다

- 상태: 채택
- 날짜: 2026-11-05

## 배경

ADR 0001과 함께 만든 영역(`ingestion`, `retrieval`, `agent`, `masking`, `observability`)은 발제를 읽기 전, 사람이 코드를 쓰는 속도가 병목이라는 전제로 잡은 레이어 분할이다. 두 가지가 바뀌었다.

- 발제([docs/requirements.md](../requirements.md))를 확인하니 `masking`은 "개인정보 없으면 해당 없음"이라 필수가 아니고, `agent`의 도구 호출·메모리는 선택이며, 정작 필수 과제 4(평가)를 맡는 영역이 없다.
- 팀원 5명 전원이 Claude Code·Codex 같은 에이전트 도구로 개발한다. 코드 양은 병목이 아니다. 병목은 (1) 네 사람의 에이전트가 서로 다른 컨벤션으로 짠 코드의 통합, (2) 청킹·프롬프트 판단·지표 정의 같은 품질 판단이다. 레이어로 나누면 각자 반나절 만에 자기 레이어를 끝내고 통합에서 막힌다.

## 결정

1. **뼈대를 먼저 하나 만든다.** 리드가 11/5 저녁~11/6 오전에 Claude Code로 `naive` 1문항 end-to-end(PDF 1개 색인 → 검색 → 생성 → 출처 → Langfuse)와 공용 계약 `src/contracts.py`(Pydantic), 공용 설정 `src/config.py`를 만들어 머지한다.
2. **영역은 관심사 다섯 개.** 5명이 하나씩 맡아 뼈대 위에서 깊이 판다. 리드는 `platform`을 맡는다. 담당은 2026-11-05 Slack `proj_3rd` 투표로 정했다.

| 영역 | 담당 | 책임 | 코드 | 발제 과제 |
|---|---|---|---|---|
| `search` | 윤승환 | 검색 품질. 청킹·임베딩·색인과 `naive` / `hybrid` / `hybrid_rerank` 세 방식. 청킹과 검색은 같이 돌려봐야 품질이 나오므로 한 사람 | `src/search/` | 1, 2 |
| `answer` | 천희재 | 답변 품질. 문맥 조립(자료 ID, 토큰 한도), 프롬프트와 판단 순서, LLM 호출 체인, 출력 JSON 검증, 자료 ID → 출처 매핑, 되묻기·보류 | `src/answer/` | 1, 3 |
| `metrics` | 오주헌 | 실험 자동화. 평가 JSON 로더, 질문 선택, 질문 × 3방식 일괄 실행 러너, Hit@k·Recall@k, 응답 시간·토큰·오류율 집계, 비교표 생성 | `src/metrics/` | 4 |
| `judge` | 김경민 | LLM 평가. RAGAS Faithfulness, Judge 4항목 채점 프롬프트·파싱, 해당 없음/평가 불가 `null` 규칙, 대표 사례 원문 대조와 사람 확인 기록 | `src/judge/` | 4 |
| `platform` | 김창동 | 재현·관측·운영. FastAPI 라우터와 오류 응답, `config.py`(동결 설정), Langfuse 트레이스, 응답 시간·토큰 측정, timeout·재시도, `.env`·README·교차 재실행, 보안 비교 4개, 발표 시연 | `src/platform/`, `src/api/`, `src/platform/security.py` | 3, 4 |

평가를 `metrics`와 `judge`로 나눈 이유: 둘 다 발제 과제 4이지만 성격이 다르다. `metrics`는 실행·집계 자동화(러너, 검색 지표, 운영 지표, 표)이고 `judge`는 LLM 채점의 규칙 준수(RAGAS 입력, 4항목 프롬프트, `null` 처리, 사람 대조)다. 한 사람이 들기엔 가장 큰 덩어리였고, 5번째 인원이 생겨 나눌 수 있었다.

3. **공용 계약은 코드다.** 영역 간 인터페이스는 `src/contracts.py`의 타입으로 고정한다. spec의 "인터페이스" 절은 그 타입을 설명한다. 바꾸려면 `[interface]` PR로 의존 영역 담당자 확인을 받는다.
4. **AI 에이전트 규약**은 `AGENTS.md`에 둔다. 각자의 에이전트가 작업 전에 읽을 문서 순서와 금지 사항을 적는다.

## 이유와 대안

- 레이어 분할 유지: 폴더와 1:1이라 단순하지만 11/7까지 아무도 end-to-end를 못 돌리고, 청킹(ingestion)과 검색(retrieval)을 다른 사람이 들면 검색 품질 튜닝 루프가 두 사람에 걸친다.
- 검색 방식별 분할(naive/hybrid/rerank를 한 사람씩): 서비스 코드가 세 벌이 되고 발제의 "공통 설정" 조건을 지키기 어렵다.
- 리드가 뼈대를 만들지 않고 팀원에게: 발제·레포 컨텍스트가 가장 많은 사람이 반나절에 끝내는 것이 가장 싸다. 뼈대의 대부분이 `platform` 코드(API, config, 래퍼, 트레이스)이므로 리드가 `platform`을 이어 맡는 것이 자연스럽다.
- 리드가 실무를 전혀 맡지 않기: 5영역 중 `platform`은 뼈대와 겹치고 리뷰·머지 전담과도 충돌하지 않는다(자기 PR은 룰셋 우회로 머지).

## 영향

`masking`, `ingestion`, `retrieval`, `service`, `observability` spec과 폴더를 지우고 다섯 영역으로 다시 만든다. 뼈대가 11/6 오전까지 머지되지 않으면 각자 mock으로 시작하고, 뼈대 머지 후 리베이스한다. 관련 spec: `docs/specs/{search,answer,metrics,judge,platform}.md`, 공용 계약 `src/contracts.py`.

흐름: 질문 → `platform.run_query()` → `search`가 조각을 꺼냄 → `answer`가 답을 씀 → `platform`이 기록. `metrics`가 `run_query()`를 일괄 호출해 `RunRecord`를 만들고, `judge`가 채점해 `EvalRecord`를 붙이고, `metrics`가 비교표로 합친다.
