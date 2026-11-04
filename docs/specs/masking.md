# masking spec

<!-- 이 문서는 "지금 어떻게 동작하나"의 기준이다. 코드가 바뀌면 같은 PR에서 함께 고친다. -->

## 범위

- 책임: LLM API로 나가는 메시지에서 개인정보(이름, 연락처, 주민번호 등)를 마스킹하고, 필요하면 응답에서 원래 값으로 되돌린다.
- 책임 아님: 저장 데이터의 암호화, 로그 마스킹(`observability`가 이 영역의 함수를 호출해 처리).

## 동작

미정. 마스킹 대상 항목과 방식(규칙 기반 / NER)은 데이터셋 확인 후 정한다.

핵심 규칙(확정):
- 호출 지점은 하나다. `agent`가 LLM을 호출하기 직전에 거친다.
- 마스킹 전 원문은 외부(LLM API, Langfuse)로 나가지 않는다.

코드 위치: `src/masking/`

## 인터페이스

- `mask(messages) -> (masked_messages, mapping)`
- `unmask(text, mapping) -> text`
- `mapping`은 요청 단위로만 살고 저장하지 않는다.

## 관련 ADR

- 0001
