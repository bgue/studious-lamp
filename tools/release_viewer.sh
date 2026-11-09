#!/usr/bin/env bash
# Name and copy a built single-file viewer as xray-viewer-v<N>-<YYYYMMDD>-<sha>.html.
#   N      download number: tools/viewer-release.txt holds the last one; this script adds 1 and writes it back.
#   date   build date (local time).
#   sha    short hash of the source commit (HEAD); "-dirty" is added when the working tree has uncommitted changes.
# Output goes to /home/user/xray-ref-dist/viewers/ (or $1), and the root xray-viewer.html is refreshed too.
# Build first: (cd web && npm run build && npm run bundle && node bench/single-file.mjs)
# Prints the full path of the named file on the last line. Commit tools/viewer-release.txt afterwards.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-/home/user/xray-ref-dist/viewers}"
SINGLE="$REPO/web/dist-single/xray-viewer.html"
COUNTER="$REPO/tools/viewer-release.txt"

[ -f "$SINGLE" ] || { echo "missing $SINGLE: build it first" >&2; exit 1; }
last="$(tr -dc '0-9' < "$COUNTER" 2>/dev/null || true)"
n=$(( ${last:-0} + 1 ))
sha="$(git -C "$REPO" rev-parse --short=7 HEAD)"
if [ -n "$(git -C "$REPO" status --porcelain --untracked-files=no -- . ':!tools/viewer-release.txt' ':!xray-viewer.html')" ]; then
  sha="$sha-dirty"
fi
name="xray-viewer-v$n-$(date +%Y%m%d)-$sha.html"

mkdir -p "$OUT_DIR"
cp "$SINGLE" "$OUT_DIR/$name"
cp "$SINGLE" "$REPO/xray-viewer.html"
echo "$n" > "$COUNTER"
echo "$OUT_DIR/$name"
