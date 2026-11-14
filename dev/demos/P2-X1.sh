#!/usr/bin/env bash
# Demo for P2-X1 (idempotency keys at the edges, P2-X1-T01 to T08): `just demo P2-X1`.
#
# The six clauses (docs/tickets/P2-X1/README.md, "Demo"), each ending in a `PASS clause N: ...`
# line that is printed only after its check returned success:
#   1  one actor sends one command twice with one Idempotency-Key: one event set, the same answer;
#   2  same key, other body: 409 idempotency_mismatch with the fixed text and nothing written; two
#      concurrent sends of one key write once and never answer 500;
#   3  an agent's keyed filing: its HTTP create is refused (403 agent_must_propose, nothing stored);
#      its MCP create_record sent twice with one key gives one proposal row;
#   4  another actor with the same key value neither sees nor collides with the first actor's entry;
#   5  after the actor's clearance drops, a replay answers as a record that never existed (404, the
#      same text as a missing id);
#   6  a removed response field fails `tl_api.openapi --compat`; an added optional field passes.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Both run all six
# clauses. Postgres is a throw-away database on TL_PG_URL (default
# postgresql://postgres:postgres@localhost:5432/tl_test, `just dev up`), dropped afterwards; an
# unreachable server is a failure, not a skip. The API is `tl serve` on a free loopback port over a
# temporary ledger, stopped afterwards. Nothing is left behind. Exits non-zero (and prints
# DEMO FAILED) when any clause is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
pg_url=""
stop_group() { # stop a process group started with setsid
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || true
  sleep 0.2
  kill -KILL -- "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
stop_server() {
  stop_group "$server_pid"
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
export P2_X1_WORKDIR="$workdir"
export TL_LAKE_DIR="$workdir/lake"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { # driver MODE: the HTTP, in-process and compat checks; their output is shown, stderr kept
  uv run python dev/demos/p2_x1_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "a clause was not met: $*"; }
}
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}

run_backend() {
  local backend="$1" api_port api_url
  step "[$backend] a new ledger, the people, the agent, the API on a free loopback port"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake" "$workdir"/session-* "$workdir"/*.db "$workdir/agent-token"
  case "$backend" in
    sqlite) export TL_DB="$workdir/$backend.db" ;;
    postgres)
      pg_url="$(quiet uv run python dev/demos/p1_i0_demo.py pg-create)" || fail "Postgres is not reachable at TL_PG_URL (try: just dev up)"
      export TL_DB="$pg_url"
      ;;
    *) fail "unknown backend $backend" ;;
  esac
  tl init --dev 2>"$workdir/init.err" >/dev/null || { cat "$workdir/init.err" >&2; fail "tl init --dev"; }
  printf 'demo\n' | as demo tl login demo --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for amy" | as demo tl admin user add amy --display-name "Amy" --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for bob" | as demo tl admin user add bob --display-name "Bob" --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  # the agent token is written to a file the driver reads; it is never printed
  as demo tl admin token issue triage --label p2-x1-demo >"$workdir/agent-token" 2>"$workdir/token.err" \
    || { cat "$workdir/token.err" >&2; fail "tl admin token issue"; }
  api_port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  api_url="http://127.0.0.1:$api_port"
  export TL_API_URL="$api_url"
  setsid uv run tl serve --port "$api_port" >"$workdir/server-$backend.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 150); do
    curl -fs "$api_url/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$api_url/health" | grep -q '"status":"ok"' || { cat "$workdir/server-$backend.log" >&2; fail "the server did not start"; }
  echo "(serving $backend at $api_url)"

  step "[$backend] clause 1: amy sends one command twice with one key"
  driver clause1
  clause 1 "one key, one body, sent twice by amy: one event set, the same answer"

  step "[$backend] clause 2: same key with another body is refused; two concurrent sends of one key"
  driver clause2
  clause 2 "same key, other body: 409 idempotency_mismatch, nothing written; concurrent sends: one record, no 500"

  step "[$backend] clause 3: the agent's HTTP create is refused; its MCP proposal twice with one key"
  driver clause3
  clause 3 "the agent's HTTP create refused (403 agent_must_propose); MCP create_record twice with one key: one proposal"

  step "[$backend] clause 4: bob's same key value does not collide with amy's entry"
  driver clause4
  clause 4 "bob's same key gives his own record; amy's replay still answers her record"

  step "[$backend] clause 5: after the clearance drops, the replay answers as a missing record"
  driver clause5
  clause 5 "the replay after the clearance drop answers 404 with the text of a missing id; no title"

  step "[$backend] clause 6: the compat step fails a removed response field and passes an added optional one"
  quiet uv run python -m tl_api.openapi --compat || fail "the real --compat did not exit 0"
  echo "(the real --compat: exit 0)"
  driver clause6
  clause 6 "a removed CommandResult field fails --compat (exit 1); an added optional field passes (exit 0)"

  stop_server
  drop_pg
  echo "[$backend] clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-X1 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
