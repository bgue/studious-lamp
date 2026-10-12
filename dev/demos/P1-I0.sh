#!/usr/bin/env bash
# Demo for P1-I0 (identity and admin, Postgres for the services): `just demo P1-I0`.
#
# The FANOUT exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  demo/demo signs in (TUI sign-in screen, headless, and the API) and creates a record;
#   2  a `user` is refused an admin action;
#   3  an admin creates a user and issues an agent token, and the agent proposes over MCP;
#   4  repeated bad passwords lock an account (and only a local `tl admin unlock` frees it);
#   5  the demo account refuses a non-loopback bind.
# Extras: the CLI session (`tl login`), `TL_ENV=prod` refusing the demo account, and a token
# revoked while the MCP server runs.
#
# Backends: `TL_DEMO_BACKENDS` is a space-separated list, default "sqlite postgres". Postgres is a
# throw-away database on TL_PG_URL (default postgresql://postgres:postgres@localhost:5432/tl_test,
# `just dev up`), dropped afterwards; an unreachable server is a failure, not a skip. Starts
# `tl serve` on a free loopback port over a temporary ledger; nothing is left behind.
# Exits non-zero (and prints DEMO FAILED) when any clause is not met. Takes about 3 minutes.
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
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i0_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}

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
  grep -q "demo/demo" "$workdir/init.err" || fail "tl init --dev did not warn about the demo account"
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

  step "[$backend] clause 1: demo signs in and creates a record (TUI headless, API)"
  driver signin
  printf 'demo\n' | as demo tl login demo --password-stdin
  as demo tl whoami
  as demo tl record create --project P123 --key DEMO-3 --title "Created from the CLI by demo"
  [ "$(quiet uv run python dev/demos/p1_i0_demo.py actors DEMO-3)" = "user:demo" ] || fail "the CLI record is not by user:demo"
  echo "PASS 1: the CLI session acts as user:demo too"

  step "[$backend] an admin creates a user and an agent (the CLI session of demo)"
  export TL_DEMO_AMY_PASSWORD="a long passphrase for amy"
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as demo tl admin user add amy --display-name "Amy A" --password-stdin
  as demo tl admin user add triage --kind agent
  TL_DEMO_AGENT_TOKEN="$(as demo tl admin token issue triage --label demo 2>"$workdir/issue.err")"
  export TL_DEMO_AGENT_TOKEN
  cat "$workdir/issue.err"
  case "$TL_DEMO_AGENT_TOKEN" in tla_*) ;; *) fail "no agent token was issued" ;; esac
  as demo tl admin user ls
  as demo tl admin token ls

  step "[$backend] clause 2: a user is refused an admin action"
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin
  if out="$(as amy tl admin user ls 2>&1)"; then fail "amy ran an admin command"; fi
  echo "$out"
  case "$out" in *"needs the admin role"*) ;; *) fail "the CLI refusal is not the admin-role message" ;; esac
  driver refused

  step "[$backend] clause 3: the agent proposes over MCP; a person decides"
  driver agent

  step "[$backend] clause 4: repeated bad passwords lock the account"
  driver lock
  as demo tl admin audit --username amy --limit 3
  as demo tl admin unlock amy
  printf '%s\n' "$TL_DEMO_AMY_PASSWORD" | as amy tl login amy --password-stdin
  echo "(unlocked locally, and amy signed in again)"

  step "[$backend] clause 5: the demo account refuses a non-loopback bind"
  if out="$(uv run tl serve --host 0.0.0.0 --port "$port" --insecure-dev 2>&1)"; then
    fail "the server started on a non-loopback address while demo was enabled"
  fi
  echo "$out" | grep -v UV_NATIVE_TLS
  case "$out" in *"demo account"*) ;; *) fail "the refusal does not name the demo account" ;; esac
  echo "PASS 5: a non-loopback bind is refused while demo is enabled"
  if out="$(TL_ENV=prod uv run tl init --dev 2>&1)"; then fail "tl init --dev worked with TL_ENV=prod"; fi
  echo "$out" | grep -v UV_NATIVE_TLS
  echo "PASS 5: and the demo account is never created when TL_ENV=prod"

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I0 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
