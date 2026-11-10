# config.py 동결 기록

- 동결 커밋: `efba38c1a93be79363c0d3c47372fd0a55037c54` (2026-11-10, PR #121, 이슈 #41)
- 이후 `src/config.py` 변경은 `[interface]` PR + 전체 재실행. 바꿨으면 아래에 커밋을 덧붙인다.

확인: `git diff efba38c -- src/config.py`가 비어 있으면 동결값 그대로다.
