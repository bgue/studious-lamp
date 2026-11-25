#!/usr/bin/env bash
# Name and copy a built single-file viewer as xray-viewer-v<N>-<YYYYMMDD>-<sha>.html.
#   N      download number: tools/viewer-release.txt holds the last one; this script adds 1 and writes it back.
#   date   build date (local time).
#   sha    short hash of the source commit (HEAD); "-dirty" is added when the working tree has uncommitted changes.
# Output goes to /home/user/xray-ref-dist/viewers/ (or $1), and the root xray-viewer.html is refreshed too.
# Build first, WITH RELEASE=1:  (cd web && RELEASE=1 npm run bundle)
#   Release number in the build: the "What's new" note (web/src/whatsnew) compares the number the build carries with the one a browser
#   saw last. This script bumps the counter AFTER the build, so a build has to know the number it is going to get: with RELEASE=1
#   web/tools/release-number.mjs gives the build counter+1 (without it, the last released number, which is what dev servers and
#   smoke tests show). The build writes the number into the page as <meta name="xray-release" content="N">; this script refuses
#   to name a file whose meta tag differs from the number it is about to assign (a build made without RELEASE=1, or a stale one).
#   Write the release's lines in CHANGELOG.md (rename "Unreleased" to "vN - YYYY-MM-DD") BEFORE building: the build embeds it.
# Prints the full path of the named file on the last line. Commit tools/viewer-release.txt afterwards.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-/home/user/xray-ref-dist/viewers}"
SINGLE="$REPO/web/dist-single/xray-viewer.html"
COUNTER="$REPO/tools/viewer-release.txt"

[ -f "$SINGLE" ] || { echo "missing $SINGLE: build it first" >&2; exit 1; }
last="$(tr -dc '0-9' < "$COUNTER" 2>/dev/null || true)"
n=$(( ${last:-0} + 1 ))
built="$(grep -o '<meta name="xray-release" content="[0-9]*"' "$SINGLE" | head -n 1 | tr -dc '0-9' || true)"
if [ "$built" != "$n" ]; then
  echo "$SINGLE carries release '${built:-none}' but this release is v$n: rebuild with RELEASE=1 (cd web && RELEASE=1 npm run bundle)" >&2
  exit 1
fi
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
