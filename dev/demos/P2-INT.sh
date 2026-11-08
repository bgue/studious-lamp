#!/usr/bin/env bash
# Demo for P2-INT (ADR-0025, ADR-0027: the optional intent of a command or a proposal): `just demo P2-INT`.
#
# The exit clauses (docs/tickets/P2-INT/README.md, Demo), each ending in a `PASS clause N` line,
# once on SQLite and once on Postgres:
#   1  a command with intent appends an event whose intent column holds the canonical JSON; without
#      intent the column is NULL (scripted: dev/accept/P2-INT/S2.py, checks `1`);
#   2  a chain without intents seals; intents appended after it seal too, and `tl archive verify`
#      passes on the chain; the golden digests of a segment without intent are unchanged
#      (pytest: packages/tl-core/tests/test_archive_intent_compat.py, run first; driver: the chain);
#   3  the archive restores into an empty database with the intents verbatim and verifies (scripted:
#      dev/accept/P2-INT/S1.py); the lake sync lands the bronze `intent` column, filled for an event
#      with intent and NULL for one without (driver: `tl lake sync`, `tl lake query`);
#   4  a bad intent refuses the whole command with intent_invalid; an unknown reference gives
#      intent_reference_unknown with fixed text; nothing is appended (scripted: S2.py, checks `4`);
#      a hidden id answers like an unknown one (pytest: packages/tl-api/tests/test_intent_walk.py);
#   5  {} and all-null intents store NULL (scripted: S2.py, checks `5`);
#   6  an agent's proposal carries an intent in its Created column, not in the payload; accepting
#      appends events with the same intent, actor the accepting person (scripted: S2.py, checks `6`);
#   7  the API reads return intent (scripted: S2.py, checks `7`); a viewer without access sees
#      "not available" (pytest: packages/tl-api/tests/test_activity_intent.py and
#      packages/tl-core/tests/insights/test_activity_intent_twin.py);
#   8  the CLI flags --why/--next/--toward, the MCP intent parameter and the TUI History text each
#      show it, once (driver: dev/accept/P2-INT/demo_cli_mcp.py).
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. The scripted
# checks S1 and S2 run on both backends at once (they open their own schemas on TL_PG_URL).
# Exits non-zero (and prints DEMO FAILED) when any clause is not met. Nothing is left behind.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
pg_url=""
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'drop_pg; rm -rf "$workdir"' EXIT

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN
backends="${TL_DEMO_BACKENDS:-sqlite postgres}"

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1"; }
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}
need_lines() { # need_lines FILE N REGEX: at least N lines of FILE match REGEX
  local got
  got="$(grep -cE "$3" "$1" || true)"
  [ "$got" -ge "$2" ] || { cat "$1" >&2; fail "expected $2 lines matching: $3 (got $got)"; }
}

# Created once per run: the scripted checks, and the pytest golden digests (clause 2, part 1).
step "clause 2 (part 1): the golden digests of a segment without intent are unchanged"
if uv run pytest -q packages/tl-core/tests/test_archive_intent_compat.py >"$workdir/pytest.out" 2>&1; then
  grep -v 'UV_NATIVE_TLS' "$workdir/pytest.out" | tail -n 2
  echo "PASS archive intent compat (golden digests)"
else
  grep -v 'UV_NATIVE_TLS' "$workdir/pytest.out" >&2 || true
  fail "archive intent compat golden digests"
fi

step "scripted checks: S2 (clauses 1, 4-7) and S1 (clause 3), SQLite and Postgres"
quiet uv run python dev/accept/P2-INT/S2.py >"$workdir/s2.out" 2>"$workdir/s2.err" \
  || { cat "$workdir/s2.out"; grep -v 'UV_NATIVE_TLS' "$workdir/s2.err" >&2; fail "S2"; }
quiet uv run python dev/accept/P2-INT/S1.py >"$workdir/s1.out" 2>"$workdir/s1.err" \
  || { cat "$workdir/s1.out"; grep -v 'UV_NATIVE_TLS' "$workdir/s1.err" >&2; fail "S1"; }
cat "$workdir/s2.out" "$workdir/s1.out"

run_tests() { # run_tests CLAUSE BACKEND FILE...: the committed tests of one adapter; PASS on exit 0
  local clause_no="$1" backend="$2" collected n out="$workdir/tests-$1-$2.out"
  shift 2
  collected="$(uv run pytest --collect-only --adapters "$backend" -k "$backend" "$@" 2>/dev/null \
    | sed -n 's/.* \([0-9][0-9]*\) tests* collected.*/\1/p' | tail -n 1)"
  n="${collected:-0}"
  [ "$n" -ge 1 ] || fail "clause $clause_no: no $backend test collected from: $*"
  echo "clause $clause_no: $n $backend tests collected from: $*"
  if ! uv run pytest -q --adapters "$backend" -k "$backend" "$@" >"$out" 2>&1; then
    grep -v 'UV_NATIVE_TLS' "$out" >&2 || true
    fail "clause $clause_no: the $backend tests failed"
  fi
  grep -v 'UV_NATIVE_TLS' "$out" | tail -n 1
}

