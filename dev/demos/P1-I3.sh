#!/usr/bin/env bash
# Demo for P1-I3 (M1 derivation pipeline: extractor jobs, schema-validated derived documents,
# publication with provenance, compensation): `just demo P1-I3`.
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  an admin registers the instrument-index and equipment-list schemas; a user cannot;
#   2  a PDF rendition of ISD-001 revision A is read by the PDF extractor: its properties are
#      recorded (pages, title), its content is stubbed (ADR-0008 decision 8);
#   3  a CSV with one wrong cell is attached: validation fails and the report names row and field;
#   4  the fixed CSV is attached and read again: a new pass, valid; the diff shows the one change;
#   5  publishing (admin) creates 40 tags with provenance src.doc.ISD-001@A and a `derived from`
#      link; compensation (admin) takes the batch back by the ids it recorded; the ledger only grows;
#   6  a user and an agent cannot publish; an agent's propose_import waits for a person, and a
#      user cannot accept it (the admin can); a client cannot pose as a publication;
#   7  the API, the TUI screens (F11, job monitor, publish preview) and the agent's MCP tools show
#      the same derived document;
#   8  a schema with a pattern that never finishes ends as validation_limit within seconds, and the
#      worker goes on to the next job.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. Starts
# `tl serve` on a free loopback port over a temporary ledger; nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
pg_url=""
stop_server() { # the server has its own process group (setsid): stop the whole group
  [ -n "$server_pid" ] || return 0
  kill -TERM -- "-$server_pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    curl -fs "${TL_DEMO_URL:-http://127.0.0.1:1}/health" >/dev/null 2>&1 || break
    sleep 0.1
  done
  kill -KILL -- "-$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  server_pid=""
}
drop_pg() {
  [ -z "$pg_url" ] || quiet uv run python dev/demos/p1_i0_demo.py pg-drop "$pg_url" || true
  pg_url=""
}
trap 'stop_server; drop_pg; rm -rf "$workdir"' EXIT

export TL_ENV="${TL_ENV:-dev}"
export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_DEMO_STATE="$workdir/state"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i3_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}
refuse() { # refuse TEXT cmd...: the command must fail and say TEXT
  local text="$1" out; shift
  if out="$("$@" 2>&1)"; then echo "$out"; fail "this was accepted: $*"; fi
  echo "$out"; expect "$text" "$out"
}

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
SAMPLES=schema/fixtures/document-schemas
KEY=ISD-001@A/instrument-index
EQKEY=ISD-002@A/equipment-list

