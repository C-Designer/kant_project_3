# retrieval spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: 질의와 검색 방식을 받아 Qdrant에서 상위 `k`개 청크를 돌려준다. 세 방식 `naive`, `hybrid`, `hybrid_rerank`를 같은 함수 시그니처로 제공한다.
- 책임 아님: 색인(`ingestion`), 청크를 프롬프트에 넣는 방법과 문맥 길이 제한(`service`).

## 동작

| 방식 | 처리 | 미정 |
|---|---|---|
| `naive` | dense 임베딩 유사도 상위 k | - |
| `hybrid` | dense + 키워드 검색을 합쳐 순서를 정함 | 키워드 검색 방식(BM25 계열 / Qdrant sparse), 결합 방식(RRF 등)과 가중치 |
| `hybrid_rerank` | `hybrid` 후보 상위 N개를 리랭커로 질문과 다시 비교해 상위 k | 리랭커 모델, 후보 수 N |

- 세 방식은 같은 컬렉션, 같은 임베딩을 쓴다. 질의 임베딩도 `ingestion`과 같은 모델.
- `k`는 호출자가 넘기고, 최종 비교에서는 세 방식에 같은 값을 쓴다. 기본값 미정.
- 정답 JSON의 근거 목록을 필터나 검색어로 쓰지 않는다.

코드 위치: `src/retrieval/`

## 인터페이스

```python
RetrievalMode = Literal["naive", "hybrid", "hybrid_rerank"]

def retrieve(query: str, mode: RetrievalMode, k: int) -> list[RetrievedChunk]
```

`RetrievedChunk`:

```json
{
  "text": "청크 원문",
  "score": 0.83,
  "metadata": { "book_id": "FB01", "file_name": "FB01.pdf", "page": 3, "chunk_id": "FB01-p3-c1" }
}
```

- `metadata`는 `ingestion`의 청크 레코드 그대로.
- 결과는 점수 내림차순, 길이는 최대 `k`. 검색 결과가 없으면 빈 목록(예외 아님).
- 지원하지 않는 `mode`는 `ValueError`.
- 검색 호출은 `observability`의 스팬으로 감싼다(방식, k, 소요 시간, 반환 `chunk_id` 목록).

## 관련 ADR

- 0001, 0002, 0003
