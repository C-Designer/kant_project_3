#!/usr/bin/env bash
# 세션 시작 시 GitHub 로그인으로 담당 영역을 한 줄 알려준다. 매핑은 README "코드 구조" 표와 같다.
# gh가 없거나 로그인이 안 돼 있거나 표에 없으면 "미확인"을 내고, 추측하지 않는다. 항상 exit 0.
login=$(gh api user --jq .login 2>/dev/null) || login=""
case "$login" in
  C-Designer)    echo "담당 영역: platform (김창동, 리드, @C-Designer). 짝: metrics. 먼저 읽을 spec: docs/specs/platform.md" ;;
  yshzjq)        echo "담당 영역: search (윤승환, @yshzjq). 짝: answer. 먼저 읽을 spec: docs/specs/search.md" ;;
  rjqnrll7-cmyk) echo "담당 영역: answer (천희재, @rjqnrll7-cmyk). 짝: search. 먼저 읽을 spec: docs/specs/answer.md" ;;
  ohjuhun1119)   echo "담당 영역: metrics (오주헌, @ohjuhun1119). 짝: judge, platform. 먼저 읽을 spec: docs/specs/metrics.md" ;;
  kokoball-eval) echo "담당 영역: judge (김경민, @kokoball-eval). 짝: metrics. 먼저 읽을 spec: docs/specs/judge.md" ;;
  *)             echo "담당 영역 미확인 (gh 로그인: ${login:-없음}). 추측하지 말고 사용자에게 영역을 물어라" ;;
esac
