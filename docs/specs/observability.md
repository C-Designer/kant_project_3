# observability spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: Langfuse 연동. 요청 ID 하나에 질문, 검색 결과, 최종 문맥, 실제 모델 입출력, 상태, 인용, 응답 시간, 입력·출력 토큰, 오류를 묶어 남긴다. 평가 점수를 트레이스에 붙이는 함수. JSONL 보조 기록.
- 책임 아님: 애플리케이션 로직. 다른 영역이 이 영역의 함수를 호출한다.

## 동작

- Langfuse 운영 방식 미정(Cloud / 셀프호스트). 팀 프로젝트 하나를 만들고 키는 각자 `.env`에.
- 트레이스 이름 = `query`, `trace_id` 또는 메타데이터에 `request_id`. 스팬: `retrieve`(mode, k, chunk_id 목록, 소요 시간), `build_context`(최종 문맥, 잘린 청크), `generate`(실제 프롬프트, 모델 출력 원문, 토큰, 시간, 재시도 횟수), `validate`(검증 결과).
- 평가 호출(RAGAS, Judge)은 별도 트레이스 이름(`eval`)으로 구분해 서비스 사용량에 섞이지 않게 한다.
- 대표 요청을 열면 "정정 공지를 못 찾음"과 "찾았지만 문맥에서 잘림"을 구분할 수 있어야 한다. 그래서 `retrieve` 결과와 `build_context` 결과를 둘 다 남긴다.
- API 키·비밀값은 트레이스에 넣지 않는다.
- Langfuse 확인 방법(프로젝트, 필터, 대표 요청 ID)은 README에 적는다.

코드 위치: `src/observability/`

## 인터페이스

```python
@contextmanager
def trace_query(request_id: str, question: str, mode: str): ...   # 트레이스 시작/종료
def span(name: str, **attrs): ...                                  # 컨텍스트 매니저
def record_generation(prompt, output, input_tokens, output_tokens, latency_ms, error=None): ...
def record_score(request_id: str, name: str, value: float | None, comment: str = ""): ...
def write_jsonl(path, record): ...                                 # 보조 기록
```

환경 변수: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`. `.env.example`에 키 이름만 둔다.

## 관련 ADR

- 0001, 0002, 0003
