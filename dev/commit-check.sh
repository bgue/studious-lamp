#!/usr/bin/env bash
# Commit check (process-v3 rule 8, V3-P2). Refuses model names in the commits of <base>..HEAD: in the subject
# and body (outside the Co-Authored-By and Claude-Session trailer lines), and in added lines of docs/reports/**.
#
# Usage: dev/commit-check.sh <base>
# Prints one line per hit: <sha7> <where> <word>, where = subject | body | report. Exit 0 when clean,
# 1 on a hit, 2 on usage errors.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2

usage() {
  echo "usage: dev/commit-check.sh <base>" >&2
  exit 2
}

[ $# -eq 1 ] || usage
case "$1" in
  -h|--help) usage ;;
esac
base="$1"
if ! git rev-parse --verify -q "$base^{commit}" >/dev/null; then
  echo "commit-check: unknown base: $base" >&2
  exit 2
fi

words='claude|opus|sonnet|haiku|fable|gpt'

# scan <sha7> <where>: reads text on stdin, prints one line per model-name word found. A token with no
# spaces that contains a slash (a path or a URL, such as a box path or a link to a session) is not text: it is blanked first.
scan() {
  local sha="$1" where="$2" word
  while IFS= read -r word; do
    printf '%s %s %s\n' "$sha" "$where" "$(printf '%s' "$word" | tr '[:upper:]' '[:lower:]')"
  done < <(sed -E 's#[^[:space:]]*/[^[:space:]]*# #g' | grep -ioEw "$words" || true)
  return 0
}

all_hits() {
  local sha s7
  for sha in $(git rev-list --reverse "$base..HEAD"); do
    s7="$(git rev-parse --short=7 "$sha")"
    git log -1 --format=%s "$sha" | scan "$s7" subject
    git log -1 --format=%B "$sha" | tail -n +2 \
      | awk '!/^(Co-Authored-By|Claude-Session):/' | scan "$s7" body
    git show --format= --unified=0 --no-color "$sha" -- docs/reports \
      | awk '/^\+\+\+/ { next } /^\+/ { print substr($0, 2) }' | scan "$s7" report
  done
  return 0
}

hits="$(all_hits)"
if [ -n "$hits" ]; then
  printf '%s\n' "$hits"
  exit 1
fi
exit 0
