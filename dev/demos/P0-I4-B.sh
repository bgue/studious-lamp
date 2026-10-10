#!/usr/bin/env bash
# Demo for P0-I4 workstream B (files): content-addressed attachments, dedupe, revisions, download
# with hash check, and object-store reconciliation. The full P0-I4 demo is dev/demos/P0-I4.sh.
# Run with `just demo P0-I4-B` from the repository root. Uses a temporary ledger and object root;
# nothing is left behind. Fails (exit 1) when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
export TL_DB="$workdir/tl.db"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_ENV="${TL_ENV:-dev}"
unset TL_SCHEMA_DIR TL_OBJECT_STORE

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

printf '%%PDF-1.7 mill test report, heat 4711\n' >"$workdir/mtr.pdf"
printf '%%PDF-1.7 mill test report, heat 4711, revision 2\n' >"$workdir/mtr-rev2.pdf"
printf 'site photo\n' >"$workdir/note.txt"

step "tl init; a record to attach to"
tl init
tl record create --project P123 --key P123-REC-0001 --title "Valve V-101"

step "tl file put (slot report, PDF only)"
first="$(tl file put "$workdir/mtr.pdf" --project P123 --record P123-REC-0001 --slot report)"
echo "$first"
expect "$first" '^status available$'
expect "$first" '^revision 1$'
expect "$first" '^sha256 [0-9a-f]{64}$'
id1="$(sed -n 's/^file //p' <<<"$first")"

step "the same bytes again: nothing new is attached"
again="$(tl file put "$workdir/mtr.pdf" --project P123 --record P123-REC-0001 --slot report)"
echo "$again"
expect "$again" '^already attached$'

step "a wrong type is refused by the slot"
if tl file put "$workdir/note.txt" --project P123 --record P123-REC-0001 --slot report 2>"$workdir/err"; then
  echo "DEMO FAILED: a text file was accepted into the PDF slot" >&2
  exit 1
fi
cat "$workdir/err"
expect "$(cat "$workdir/err")" 'error: '

step "a generic attachment needs no slot"
tl file put "$workdir/note.txt" --project P123 --record P123-REC-0001

step "revision 2 supersedes revision 1 in the one-file slot"
second="$(tl file put "$workdir/mtr-rev2.pdf" --project P123 --record P123-REC-0001 --slot report)"
expect "$second" '^revision 2$'
echo "-- current files"
tl file ls --project P123 --record P123-REC-0001
echo "-- all files"
all="$(tl file ls --project P123 --record P123-REC-0001 --all)"
echo "$all"
expect "$all" "^${id1}"$'\t'"report"$'\t'"1"$'\t'"superseded"

step "tl file get: identical bytes, hash checked"
tl file get "$id1" --project P123 --out "$workdir/copy.pdf"
cmp "$workdir/mtr.pdf" "$workdir/copy.pdf"
echo "bytes identical"

step "the ledger holds the file events"
events="$(tl events tail --project P123 -n 20)"
echo "$events" | cut -c1-100
expect "$events" 'File.Uploaded'
expect "$events" 'File.Processed'

step "tl file reconcile: clean"
tl file reconcile --verify

step "damage an object, reconcile finds it (exit 1 expected)"
stored="$(find "$TL_OBJECT_ROOT/sha256" -type f | head -n 1)"
printf 'bit rot' >"$stored"
if tl file reconcile --verify >"$workdir/rec" 2>&1; then
  echo "DEMO FAILED: reconcile did not notice the damaged object" >&2
  exit 1
fi
cat "$workdir/rec"
expect "$(cat "$workdir/rec")" '^corrupt [0-9a-f]{64} files='

echo
echo "P0-I4 workstream B demo OK"
