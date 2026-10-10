#!/usr/bin/env bash
# Demo for P0-I6 workstream A (activity feed and hashtags): records make an event card, a post tags a
# record and a signal, the tag suggests a `references` link (nothing else changes), the feed is read
# by project, record and hashtag, a post is reacted to and retracted, and a rebuild of the
# projections gives the same feed. Run with `just demo P0-I6-A` from the repository root. Uses a
# temporary ledger; nothing is left behind. Fails (exit 1) when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
export TL_DB="$workdir/tl.db"
unset TL_SCHEMA_DIR

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>: fail the demo if the pattern is missing
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}
refuse() { # refuse <description> <command...>: the command must fail; its stderr is printed
  local what="$1"
  shift
  if "$@" 2>"$workdir/refused.err"; then
    echo "DEMO FAILED: $what was accepted" >&2
    exit 1
  fi
  cat "$workdir/refused.err"
}

step "tl init ; two records are created in a burst"
tl init
tl record create --project P123 --title "Spool S03" >/dev/null
tl record create --project P123 --title "Gate valve 47" >/dev/null
spool=P123-REC-0001
valve=P123-REC-0002

step "the burst is one event card in the project feed"
out="$(tl feed ls --project P123)"
echo "$out"
expect "$out" "  card  .*  dev created 2 records \($spool, $valve\)"

step "a post tags a record, a signal tag, a code and a mention"
out="$(tl feed post --project P123 "Spool arrived with damaged bevels #$spool #hold #area:A12 @party:fab-a" --actor user:mlee)"
echo "$out"
expect "$out" "^posted [0-9A-Z]{26}$"
expect "$out" "tags #$spool \(record\), #hold \(signal\), #area:A12 \(code\), @party:fab-a \(mention\)"
expect "$out" "^suggested 1 link$"
post_id="$(head -n1 <<<"$out" | cut -d' ' -f2)"

step "the tag only SUGGESTS a link: the record itself did not change"
out="$(tl link list --project P123 "$spool")"
echo "$out"
expect "$out" "referenced by .* suggested"
out="$(tl record show --project P123 "$spool")"
expect "$out" "^version: 1$"

step "the feed by hashtag, by record, and posts only"
out="$(tl feed ls --project P123 --tag hold)"
echo "$out"
expect "$out" "^$post_id  post .* mlee !  Spool arrived"
[ "$(tl feed ls --project P123 --tag hold | wc -l)" -eq 1 ]
out="$(tl feed ls --project P123 --record "$spool" --posts)"
expect "$out" "^$post_id"
[ -z "$(tl feed ls --project P123 --record "$valve" --posts)" ]

step "two people acknowledge the post; the same person cannot twice"
tl feed react --project P123 "$post_id" --actor user:ann
tl feed react --project P123 "$post_id" --actor user:bob
refuse "a second ack by the same person" tl feed react --project P123 "$post_id" --actor user:ann
out="$(tl feed ls --project P123 --posts)"
echo "$out"
expect "$out" "\[ack 2\]$"

step "a rebuild of the projections gives the same feed"
before="$(tl feed ls --project P123)"
quiet uv run tl projections rebuild
after="$(tl feed ls --project P123)"
if [ "$before" != "$after" ]; then
  echo "DEMO FAILED: the feed changed after a rebuild" >&2
  diff <(echo "$before") <(echo "$after") >&2 || true
  exit 1
fi
echo "identical after rebuild"

step "retracting the post leaves a tombstone and takes it out of the hashtag feed"
tl feed retract --project P123 "$post_id" --reason "wrong spool" --actor user:mlee
out="$(tl feed ls --project P123 --posts)"
echo "$out"
expect "$out" "\[retracted\]"
[ -z "$(tl feed ls --project P123 --tag hold)" ]
refuse "reacting to a retracted post" tl feed react --project P123 "$post_id" --actor user:cy

step "a blank post and an unknown record are refused"
refuse "a blank post" tl feed post --project P123 "   "
refuse "an unknown record feed" tl feed ls --project P123 --record NOPE-1

echo
echo "P0-I6-A demo ok"
