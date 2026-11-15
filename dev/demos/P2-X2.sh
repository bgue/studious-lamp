#!/usr/bin/env bash
# Demo for P2-X2 (agent scope: filing check, queue cap, stop switch, P2-X2-T01 to T06): `just demo P2-X2`.
#
# The six clauses (docs/tickets/P2-X2/README.md, "Demo"), each ending in a `PASS clause N: ...`
# line that is printed only after its check returned success:
#   1  an agent without the module `user` word on the scope files: refused, the text of a missing
#      scope;
#   2  with the word (`tl admin roles grant`) it files; a person without the word cannot accept it;
#   3  the project queue cap (`tl config set ai.agents.max_pending_per_project`) is reached: the
#      next filing is refused with the fixed text, which shows no count;
#   4  `tl agent stop`: new filings refused with the stop text, pending ones show as held
#      (`tl agent stopped`), accept refused;
#   5  `tl agent resume` lifts both; the ledger shows `Agent.Stopped` then `Agent.Resumed`, the hash
#      chain still verifies (`tl ledger verify`), nothing rewritten;
#   6  the held count and the stopped list, read as five kinds of reader, name no hidden record and
#      count none.
#
# The admin acts are `tl` commands; the agent's filings and the five-reader read are the Python
# driver dev/demos/p2_x2_demo.py. Backends: `TL_DEMO_BACKENDS` is a space-separated list, default
# "sqlite postgres". Postgres is a throw-away database on TL_PG_URL (`just dev up`), dropped
# afterwards; an unreachable server is a failure, not a skip. The API is `tl serve` on a free
# loopback port over a temporary ledger, stopped afterwards. Nothing is left behind. Exits non-zero
# (and prints DEMO FAILED) when any clause is not met.
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
export P2_X2_WORKDIR="$workdir"
export TL_LAKE_DIR="$workdir/lake"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
clause() { echo "PASS clause $1: $2"; }
driver() { # driver MODE: the agent's filings and the five-reader read; its output is shown
  uv run python dev/demos/p2_x2_demo.py "$@" 2>"$workdir/driver.err" \
    || { grep -v 'UV_NATIVE_TLS' "$workdir/driver.err" >&2; fail "a clause was not met: $*"; }
}
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}

run_backend() {
  local backend="$1" api_port api_url out pid_a pid_b held
  step "[$backend] a new ledger, the people, the agent, the API on a free loopback port"
  drop_pg
  rm -rf "$workdir/objects" "$workdir/lake" "$workdir"/session-* "$workdir"/*.db "$workdir"/*.id \
    "$workdir/agent-token" "$workdir/held-expected" "$workdir"/accept-*.err
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
  printf '%s\n' "a long passphrase for dora" | as demo tl admin user add dora --display-name "Dora" --role user --role document_controller --password-stdin >/dev/null
  printf '%s\n' "a long passphrase for amy" | as amy tl login amy --password-stdin >/dev/null
  as demo tl admin user add triage --kind agent >/dev/null
  # the agent token is written to a file the driver reads; it is never printed
  as demo tl admin token issue triage --label p2-x2-demo >"$workdir/agent-token" 2>"$workdir/token.err" \
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

  step "[$backend] clause 1: the agent has no module word on project:P1; a missing scope gets the same refusal"
  driver clause1
  clause 1 "no word on project:P1 is refused with the text of a scope that does not exist"

  step "[$backend] clause 2: the grant, the agent files, a person without the word cannot accept"
  out="$(as demo tl admin roles grant triage --project P1 --module '*' --role user --reason "demo grant")"
  [ "$out" = "granted user on * for project:P1 to triage" ] || fail "tl admin roles grant printed: $out"
  echo "$out"
  driver clause2
  pid_a="$(read -r line <"$workdir/proposal-a.id"; echo "$line")"
  if as amy tl proposal accept "$pid_a" --actor user:amy >/dev/null 2>"$workdir/accept-amy.err"; then
    fail "amy, without the word, accepted $pid_a"
  fi
  [ -s "$workdir/accept-amy.err" ] || fail "amy's accept refusal printed nothing"
  clause 2 "with the word the agent files (pending); amy without the word cannot accept it"

  step "[$backend] clause 3: the queue cap is 2 for project:P1; the next filing is refused with the fixed text"
  out="$(as demo tl config set ai.agents.max_pending_per_project 2 --project P1 --reason "demo queue cap")"
  echo "$out"
  driver clause3
  pid_b="$(read -r line <"$workdir/proposal-b.id"; echo "$line")"
  clause 3 "the cap refuses the filing past two pending with the fixed text, no count in it"

  step "[$backend] clause 4: tl agent stop; new filings refused; pending ones held; accept refused"
  out="$(as demo tl agent stop triage --reason "demo stop")"
  [ "$out" = "stopped agent:triage" ] || fail "tl agent stop printed: $out"
  echo "$out"
  if as demo tl proposal accept "$pid_a" --actor user:demo >/dev/null 2>"$workdir/accept-stopped.err"; then
    fail "a stopped agent's proposal $pid_a was accepted"
  fi
  driver clause4
  held="$(read -r line <"$workdir/held-expected"; echo "$line")"
  as demo tl agent stopped | grep -Eq "^agent:triage  since .*  by user:demo  held ${held}  demo stop$" \
    || fail "tl agent stopped does not show held $held"
  as demo tl agent stopped
  clause 4 "new filing refused with the stop text; tl agent stopped shows held $held; accept refused"

  step "[$backend] clause 5: tl agent resume; the agent files again; accept works; the ledger verifies"
  out="$(as demo tl agent resume triage)"
  [ "$out" = "resumed agent:triage" ] || fail "tl agent resume printed: $out"
  echo "$out"
  out="$(as demo tl proposal accept "$pid_b" --actor user:demo)"
  printf '%s\n' "$out" | grep -q "^accepted $pid_b$" || fail "the accept after resume printed: $out"
  echo "$out"
  driver clause5
  tl ledger verify >"$workdir/verify.out" 2>&1 || { cat "$workdir/verify.out" >&2; fail "the hash chain does not verify"; }
  tail -n 1 "$workdir/verify.out"
  clause 5 "resume lifts both; accept works; Agent.Stopped then Agent.Resumed; the hash chain verifies"

  step "[$backend] clause 6: tl agent stop again; five readers read the held count and the stopped list"
  out="$(as demo tl agent stop triage --reason "clause 6 review")"
  [ "$out" = "stopped agent:triage" ] || fail "tl agent stop printed: $out"
  driver clause6
  clause 6 "five readers: held 1, 1, 1, 1, 2 (named); the stopped list names no hidden record"

  stop_server
  drop_pg
  echo "[$backend] clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P2-X2 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