run_backend() {
  local backend="$1"
  step "[$backend] a new ledger, the demo account, and the API on a free loopback port"
  stop_server
  case "$backend" in
    sqlite) export TL_DB="$workdir/$backend.db" ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  local port
  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  export TL_DEMO_URL="http://127.0.0.1:$port"
  export TL_TOKENS="$workdir/tokens-$backend.json"
  tl init --dev 2>"$workdir/init.err" >/dev/null || { cat "$workdir/init.err" >&2; fail "tl init --dev"; }
  setsid uv run tl serve --port "$port" >"$workdir/server-$backend.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 150); do
    curl -fs "$TL_DEMO_URL/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$TL_DEMO_URL/health" | grep -q '"status":"ok"' || {
    cat "$workdir/server-$backend.log" >&2
    fail "the server did not start"
  }
  echo "(serving $backend at $TL_DEMO_URL)"
  printf 'demo\n' | as demo tl login demo --password-stdin >/dev/null
  export TL_DEMO_AMY_PASSWORD="a long passphrase for amy"
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as demo tl admin user add amy --display-name "Amy A" --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>/dev/null)"
  export TL_DEMO_AGENT_TOKEN
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin >/dev/null
  as demo tl standards load "$STANDARDS" >/dev/null
  driver prepare "$workdir"
  local derive_worker="tl derive worker --once"

  step "[$backend] clause 1: an admin registers the schemas; a user cannot"
  refuse "forbidden" as amy tl derive schema register "$workdir/instrument-index.yaml" --company
  out="$(as demo tl derive schema register "$workdir/instrument-index.yaml" --company)"; echo "$out"
  expect "registered instrument-index@1.0.0 company" "$out"
  as demo tl derive schema register "$workdir/equipment-list.yaml" --company >/dev/null
  out="$(as amy tl derive schema ls)"; echo "$out"
  expect "instrument-index@1.0.0" "$out"
  expect "equipment-list@1.0.0" "$out"
  echo "PASS 1: the admin registered instrument-index and equipment-list; a user was refused"

  step "[$backend] clause 2: the PDF extractor records the properties and stubs the content"
  as amy tl doc register ISD-001 --project P123 --title "Instrument index, unit 47" >/dev/null
  as amy tl doc rev create ISD-001 --project P123 --purpose "First issue" >/dev/null
  as amy tl doc rendition add ISD-001 A "$workdir/isd-001-A.pdf" --project P123 --kind pdf --pages 3 >/dev/null
  out="$(as amy tl derive open ISD-001 A --schema instrument-index --project P123)"; echo "$out"
  expect "opened $KEY" "$out"
  as amy tl derive start "$KEY" --project P123 >/dev/null
  out="$(as amy $derive_worker)"; echo "$out"
  expect " extract done" "$out"
  out="$(as amy tl derive show "$KEY" --project P123)"; echo "$out"
  expect "pass 1  pdf  metadata_only  rows 0" "$out"
  expect "state Pending" "$out"
  echo "PASS 2: the PDF extractor read the file (metadata_only: content extraction is stubbed, ADR-0008 decision 8)"

  step "[$backend] clause 3: a CSV with one wrong cell fails validation, and the report says where"
  as amy tl derive content "$KEY" "$SAMPLES/instrument-index@1.0.0.invalid.csv" --project P123 >/dev/null
  as amy tl derive start "$KEY" --project P123 >/dev/null
  as amy $derive_worker >/dev/null
  out="$(as amy tl derive report "$KEY" --project P123)"; echo "$out"
  expect ": invalid" "$out"
  expect "column fail_action" "$out"
  expect "OPEN" "$out"
  out="$(as amy tl derive show "$KEY" --project P123)"
  expect "state Invalid" "$out"
  echo "PASS 3: validation failed on one row, naming its row and the field fail_action"

  step "[$backend] clause 4: the fixed CSV is read again; the diff shows the one change"
  as amy tl derive content "$KEY" "$SAMPLES/instrument-index@1.0.0.sample.csv" --project P123 >/dev/null
  as amy tl derive start "$KEY" --project P123 >/dev/null
  as amy $derive_worker >/dev/null
  out="$(as amy tl derive show "$KEY" --project P123)"; echo "$out"
  expect "state Valid" "$out"
  expect "pass 3  tabular  ok  rows 40" "$out"
  out="$(as amy tl derive diff "$KEY" --project P123 --rev 3)"; echo "$out"
  expect "changed 1" "$out"
  expect "fail_action OPEN -> " "$out"
  echo "PASS 4: pass 3 is valid with 40 rows; the diff against pass 2 shows the fixed cell"

  step "[$backend] clause 5: publishing creates 40 tags with provenance; compensation takes them back"
  out="$(as amy tl derive publish "$KEY" --project P123)"; echo "$out" | sed -n 1,4p
  expect "create 40" "$out"
  expect "dry run: nothing written" "$out"
  refuse "forbidden" as amy tl derive publish "$KEY" --project P123 --apply
  out="$(as demo tl derive publish "$KEY" --project P123 --apply)"; echo "$out"
  expect "published 40 records" "$out"
  driver published 40 after-publish
  out="$(as demo tl derive compensate "$KEY" --project P123 --reason "demo: roll it back")"; echo "$out" | sed -n 1,2p
  expect "dry run: nothing written" "$out"
  out="$(as demo tl derive compensate "$KEY" --project P123 --reason "demo: roll it back" --apply)"; echo "$out"
  expect "compensated 40 records" "$out"
  driver published 40 after-compensation
  out="$(as demo tl derive show "$KEY" --project P123)"
  expect "state Valid" "$out"

  step "[$backend] clause 6: users and agents cannot publish; an agent's proposal waits for a person"
  as amy tl doc register ISD-002 --project P123 --title "Equipment list, unit 47" >/dev/null
  as amy tl doc rev create ISD-002 --project P123 --purpose "First issue" >/dev/null
  as amy tl derive open ISD-002 A --schema equipment-list --project P123 >/dev/null
  as amy tl derive content "$EQKEY" "$SAMPLES/equipment-list@1.0.0.sample.csv" --project P123 >/dev/null
  as amy tl derive start "$EQKEY" --project P123 >/dev/null
  as amy $derive_worker >/dev/null
  out="$(as amy tl derive show "$EQKEY" --project P123)"; expect "state Valid" "$out"
  driver refused
  driver propose
  proposal="$(cat "$TL_DEMO_STATE")"
  out="$(as demo tl proposal ls --project P123)"; echo "$out"
  expect "$proposal" "$out"
  refuse "needs the admin role" as amy tl proposal accept "$proposal"
  out="$(as demo tl derive show "$EQKEY" --project P123)"; expect "state Valid" "$out"
  out="$(as demo tl proposal accept "$proposal")"; echo "$out"
  expect "accepted" "$out"
  out="$(as demo tl derive show "$EQKEY" --project P123)"; echo "$out" | sed -n 1,2p
  expect "state Published" "$out"
  expect "published 10 records" "$out"
  echo "PASS 6b: the agent's proposal needed an admin to accept it; accepted, it created 10 tags"

  step "[$backend] clause 7: the API, the TUI and an agent show the same derived document"
  driver reads

  step "[$backend] clause 8: a pattern that never finishes ends as validation_limit; the worker goes on"
  as demo tl derive schema register "$workdir/hostile.yaml" --company >/dev/null
  for n in 3 4; do
    as amy tl doc register "ISD-00$n" --project P123 --title "Hostile test $n" >/dev/null
    as amy tl doc rev create "ISD-00$n" --project P123 --purpose "test" >/dev/null
    as amy tl derive open "ISD-00$n" A --schema hostile-pattern --project P123 >/dev/null
  done
  as amy tl derive content "ISD-003@A/hostile-pattern" "$workdir/hostile.csv" --project P123 >/dev/null
  as amy tl derive content "ISD-004@A/hostile-pattern" "$workdir/fine.csv" --project P123 >/dev/null
  as amy tl derive start "ISD-003@A/hostile-pattern" --project P123 >/dev/null
  as amy tl derive start "ISD-004@A/hostile-pattern" --project P123 >/dev/null
  started=$SECONDS
  out="$(as amy tl derive worker --once --timeout 3)"; echo "$out"
  [ $((SECONDS - started)) -lt 90 ] || fail "the hostile pattern held the worker"
  expect "worker done: ran=2" "$out"
  out="$(as amy tl derive jobs --project P123 --state failed)"; echo "$out"
  expect "validation_limit" "$out"
  out="$(as amy tl derive show ISD-004@A/hostile-pattern --project P123)"
  expect "state Valid" "$out"
  echo "PASS 8: the hostile pattern failed its job with validation_limit; the next job ran and passed"

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I3 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
