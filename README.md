# kant_project_3
KANT 3차 프로젝트 (proj_3rd)

## 코드 구조

영역 하나당 `src/<영역>/` 폴더와 `docs/specs/<영역>.md` spec이 1:1로 대응한다. 영역을 맡으면 spec부터 채운다 (`docs/documentation.md`).

| 영역 | 역할 |
|---|---|
| `ingestion` | 데이터셋 청킹·임베딩·벡터스토어 적재 |
| `retrieval` | 질의로 관련 청크 검색 |
| `agent` | 컨텍스트 조립, 도구 호출 루프, LLM 호출 |
| `masking` | LLM API 호출 직전 개인정보 마스킹·복원 |
| `observability` | Langfuse 트레이싱·평가 |

요청 흐름: 사용자 → `agent` → `retrieval` → `agent`(컨텍스트 조립) → `masking` → LLM API. `observability`가 전 구간을 트레이스한다.

언어·프레임워크·벡터스토어는 미정이며 결정되면 ADR로 기록한다.
