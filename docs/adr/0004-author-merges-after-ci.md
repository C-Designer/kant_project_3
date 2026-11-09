# 0004. PR은 CI(pytest)가 통과하면 올린 사람이 머지한다

- 상태: 채택
- 날짜: 2026-11-06

## 배경

ADR 0002는 리드가 모든 PR을 리뷰·머지하고 자기 PR은 룰셋 우회로 머지한다고 전제했다. 실제 룰셋 `main-protection`에는 우회자가 없어 리드도 PR을 거쳐야 했다. 머지 규칙은 ADR 없이 `docs/branch-strategy.md`에서 두 번 바뀌었다(#72, #73). 이 ADR은 그 결정을 기록한다.

## 결정

- 필수 status check `pytest`(`.github/workflows/ci.yml`: `uv sync --locked` 후 `uv run pytest`)를 룰셋에 건다. 실패하면 머지 버튼이 막힌다(#72).
- CI가 통과하면 **PR을 올린 사람이 직접 Squash and merge**한다. 필수 승인은 없고, 리뷰를 받고 싶으면 Draft로 올려 받은 뒤 머지한다. CODEOWNERS는 리드를 리뷰어로 자동 지정만 한다(#73).
- 룰셋 우회자는 두지 않는다. 리드도 같은 절차를 따른다.

## 이유와 대안

- 리드만 머지(ADR 0002의 전제): GitHub이 강제하지 못하는 약속이었고, 우회자가 없어 리드 자신의 PR도 같은 절차를 거쳤다. 바꾼 이유는 #72·#73에 기록되지 않았다.
- CI 통과 시 자동 머지: #72에서 적용했다가 같은 날 #73에서 작성자 머지로 바꿨다. 이유는 PR에 기록되지 않았다.
- 필수 승인 1개 이상: 승인 0개를 유지했다(#72에서 "unattributed changes 추가 승인" 규칙도 껐다).

## 영향

테스트로 고정한 발제 규칙(`None` 집계, `source_ids` 검증 등)이 깨진 PR은 머지되지 않는다. 다른 영역의 파일을 고친 PR도 담당자 확인 없이 머지될 수 있으므로 그런 PR은 본문에서 담당자를 부른다. `contracts.py`·`config.py`·패키지 변경은 계속 `[interface]` + 짝 확인(ADR 0002). 규칙 전체는 `docs/branch-strategy.md`.
