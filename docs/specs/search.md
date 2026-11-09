# search spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 윤승환. 짝: `answer`(조각을 넘김).

## 범위

- 책임: 검색 품질 전체. `documents/*.pdf` 전부를 출처가 보존된 청크로 만들어 Qdrant에 색인하고, `naive` / `hybrid` / `hybrid_rerank` 세 방식으로 상위 `k`개를 돌려준다. 누락·실패 리포트. 청킹과 검색 방식을 함께 조정한다.
- 책임 아님: 청크를 프롬프트에 넣는 방법과 문맥 길이(`answer`), 지표 계산(`metrics`), `evaluation/` JSON(절대 색인하지 않는다).

## 동작

뼈대(11/5)에 `naive` + 단순 청킹이 들어 있다. 담당자가 아래 미정을 채우며 깊이 판다.

색인
- 데이터 위치 `data/shipping/documents/*.pdf` (git 제외).
- `pypdf` 페이지 단위 추출, 첫 페이지 = 1.
- 청킹 (`src/search/chunking.py`의 `chunk_pdf`, Basic 기준). 아래 "현재 구현"은 검증 전의 잠정 값이다.
  - 현재 구현
    - 단위: **한 쪽 = 청크 하나**, overlap 없음. Basic PDF 15개, 360쪽 → 청크 360개, 길이 최소 604 / 평균 916 / 최대 1209자.
    - 쪽 구조는 360쪽 전부 같다: 머리말 `<book_id> | <담당 부서>`, 문서 제목, 소제목 1줄, 본문, 꼬리말 `N / 전체쪽수`.
    - 청크 텍스트는 `문서 제목 (담당: 부서)` / 소제목 / 본문 순서다. `<book_id>` 머리말과 꼬리말은 뺀다(출처는 `ChunkMeta`가 따로 가진다). `include_doc_context=False`로 첫 줄(제목·부서)을 뺄 수 있고 기본값은 `True`다.
    - 본문의 줄바꿈은 모두 지운다. PDF 줄 꺾임이 단어 중간에서도 생겨("대\n수") 키워드 검색이 못 찾기 때문이다. 단어 사이의 꺾임은 붙게 되므로("예약을\n신청") 키워드 검색은 글자 단위 비교를 전제한다.
    - 구조가 위와 다른 쪽은 글을 버리지 않고 줄바꿈만 지운 원문을 쓴다. Intermediate·Advanced는 구조가 달라 이 규칙을 아직 적용하지 않는다.
    - `chunk_id`는 쪽당 청크가 하나라 항상 `-c1`이다.
  - 확인한 것
    - Basic에는 표가 없다: 360쪽 모두 표를 그리는 선·사각형이 없고, 대표로 `SB01` 16쪽을 열어 문단 글임을 확인했다.
    - 정정 공지 문서 `SB11`은 24쪽 모두 문장 부호로 끝나고 쪽마다 소제목이 달라, 쪽 경계에서 문장이 끊기지 않는다. 핵심 정정은 1~4쪽, 5~24쪽은 처리 예시와 상담 사례다.
  - 미정 (검증 전)
    - 제목·부서를 붙일지(`include_doc_context`): 같은 문서의 쪽들이 서로 비슷해져 상위 `k`가 한 문서로 채워지면 Recall@k가 떨어질 수 있다. 켬/끔을 Hit@k·Recall@k로 비교해 정한다.
    - 줄바꿈 제거가 맞는지: 같은 방식으로 Hit@k·Recall@k로 확인한다.
    - ~~청크 길이~~ 확정: 한 청크 최대 `config.CHUNK_SIZE`=900자, 겹침 `config.CHUNK_OVERLAP`=0. 쪽이 900자를 넘으면 문장 끝에서 균등 분할한다(`chunk_id`의 `c<n>`이 늘어난다). Basic은 글자÷토큰이 평균 1.93이라 E5의 512토큰 안이다. 300~1300자·겹침 50~200 비교에서 이긴 값이 없었다.
- 임베딩: 로컬 E5 계열, 모델명·차원 미정. 질의 임베딩도 같은 모델.
- Qdrant 컬렉션: 이름, 거리 함수, sparse 벡터 포함 여부 미정.
- 명령 `uv run python -m src.search.index [--only FB01.pdf]`. Qdrant는 `QDRANT_URL`이 있으면 서버, 없으면 `data/qdrant` 로컬 폴더(프로세스당 클라이언트 1개). 결과 `data/shipping/ingest-report.json`(문서 수, 페이지 수, 청크 수, 실패 파일과 이유).

검색

| 방식 | 처리 | 미정 |
|---|---|---|
| `naive` | dense 상위 k | - |
| `hybrid` | dense 상위 `POOL`=20개 + BM25 상위 20개를 RRF(`HYBRID_FUSION`="rrf", 상수 60, 무게 1:1)로 합침. BM25는 2-gram 토큰, k1 1.5·b 0.75 | 청킹이 줄바꿈을 지워 단어가 붙어 있으므로 키워드 비교는 글자 단위(n-gram). 상수·POOL은 `retrieve.py`에 있다 |
| `hybrid_rerank` | `hybrid` 후보 `config.RERANK_CANDIDATES`=20개를 `config.RERANKER_MODEL`(`BAAI/bge-reranker-v2-m3`)로 재정렬 후 상위 k | - |

- 세 방식은 같은 컬렉션·같은 임베딩. `k`는 호출자가 넘기고 최종 비교에서는 동일.
- 정답 JSON의 근거 목록을 필터나 검색어로 쓰지 않는다.
- 검색 호출은 `platform.tracing.span("retrieve")`로 감싼다. 출력에 문맥 축소 전 검색 청크의 본문·점수·메타데이터를 남기고, 메타데이터에 방식·k·chunk_id 목록·소요 시간을 남긴다.

상태: 세 방식 모두 동작(#68·#71). 컬렉션이 없으면 `IndexNotFound`. 청크는 페이지를 넘지 않고 글자 수 기준. Basic·개발용 28문항 비교에서 임베딩(E5 small), 리랭커(bge-reranker-v2-m3), 후보 수(20), hybrid 설정 모두 대안이 이기지 못해 유지했다.

코드 위치: `src/search/` (`index.py`, `chunking.py`, `embed.py`, `store.py`, `retrieve.py`)

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
