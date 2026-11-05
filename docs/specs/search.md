# search spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 윤승환. 짝: `answer`(조각을 넘김).

## 범위

- 책임: 검색 품질 전체. `documents/*.pdf` 전부를 출처가 보존된 청크로 만들어 Qdrant에 색인하고, `naive` / `hybrid` / `hybrid_rerank` 세 방식으로 상위 `k`개를 돌려준다. 누락·실패 리포트. 청킹과 검색 방식을 함께 조정한다.
- 책임 아님: 청크를 프롬프트에 넣는 방법과 문맥 길이(`answer`), 지표 계산(`metrics`), `evaluation/` JSON(절대 색인하지 않는다).

## 동작

뼈대(11/6)에 `naive` + 단순 청킹이 들어 있다. 담당자가 아래 미정을 채우며 깊이 판다.

색인
- 데이터 위치 `data/shipping/documents/*.pdf` (git 제외).
- `pypdf` 페이지 단위 추출, 첫 페이지 = 1.
- 청킹: 크기·overlap 미정. 표는 행·열 제목, 단위, 각주를 같은 청크에. 대상·적용일·단위·출처가 끊기지 않게.
- 임베딩: 로컬 E5 계열, 모델명·차원 미정. 질의 임베딩도 같은 모델.
- Qdrant 컬렉션: 이름, 거리 함수, sparse 벡터 포함 여부 미정.
- 명령 `python -m src.search.index --dataset data/shipping` (예시). 결과 `data/shipping/ingest-report.json`(문서 수, 페이지 수, 청크 수, 실패 파일과 이유).

검색

| 방식 | 처리 | 미정 |
|---|---|---|
| `naive` | dense 상위 k | - |
| `hybrid` | dense + 키워드(BM25 계열 / Qdrant sparse) 결합 | 키워드 방식, 결합(RRF 등)과 가중치 |
| `hybrid_rerank` | `hybrid` 후보 N개를 로컬 리랭커로 재정렬 후 상위 k | 리랭커 모델, N |

- 세 방식은 같은 컬렉션·같은 임베딩. `k`는 호출자가 넘기고 최종 비교에서는 동일.
- 정답 JSON의 근거 목록을 필터나 검색어로 쓰지 않는다.
- 검색 호출은 `platform.tracing.span("retrieve")`로 감싼다(방식, k, chunk_id 목록, 소요 시간).

코드 위치: `src/search/` (`index.py`, `chunking.py`, `embed.py`, `retrieve.py`)

## 인터페이스

`src/contracts.py`의 타입을 쓴다.

```python
class ChunkMeta(BaseModel):
    book_id: str        # 파일명에서 .pdf 뺀 값
    file_name: str
    page: int           # 1부터
    chunk_id: str       # "<book_id>-p<page>-c<n>", 컬렉션 안에서 유일

class RetrievedChunk(BaseModel):
    text: str
    score: float
    metadata: ChunkMeta

RetrievalMode = Literal["naive", "hybrid", "hybrid_rerank"]

def retrieve(query: str, mode: RetrievalMode, k: int) -> list[RetrievedChunk]
```

- 점수 내림차순, 최대 `k`개. 결과 없으면 빈 목록(예외 아님). 지원하지 않는 `mode`는 `ValueError`.
- 원문에 없는 메타데이터를 만들지 않는다.

## 관련 ADR

- 0001, 0002, 0003
