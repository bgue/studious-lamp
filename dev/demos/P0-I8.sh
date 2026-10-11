#!/usr/bin/env bash
# Demo for P0-I8 and the Phase 0 exit (brief 16): `just demo P0-I8`.
#
# One simulated project (a seeded team plays three working days through the API), then the four
# exit clauses on it, each ending in a PASS line:
#   1  create, link and set psets on a generic record in the TUI (headless pilot), the REST API and
#      MCP (an agent proposes, a person accepts: MCP writes are propose-only);
#   2  live updates between two TUIs (two remote clients on one server; one writes, the other sees);
#   3  an external webhook receiver (a loopback HTTP server standing in for one) gets a signed event
#      for a filtered subscription and verifies the signature;
#   4  a full restore from backup: the ledger archive is sealed, verified and replayed into a new
#      database (and into a scratch Postgres database when one is reachable); the restored state
#      equals the original and both ledgers verify.
# Extras: a settings change that applies live without a restart, and extension-type records
# (a company type package registered while the server runs, instances over REST, a body over MCP).
#
# Starts `tl serve` on a free loopback port over a temporary ledger; nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met. Takes about 2 minutes.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
stop_server() { # the server has its own process group (setsid): stop the whole group
  [ -n "$server_pid" ] || return 0
  kill -TERM -- "-$server_pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    curl -fs "${TL_API_URL:-http://127.0.0.1:1}/health" >/dev/null 2>&1 || break
    sleep 0.1
  done
  kill -KILL -- "-$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
  server_pid=""
}
trap 'stop_server; rm -rf "$workdir"' EXIT

export TL_ENV="${TL_ENV:-dev}"
export TL_DB="$workdir/tl.db"
export TL_TOKENS="$workdir/tokens.json"
export TL_SIM_DIR="$workdir/sim"
export TL_OBJECT_ROOT="$workdir/objects"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_WEBHOOK_ALLOWLIST

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }

step "an empty ledger, the API on a free loopback port, and a simulated project (3 working days)"
tl init >/dev/null
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
export TL_API_URL="http://127.0.0.1:$port"
setsid uv run tl serve --port "$port" >"$workdir/server.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 100); do
  curl -fs "$TL_API_URL/health" >/dev/null 2>&1 && break
  sleep 0.1
done
curl -fs "$TL_API_URL/health" | grep -q '"status":"ok"' || {
  cat "$workdir/server.log" >&2
  fail "the server did not start"
}
time_start=$SECONDS
tl sim seed --scale xs --run-id exit
echo "(seeded in $((SECONDS - time_start)) s)"
for who in user:alice user:bob agent:triage; do
  name="${who#*:}"
  export "TL_DEMO_TOKEN_${name^^}=$(tl dev token add "$who")"
done

step "the exit clauses (driver: dev/demos/p0_i8_demo.py)"
export TL_DEMO_WORK="$workdir"
export TL_DEMO_SCOPE="project:sim-exit"
quiet uv run python dev/demos/p0_i8_demo.py || fail "an exit clause was not met"

echo
echo "P0-I8 demo OK: every exit clause above printed PASS"
