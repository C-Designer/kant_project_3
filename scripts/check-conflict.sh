#!/usr/bin/env bash
# Claude Code·Codex 공용 PreToolUse(Bash) 훅: `gh pr create` 전에 현재 브랜치가 origin/main과 충돌하는지 본다.
# 충돌이면 exit 2로 막고 충돌 파일을 알려준다. 그 외(다른 명령, fetch 실패)는 통과(exit 0).
cmd=$(jq -r '.tool_input.command // ""')
[[ "$cmd" == *"gh pr create"* ]] || exit 0

git fetch -q origin main 2>/dev/null || exit 0
if ! out=$(git merge-tree --write-tree --name-only HEAD origin/main 2>&1); then
  {
    echo "origin/main과 충돌이 있어 PR 생성을 막았다. 충돌 파일:"
    echo "$out" | sed -n '2,/^$/p' | sed '/^$/d'
    echo "해결: git merge origin/main 후 충돌을 고쳐 커밋하고 다시 PR을 만든다 (docs/branch-strategy.md)."
  } >&2
  exit 2
fi
exit 0
