#!/usr/bin/env bash
# 사용: bash scripts/exp2/launch.sh <t1|t2|t3|t4>   (기준 워크트리에서 실행)
# 선행: 기준 브랜치(exp/langfuse-experiments)에 scripts/lf_experiment.py와 docs/experiments/0002-*.md가 커밋돼 있어야
#       새 워크트리에 보인다. 이 스크립트는 커밋하지 않는다.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
BASE=$(cd "$HERE/../.." && pwd)
ROOT=$(dirname "$BASE")
# shortcut: codex 플러그인 버전(1.0.6)이 경로에 박혀 있다, 플러그인을 올리면 이 경로를 고친다
CC=$HOME/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/codex-companion.mjs

# 작업 | 브랜치 접미사 | 모델 | effort
case "${1:-}" in
  t1) name=inject;  model=spark;       effort=medium ;;
  t2) name=overlap; model=gpt-6-astra; effort=medium ;;
  t3) name=docker;  model=spark;       effort=low ;;
  t4) name=latency; model=spark;       effort=low ;;
  *) echo "사용: $0 t1|t2|t3|t4"; exit 1 ;;
esac
wt="$ROOT/exp2-$name"

if [ ! -d "$wt" ]; then
  git -C "$BASE" worktree add -b "exp/exp2-$name" "$wt" exp/langfuse-experiments
  cp -R "$BASE/data" "$wt/data"  # 복사본이라 원본 로컬 색인을 건드리지 않는다
  printf 'data/\n.scratch/\n' >> "$(git -C "$wt" rev-parse --path-format=absolute --git-common-dir)/info/exclude"
fi

mkdir -p "$wt/.scratch"
cat "$HERE/common.md" "$HERE/$1-$name.md" > "$wt/.scratch/prompt.md"
node "$CC" task --background --write --cwd "$wt" --model "$model" --effort "$effort" --prompt-file "$wt/.scratch/prompt.md"
