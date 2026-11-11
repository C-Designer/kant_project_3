# search spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

담당: 윤승환. 짝: `answer`(조각을 넘김).

## 범위

- 책임: 검색 품질 전체. `documents/*.pdf` 전부를 출처가 보존된 청크로 만들어 Qdrant에 색인하고, `naive` / `hybrid` / `hybrid_rerank` 세 방식으로 상위 `k`개를 돌려준다. 누락·실패 리포트. 청킹과 검색 방식을 함께 조정한다.
- 책임 아님: 청크를 프롬프트에 넣는 방법과 문맥 길이(`answer`), 지표 계산(`metrics`), `evaluation/` JSON(절대 색인하지 않는다).

## 동작

세 방식 모두 동작한다(#68·#71, 아래 "상태"). 2026-11-10 동결(#41): 아래 값과 현재 구현으로 확정한다.

색인
- 데이터 위치 `data/shipping/documents/*.pdf` (git 제외).
- `pypdf` 페이지 단위 추출, 첫 페이지 = 1.
- 청킹 (`src/search/chunking.py`의 `extract_pages` → `chunk_pages`, Basic 기준). 청크 길이와 아래 처리 방식은 확정이다.
  - 현재 구현
    - 단위: 쪽이 `config.CHUNK_SIZE`(900자) 이하면 **한 쪽 = 청크 하나**, 넘으면 문장 끝에서 균등 분할하고 나눈 조각마다 머리 줄(제목·부서, 소제목)을 다시 붙인다. overlap 없음. 청크는 쪽을 넘지 않는다. Basic PDF 15개, 360쪽(정리한 쪽 길이 최소 604 / 평균 916 / 최대 1209자) → 청크 572개(2026-11-09 공용 컬렉션 확인).
    - 쪽 구조는 360쪽 전부 같다: 머리말 `<book_id> | <담당 부서>`, 문서 제목, 소제목 1줄, 본문, 꼬리말 `N / 전체쪽수`.
    - 청크 텍스트는 `문서 제목 (담당: 부서)` / 소제목 / 본문 순서다. `<book_id>` 머리말과 꼬리말은 뺀다(출처는 `ChunkMeta`가 따로 가진다). `include_doc_context=False`로 첫 줄(제목·부서)을 뺄 수 있고 기본값은 `True`다.
    - 본문의 줄바꿈은 모두 지운다. PDF 줄 꺾임이 단어 중간에서도 생겨("대\n수") 키워드 검색이 못 찾기 때문이다. 단어 사이의 꺾임은 붙게 되므로("예약을\n신청") 키워드 검색은 글자 단위 비교를 전제한다.
    - 구조가 위와 다른 쪽은 글을 버리지 않고 줄바꿈만 지운 원문을 쓴다. Intermediate·Advanced는 구조가 달라 이 규칙을 아직 적용하지 않는다.
    - `chunk_id`는 `<book_id>-p<쪽>-c<n>`. 나누지 않은 쪽은 `-c1`뿐이고, 나눈 쪽은 `-c1`, `-c2`, …
  - 확인한 것
    - Basic에는 표가 없다: 360쪽 모두 표를 그리는 선·사각형이 없고, 대표로 `SB01` 16쪽을 열어 문단 글임을 확인했다.
    - 정정 공지 문서 `SB11`은 24쪽 모두 문장 부호로 끝나고 쪽마다 소제목이 달라, 쪽 경계에서 문장이 끊기지 않는다. 핵심 정정은 1~4쪽, 5~24쪽은 처리 예시와 상담 사례다.
  - 확정 (2026-11-10 동결, #41)
    - 제목·부서를 붙인다(`include_doc_context=True`, 현재 구현). 끔과의 Hit@k·Recall@k 비교는 하지 않았다. 한계: 같은 문서의 쪽들이 서로 비슷해져 상위 `k`가 한 문서로 채워질 수 있다.
    - 줄바꿈을 지운다(현재 구현). 남기는 쪽과의 비교는 하지 않았다.
    - 청크 길이: 한 청크 최대 `config.CHUNK_SIZE`=900자, 겹침 `config.CHUNK_OVERLAP`=0. 쪽이 900자를 넘으면 문장 끝에서 균등 분할한다(`chunk_id`의 `c<n>`이 늘어난다). Basic은 글자÷토큰이 평균 1.93이라 E5의 512토큰 안이다. 300~1300자·겹침 50~200 비교에서 이긴 값이 없었다.
- 임베딩: 지금 `config.EMBEDDING_MODEL` = `intfloat/multilingual-e5-small`(384차원, 확정 #14, 2026-11-10 동결). 질의 임베딩도 같은 모델. 개발용 28문항 비교에서 대안이 이기지 못했다(아래 "상태").
- Qdrant 컬렉션: 이름 `config.COLLECTION` = `shipping_basic`. 데이터셋(난이도)마다 컬렉션을 따로 둔다(`shipping_<난이도>`): 한 컬렉션에 섞으면 재색인이 다른 데이터셋을 지우고, 검색과 BM25 통계가 섞인다(#97). dense 벡터 하나·코사인 거리. sparse 벡터는 넣지 않는다. BM25는 `keyword.py`가 컬렉션의 청크 글을 읽어 메모리에 만든다.
- 명령 `uv run python -m src.search.index [--only FB01.pdf]`. Qdrant는 `QDRANT_URL`이 있으면 서버(`QDRANT_API_KEY`가 있으면 함께 전달), 없으면 `data/shipping/qdrant` 로컬 폴더(`config.QDRANT_PATH`, 프로세스당 클라이언트 1개). 기본 실행은 컬렉션을 지우고 다시 만들므로 공용 Qdrant 주소로는 실행하지 않는다. 공용 색인은 리드와 정한 뒤 서버에서만 다시 만든다(AGENTS.md). 결과 `data/shipping/ingest-report.json`(문서 수, 페이지 수, 청크 수, 실패 파일과 이유).

검색

| 방식 | 처리 | 비고 |
|---|---|---|
| `naive` | dense 상위 k | - |
| `hybrid` | dense 상위 `POOL`=20개 + BM25 상위 20개를 RRF(`HYBRID_FUSION`="rrf", 상수 60, 무게 1:1)로 합침. BM25는 2-gram 토큰, k1 1.5·b 0.75 | 청킹이 줄바꿈을 지워 단어가 붙어 있으므로 키워드 비교는 글자 단위(n-gram). 상수·POOL은 `retrieve.py`에 있다 |
| `hybrid_rerank` | `hybrid` 후보 `config.RERANK_CANDIDATES`=20개를 `config.RERANKER_MODEL`(`BAAI/bge-reranker-v2-m3`)로 재정렬 후 상위 k | - |
| `hybrid_rerank_subq` (#125) | LLM이 질문을 하위 질문(최대 `config.SUBQ_MAX`=4개)으로 나눈다. 하위 질문마다 hybrid(E5·BM25 각 상위 `config.SUBQ_CANDIDATES`=50개 RRF)로 후보를 뽑고 하위 질문들의 후보를 RRF로 합쳐 50개를 남긴다. 그 후보 전체를 하위 질문마다 따로 리랭크한 순위의 1위, 2위, …를 번갈아 담아(이미 담은 청크는 건너뜀) k개 | 분해 프롬프트(현재 `subq.SYSTEM`, 강화안은 시험 중) |

- 방식은 모두 같은 컬렉션·같은 임베딩. `k`는 호출자가 넘기고 최종 비교에서는 동일.
- `hybrid_rerank_subq` 세부: 하위 질문이 2개 미만이거나 분해가 실패(LLM 오류·형식 오류)하면 원래 질문 하나로 같은 경로를 탄다(후보 50개를 원래 질문으로 리랭크). LLM은 `platform.llm.call`로 질문당 1회 부르며(질문 글만 입력) 요청 토큰·시간에 합산된다. 비용은 리랭크가 하위 질문 수만큼 늘어난다(분석 Advanced 60문항, GPU, 메모리 Qdrant: 검색 중앙값 `hybrid_rerank` 1.6초, 이 방식 10.8초, 하위 질문 만들기 LLM 약 3.3초 별도). 효과는 이슈 #125와 `search-notes`의 5.58~5.60(분석 전용): Basic 충분 문항 k=5 46→53, Advanced 35→40, Intermediate 42→43(판정 gpt-6-luna). 선정은 문항 집합이 같은 분석 결과라 새 문항에서의 일반화는 확인하지 못했다.
- `hybrid_rerank` 소요 시간(질문당, 리랭크 단계만, Basic 개발용 28문항, 후보 20개): CPU 약 6~8초, GPU(RTX 5060 Laptop) 약 1.0초. 후보 수에 거의 비례한다(후보 50개면 CPU 11.8초, GPU 약 2.5초). 느려서 작은 모델로 바꾸는 안은 5종 비교에서 이긴 모델이 없어 두지 않았다.
- 공용 Qdrant 호출(`collection_exists`, `query_points`, BM25 구축의 `scroll`)은 `store.call`로 감싼다. 한 번 호출의 제한 시간은 `config.QDRANT_TIMEOUT_SEC`=40초. 시간 초과·연결 실패와 502·503·504에서만 `config.QDRANT_MAX_RETRIES`=2번 다시 시도하고(대기 0.5초, 1초), 401·404는 재시도하지 않는다. 정하지 않으면 HTTP 기본값(약 5초)이라 서버가 한 번 느리면 요청이 `internal_error`로 끝난다(#106).
- 정답 JSON의 근거 목록을 필터나 검색어로 쓰지 않는다.
- 검색 호출은 `platform.tracing.span("retrieve")`로 감싼다. 출력에 문맥 축소 전 검색 청크의 본문·점수·메타데이터를 남기고, 메타데이터에 방식·k·chunk_id 목록·소요 시간을 남긴다.

상태: 네 방식 모두 동작(#68·#71, `hybrid_rerank_subq`는 #125: 분석 선정과 Basic 60문항×k=5·10에서 120/120 일치). 컬렉션이 없으면 `IndexNotFound`. 청크는 페이지를 넘지 않고 글자 수 기준. Basic·개발용 28문항 비교에서 임베딩(E5 small), 리랭커(bge-reranker-v2-m3), 후보 수(20), hybrid 설정 모두 대안이 이기지 못해 유지했다.

코드 위치: `src/search/` (`index.py`, `chunking.py`, `embed.py`, `store.py`, `retrieve.py`, `keyword.py`(BM25), `rerank.py`, `compare_models.py`(모델 비교 스크립트)). `config_basic.py`·`config_default.py`는 참고용 설정 사본이라 코드가 읽지 않는다(#87). 실제 설정은 `src/config.py`.

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

RetrievalMode = Literal["naive", "hybrid", "hybrid_rerank", "hybrid_rerank_subq"]

def retrieve(query: str, mode: RetrievalMode, k: int) -> list[RetrievedChunk]
```

- 점수 내림차순, 최대 `k`개. 결과 없으면 빈 목록(예외 아님). 지원하지 않는 `mode`는 `ValueError`. 단 `hybrid_rerank_subq`는 하위 질문별 순위를 번갈아 담은 순서이고 `score`는 그 청크를 뽑은 하위 질문의 리랭커 점수라 내림차순이 아닐 수 있다.
- 원문에 없는 메타데이터를 만들지 않는다.

## 관련 ADR

- 0001, 0002, 0003, 0005
