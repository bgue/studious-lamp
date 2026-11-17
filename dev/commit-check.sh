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

# path_pieces: on stdin, splits each token that holds a slash and keeps only the pieces that are not path or
# URL parts. A piece is a path or URL part when it is empty, a scheme (https:), holds a dot (claude.ai,
# a file name) or a hyphen and digit (claude-0). So /tmp/claude-0/x and https://claude.ai/code/x are clean,
# while opus/sonnet and see/Opus still hit.
path_pieces() {
  awk '{
    out = ""
    for (i = 1; i <= NF; i++) {
      t = $i
      if (index(t, "/") == 0) { out = out " " t; continue }
      n = split(t, p, "/")
      for (j = 1; j <= n; j++) {
        q = p[j]
        if (q == "" || q ~ /:$/ || index(q, ".") > 0 || q ~ /-[0-9]/) continue
        out = out " " q
      }
    }
    print out
  }'
}

# exempt_trailers: on stdin (a message body), drops the trailer lines that may name the agent: a Co-Authored-By
# line, or a Claude-Session line followed by a URL. Only lines in the final contiguous trailer block are exempt;
# a trailer-looking line mid-body is checked.
exempt_trailers() {
  awk '
    { line[NR] = $0 }
    END {
      n = NR
      while (n > 0 && line[n] == "") n--
      s = n + 1
      while (s > 1 && line[s - 1] ~ /^[A-Za-z][A-Za-z-]*: /) s--
      for (i = 1; i <= NR; i++) {
        if (i >= s && (line[i] ~ /^Co-Authored-By: / || line[i] ~ /^Claude-Session: https?:\/\//)) continue
        print line[i]
      }
    }'
}

# scan <sha7> <where>: reads text on stdin, prints one line per model-name word found.
scan() {
  local sha="$1" where="$2" word
  while IFS= read -r word; do
    printf '%s %s %s\n' "$sha" "$where" "$(printf '%s' "$word" | tr '[:upper:]' '[:lower:]')"
  done < <(path_pieces | grep -ioEw "$words" || true)
  return 0
}

all_hits() {
  local sha s7
  for sha in $(git rev-list --reverse "$base..HEAD"); do
    s7="$(git rev-parse --short=7 "$sha")"
    git log -1 --format=%s "$sha" | scan "$s7" subject
    git log -1 --format=%B "$sha" | tail -n +2 | exempt_trailers | scan "$s7" body
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
