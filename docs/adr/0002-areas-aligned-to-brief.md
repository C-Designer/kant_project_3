# 0002. 작업 영역을 발제의 필수 과제에 맞춰 다섯 개로 재편한다

- 상태: 채택
- 날짜: 2026-11-05

## 배경

ADR 0001과 함께 만든 영역(`ingestion`, `retrieval`, `agent`, `masking`, `observability`)은 발제를 읽기 전에 잡은 것이다. 발제([docs/requirements.md](../requirements.md))를 확인하니 두 군데가 어긋난다.

- `masking`: 발제는 "개인정보가 있다면 처리 범위를 확인하고 없으면 해당 없음"이라고만 한다. 교육용 가상 자료이므로 별도 영역으로 둘 근거가 없다.
- `agent`의 "도구 호출 루프"와 대화 메모리는 선택 사항이다. 반면 필수 과제 4(평가: Hit@k·Recall@k, RAGAS, LLM-as-a-Judge, 보안 비교, 운영 지표)를 맡는 영역이 없다.

## 결정

영역을 아래 다섯 개로 고정한다. `src/<영역>/`과 `docs/specs/<영역>.md`가 1:1로 대응한다.

| 영역 | 책임 | 발제 과제 |
|---|---|---|
| `ingestion` | PDF → 텍스트·출처 추출 → 청킹 → 임베딩 → 색인. 누락·실패 기록 | 1 |
| `retrieval` | `naive` / `hybrid` / `hybrid_rerank` 세 검색 방식. 공통 `k` | 2 |
| `service` | FastAPI `/health`·`/query`, 프롬프트, LLM 호출, 출력 JSON 검증, 자료 ID → 출처 매핑, 상태·오류 처리 | 1, 3 |
| `evaluation` | 질문 선택, 세 방식 일괄 실행, 검색 지표, RAGAS, Judge, 보안 4개, 운영 지표 집계, 비교표 | 4 |
| `observability` | Langfuse 트레이스(요청 ID로 질문·검색·문맥·모델 입출력·시간·토큰 연결), JSONL 보조 기록 | 3, 4 |

- `masking`은 삭제한다. 개인정보 처리 범위는 `service` spec에 "해당 없음" 여부를 한 줄로 남긴다.
- `agent`는 `service`로 이름을 바꾼다. 도구 호출·대화 메모리는 범위에서 뺀다. 필요해지면 선택 과제로 새 ADR.

## 이유와 대안

- 기존 유지 + `evaluation`만 추가: 빈 `masking`이 남고 `agent` 이름이 실제 책임(API + 프롬프트)과 어긋나 신규 팀원이 헷갈린다.
- `evaluation`을 `observability`에 합치기: Langfuse 연동은 하루 작업이고 평가는 가장 큰 덩어리라 한 사람이 들기 어렵다. 분리해야 병렬이 된다.
- `retrieval`을 `ingestion`에 합치기: 같은 벡터스토어를 쓰지만 세 방식 구현이 별도 작업량이다. 담당을 나눌 수 있도록 분리한다.

## 영향

`docs/specs/masking.md`, `src/masking/`을 삭제하고 `agent` → `service`로 옮긴다. `docs/specs/evaluation.md`, `src/evaluation/`을 만든다. 영역 간 인터페이스는 각 spec의 "인터페이스" 절에 고정하며, 이 ADR 이후 바꾸려면 PR에서 의존 영역 담당자 확인을 받는다. 관련 spec: `docs/specs/*.md`.