run_backend() {
  local backend="$1"
  local arch="$workdir/archive-$backend" key="$workdir/archive-$backend.pem"
  local pub="$workdir/archive-$backend.pub" sess="$workdir/session-$backend.json"
  local lake="$workdir/lake-$backend"
  export TL_SESSION_FILE="$sess" TL_LAKE_DIR="$lake" TL_ARCHIVE_DIR="$arch"
  export TL_ARCHIVE_KEY="$key" TL_ARCHIVE_PUBLIC_KEY="$pub"

  # Clause 1, 3-7: the scripted checks, per backend.
  step "[$backend] scripted checks"
  need_lines "$workdir/s2.out" 2 "^PASS $backend 1 "
  clause 1
  step "[$backend] scripted checks of clauses 4-7 (S2)"
  need_lines "$workdir/s2.out" 3 "^PASS $backend 4 "
  need_lines "$workdir/s2.out" 1 "^PASS $backend 5 "
  need_lines "$workdir/s2.out" 3 "^PASS $backend 6 "
  need_lines "$workdir/s2.out" 1 "^PASS $backend 7 "
  for label in "append stores intent text" "hash matches recomputed_hash" "seal" \
    "verify archive" "restore is verbatim" "verify restored ledger"; do
    grep -Fxq "PASS $backend $label" "$workdir/s1.out" || fail "S1 did not pass: $backend $label"
  done

  step "[$backend] clause 2 (part 2): a chain without intents, then intents, seals and verifies"
  drop_pg
  rm -rf "$arch" "$lake" "$sess"
  case "$backend" in
    sqlite) export TL_DB="$workdir/$backend.db" ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  tl init --dev 2>"$workdir/init.err" >/dev/null || { cat "$workdir/init.err" >&2; fail "tl init --dev"; }
  printf 'demo\n' | tl login demo --password-stdin >/dev/null
  quiet uv run tl archive keygen --key "$key" >/dev/null 2>&1 || fail "archive keygen"
  [ -f "$pub" ] || fail "archive keygen wrote no public key"

  out="$(tl record create --project P1 --title "Before any intent")"
  first_key="$(printf '%s\n' "$out" | awk '$1 == "key" {print $2}')"
  [ -n "$first_key" ] || fail "record create gave no key: $out"
  tl record create --project P1 --title "Also before any intent" >/dev/null
  out="$(tl archive seal --max-events 10000)"; echo "$out"
  expect "sealed" "$out"
  tl record create --project P1 --title "With intent" --why "pour on Monday" \
    --next text:call-the-super --toward "$first_key:~cured" >/dev/null
  tl record create --project P1 --title "Without intent after" >/dev/null
  out="$(tl archive seal --max-events 10000)"; echo "$out"
  last_seq="$(printf '%s\n' "$out" | sed -n 's/.*archive is at seq \([0-9][0-9]*\).*/\1/p' | tail -n 1)"
  [ -n "$last_seq" ] || fail "seal gave no last seq: $out"
  out="$(tl archive verify --db "$TL_DB" --expect-last-seq "$last_seq" 2>&1)" || { echo "$out"; fail "tl archive verify"; }
  echo "$out" | grep -E '^verified' || { echo "$out"; fail "tl archive verify did not verify"; }
  clause 2

  step "[$backend] clause 3 (part 2): the lake sync lands the bronze intent column"
  tl lake sync >/dev/null
  counts="$(tl lake query "SELECT count(*) FILTER (WHERE intent IS NOT NULL) AS with_intent, count(*) FILTER (WHERE intent IS NULL) AS without FROM events" | awk -F' [|] ' 'NF == 2 && $1 ~ /^[0-9]+$/ {print $1, $2}')"
  echo "bronze events: with intent, without: $counts"
  read -r with_intent without <<<"$counts"
  [ "${with_intent:-0}" -ge 1 ] || fail "no bronze event has an intent"
  [ "${without:-0}" -ge 1 ] || fail "no bronze event without an intent is NULL"
  text_out="$(tl lake query "SELECT intent FROM events WHERE intent IS NOT NULL")"
  expect "pour on Monday" "$text_out"
  clause 3

  step "[$backend] clause 4: a hidden id answers like an unknown one (committed walking tests)"
  run_tests 4 "$backend" packages/tl-api/tests/test_intent_walk.py
  clause 4
  clause 5
  clause 6
  step "[$backend] clause 7: a viewer without access sees not available (committed tests)"
  run_tests 7 "$backend" packages/tl-api/tests/test_activity_intent.py \
    packages/tl-core/tests/insights/test_activity_intent_twin.py
  clause 7

  step "[$backend] clause 8: CLI --why/--next/--toward, the MCP intent parameter, the TUI History text"
  quiet uv run python dev/accept/P2-INT/demo_cli_mcp.py "$TL_DB" "$first_key" \
    || fail "clause 8 (dev/accept/P2-INT/demo_cli_mcp.py)"
  clause 8

  drop_pg
  echo "[$backend] clauses 1-8 passed"
}

for backend in $backends; do
  run_backend "$backend"
done

echo
echo "P2-INT demo OK on: $backends"
