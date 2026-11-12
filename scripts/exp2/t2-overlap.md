<task>
[T2 overlap 청킹과 색인 빌더] 브랜치 exp/exp2-overlap.
1. 원격 브랜치 origin/exp/chunk-ab(윤승환, "main에 넣지 않음")의 `src/search/chunking.py` 변경을 `git show`/`git diff origin/main...origin/exp/chunk-ab -- src/search/chunking.py`로 **읽기만** 한다. 거기서 overlap을 다루는 방식을 이해하되 그 브랜치를 merge·cherry-pick하지 않고 코드를 통째로 복사하지 않는다(임베딩 비교 등 다른 스위치는 범위 밖).
2. scripts/exp_chunking.py에 interface_contract의 `chunk_pages`를 구현한다. overlap=0이면 `src.search.chunking.chunk_pages`와 결과가 완전히 같아야 한다(원본을 그대로 호출해 위임해도 된다). overlap>0이면 쪽 경계를 존중하는 현재 청킹 규칙(쪽이 size보다 길면 문장 끝에서 균등 분할, ChunkMeta의 file_name·book_id·page·chunk_id 규칙)을 깨지 않고 이전 청크 끝 overlap글자를 다음 청크 앞에 붙인다. 청크 id가 서로 겹치지 않게 한다. src/search/chunking.py의 ChunkMeta 생성·id 규칙을 읽어 그대로 따른다.
3. scripts/exp_index.py를 만든다. src.search.index의 색인 함수를 재사용하되(기존 함수를 읽고 설정 덮어쓰기 방식으로 호출), 컬렉션 삭제·재생성이 EXP_INDEX_DIR 안의 새 로컬 Qdrant에만 일어나게 한다. 원본 `data/shipping/qdrant`와 `ingest-report.json`에 쓰지 않도록 config.QDRANT_PATH와 리포트 경로를 EXP_INDEX_DIR로 돌린다(src/search/index.py:77의 쓰기 위치를 확인). QDRANT_URL이 설정돼 있으면 RuntimeError로 거부한다.
4. 색인이 끝나면 청크 토큰 길이를 임베딩 모델 토크나이저(config.EMBEDDING_MODEL, e5-small 최대 512 토큰)로 재서 index_meta.json에 `max_tokens`와 `over_512`(512 토큰을 넘는 청크 수)를 추가로 적는다. chunk_size 1200이 임베딩 입력 한도를 넘는지 보려는 값이다.
</task>

<completeness_contract>
점검: overlap=0 결과가 원본과 같음, overlap=100에서 인접 청크가 정확히 100글자 겹침, 쪽 경계(다른 쪽의 글이 섞이지 않음)·chunk_id 유일성을 작은 가짜 입력으로 assert. 실제 색인은 작업 폴더 안 `.scratch/idx/600-100`(chunk_size 600, overlap 100)에 한 번 만들고(`.scratch/`가 커밋에 섞이지 않게 이 워크트리의 `.git/info/exclude`에 추가하고 `git add`는 파일 이름을 명시한다), 청크 수와 index_meta.json 내용을 보고한다. 시간이 오래 걸리면 PDF 1~2개로 줄여도 되고, 줄였다면 보고에 적는다.
</completeness_contract>
