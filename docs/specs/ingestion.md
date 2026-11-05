# ingestion spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: 데이터셋 `documents/*.pdf` 전부를 텍스트로 추출하고, 출처(`book_id`, `page`)를 보존한 채 청킹·임베딩해 Qdrant에 색인한다. 전체 재색인 명령을 제공한다. 빠진 문서와 처리 실패 목록을 남긴다.
- 책임 아님: 질의 시점 검색(`retrieval`), `evaluation/` JSON 처리(절대 색인하지 않는다. [requirements.md](../requirements.md) 데이터 규칙).

## 동작

미정 항목은 담당자가 데이터셋 확인 후 이 문서에서 고정한다.

- 데이터 위치: `data/<분야>/documents/*.pdf` (git에 올리지 않는다. `.gitignore`)
- 추출: `pypdf`. 페이지 단위로 읽고 첫 페이지를 1로 기록한다.
- 청킹: 크기·overlap 미정. 표는 행·열 제목, 단위, 각주를 같은 청크에 유지한다. 대상·적용일·단위·출처가 끊기지 않게 한다.
- 임베딩 모델: 로컬 E5 계열, 정확한 모델명·차원 미정.
- Qdrant 컬렉션: 이름·거리 함수·sparse 벡터 포함 여부 미정(`retrieval`의 하이브리드 방식과 함께 결정).
- 재색인 명령: `python -m src.ingestion.index --dataset data/<분야>` (예시. 확정 후 갱신)
- 처리 로그: 문서 수, 페이지 수, 청크 수, 실패 파일과 이유를 `data/<분야>/ingest-report.json`에 남긴다.

코드 위치: `src/ingestion/`

## 인터페이스

청크 레코드. `retrieval`, `service`, `evaluation`이 이 형식에 의존한다.

```json
{
  "page_content": "청크 원문",
  "metadata": {
    "book_id": "FB01",
    "file_name": "FB01.pdf",
    "page": 3,
    "chunk_id": "FB01-p3-c1"
  }
}
```

- `book_id` = 파일명에서 `.pdf`를 뺀 값. 파일명은 바꾸지 않는다.
- `page` = 청크가 시작하는 PDF 페이지(1부터). 여러 페이지에 걸치면 `metadata.page_end`를 추가해도 된다(미정).
- `chunk_id` = `<book_id>-p<page>-c<순번>`. 컬렉션 안에서 유일.
- 위 네 필드 외 메타데이터를 원문에 없는 값으로 만들지 않는다.

## 관련 ADR

- 0001, 0002, 0003
