#!/usr/bin/env bash
# Demo for P0-I1 (Foundations): ledger, hash chain, current-state table, and the `tl` CLI.
# Run with `just demo P0-I1` from the repository root. Uses a temporary ledger; nothing is left behind.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
export TL_DB="$workdir/tl.db"

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
tl() { uv run tl "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>: fail the demo if the pattern is missing
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}

step "tl init"
tl init

step 'tl record create --project P123 --key DEMO-0001 --title "First record"'
out="$(tl record create --project P123 --key DEMO-0001 --title "First record")"
echo "$out"
expect "$out" '^version 1$'

step "tl record show --project P123 DEMO-0001   (the cur_core_record row)"
before="$(tl record show --project P123 DEMO-0001)"
echo "$before"
expect "$before" '^title: First record$'
expect "$before" '^voided: false$'

step "the same row read straight from the table"
uv run python - "$TL_DB" 2> >(grep -v 'UV_NATIVE_TLS' >&2) <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.row_factory = sqlite3.Row
row = db.execute("SELECT id, key, type, scope, title, status, voided, version, last_seq FROM cur_core_record").fetchone()
print(dict(row))
PY

step "tl events tail --project P123 -n 5   (Record.Created with its hash)"
events="$(tl events tail --project P123 -n 5)"
echo "$events"
expect "$events" 'Record\.Created .* [0-9a-f]{64}$'

step "a duplicate key is refused (exit 1)"
if tl record create --project P123 --key DEMO-0001 --title "Again"; then
  echo "DEMO FAILED: duplicate key was accepted" >&2
  exit 1
fi

step "tl record void --project P123 DEMO-0001 --reason demo"
tl record void --project P123 DEMO-0001 --reason demo
voided="$(tl record show --project P123 DEMO-0001)"
echo "$voided"
expect "$voided" '^voided: true$'
expect "$voided" '^version: 2$'

step "tl projections rebuild   (replay the ledger; the row must not change)"
rebuilt="$(tl projections rebuild)"
echo "$rebuilt"
expect "$rebuilt" '^replayed 2 events$'
after="$(tl record show --project P123 DEMO-0001)"
if [ "$after" != "$voided" ]; then
  echo "DEMO FAILED: rebuild changed the row" >&2
  exit 1
fi

step "events after the void (hash chain: each line has its own 64-hex hash)"
tl events tail --project P123 -n 5

printf '\nP0-I1 demo ok\n'
