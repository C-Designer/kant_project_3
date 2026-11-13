#!/usr/bin/env bash
# HTML 두 벌을 다시 만들고 Chrome으로 PDF를 뽑는다. macOS + Google Chrome 필요.
set -euo pipefail
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
python3 build_deck.py
for n in RAG-search-experiments-team RAG-param-sweep-platform; do
  "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$PWD/$n.pdf" "file://$PWD/$n.html" >/dev/null 2>&1
  echo "$n.pdf"
done
