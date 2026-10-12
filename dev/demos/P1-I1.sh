#!/usr/bin/env bash
# Demo for P1-I1 (M2 Engineering Data: standards registry, numbering patterns, Tag and TagClass):
# `just demo P1-I1`.
#
# The exit clauses, each ending in a PASS line, once on SQLite and once on Postgres:
#   1  an admin loads the company standards (dry run first); a second load changes nothing;
#   2  `tl tag create 47-FV-2001 --class ControlValve` parses the segments (47, FV, 2001) and shows
#      the missing valve_data as non-conformant; `47-XX-1` is refused with every problem;
#   3  filling in valve_data makes the tag conform (the class binds the property set);
#   4  a rename creates a new tag that supersedes the old one, which leaves service;
#   5  a legacy tag list is previewed as a diff and applied (admin only); bad numbers stay as
#      violations; a number a superseded tag holds is refused in the preview; the three base reports
#      read them;
#   6  a user cannot change the registry, edit a tag class generically or set `origin`;
#   7  the API, the TUI tag register (F8) and an agent's MCP tools read the same tags.
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
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT TL_AGENT_TOKEN TL_SIM_AGENT_TOKEN

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
fail() { echo "DEMO FAILED: $*" >&2; exit 1; }
driver() { quiet uv run python dev/demos/p1_i1_demo.py "$@" || fail "an exit clause was not met"; }
as() { # as NAME cmd...: run a command with that person's CLI session
  local who="$1"; shift
  TL_SESSION_FILE="$workdir/session-$who.json" "$@"
}
expect() { # expect TEXT OUTPUT: the output must contain the text
  case "$2" in *"$1"*) ;; *) echo "$2"; fail "expected to see: $1" ;; esac
}

STANDARDS=schema/fixtures/standards/co.acme.standards@1.0.0.yaml
MAPPING=dev/seed/templates/tag-list-instrument-index.yaml
LEGACY=dev/seed/legacy/instrument-index.csv

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

  step "[$backend] clause 1: an admin loads the company standards; a second load changes nothing"
  out="$(as demo tl standards load "$STANDARDS" --dry-run)"; echo "$out"
  expect "plan co.acme.standards@1.0.0" "$out"
  out="$(as demo tl standards load "$STANDARDS")"; echo "$out"
  expect "loaded co.acme.standards@1.0.0" "$out"
  as demo tl standards ls --kind code-list
  as demo tl standards values Area
  out="$(as demo tl standards load "$STANDARDS")"
  case "$out" in *"create=0"*"create=0"*"create=0"*"create=0"*"create=0"*) ;; *) echo "$out"; fail "a second load created entries" ;; esac
  as demo tl standards class ls
  echo "PASS 1: the standards are in the registry, and loading them again is a no-op"

  step "[$backend] clause 2: a tag number is parsed; a wrong one is refused with every problem"
  out="$(as demo tl tag create 47-FV-2001 --class ControlValve --service "Feed gas flow control" --project P123)"; echo "$out"
  expect "segments area=47 mnemonic=FV seq=2001" "$out"
  expect "conformance nonconformant" "$out"
  expect "valve_data" "$out"
  if out="$(as demo tl tag create 47-XX-1 --project P123 2>&1)"; then fail "47-XX-1 was accepted"; fi
  echo "$out"
  expect "mnemonic" "$out"
  expect "seq" "$out"
  echo "PASS 2: 47-FV-2001 is parsed and non-conformant; 47-XX-1 is refused"

  step "[$backend] clause 3: the class binds the property set; filling it in makes the tag conform"
  as demo tl pset set --project P123 47-FV-2001 valve_data manufacturer=Acme size_in=4
  out="$(as demo tl tag show 47-FV-2001 --project P123)"; echo "$out"
  expect "conformance: ok" "$out"
  echo "PASS 3: valve_data satisfies the class"

  step "[$backend] clause 4: a rename creates a new tag that supersedes the old one"
  as demo tl tag rename 47-FV-2001 47-FV-2002 --reason "renumbered by the design office" --project P123
  out="$(as demo tl tag ls --project P123)"; echo "$out"
  expect "47-FV-2002" "$out"
  case "$out" in *"47-FV-2001"*) fail "the old tag is still in service" ;; esac
  out="$(as demo tl tag ls --project P123 --all)"; echo "$out"
  expect "47-FV-2001" "$out"
  echo "PASS 4: 47-FV-2001 was replaced by 47-FV-2002 (the old one is kept as Superseded)"

  step "[$backend] clause 5: a legacy list is previewed and applied (admin only); bad numbers stay as violations"
  out="$(as demo tl tag import "$LEGACY" --mapping "$MAPPING" --project P123)"; echo "$out"
  expect "dry run: nothing written" "$out"
  expect "invalid=3" "$out"
  if out="$(as amy tl tag import "$LEGACY" --mapping "$MAPPING" --project P123 --apply --skip-invalid 2>&1)"; then fail "a user applied an import"; fi
  echo "$out"
  expect "needs the admin role" "$out"
  out="$(as demo tl tag import "$LEGACY" --mapping "$MAPPING" --project P123 --apply --skip-invalid)"; echo "$out" | tail -n 3
  expect "applied instrument-index: created=11" "$out"
  printf 'TAG NO,SERVICE,TYPE,SIZE (IN),MATERIAL,MFR,FAIL,FAT WITNESS\n47-FV-2001,Reused number,CV,4,CS,Acme,FC,\n' >"$workdir/reuse.csv"
  out="$(as demo tl tag import "$workdir/reuse.csv" --mapping "$MAPPING" --project P123)"
  echo "$out" | grep -E '^(import|new=|!)'
  expect "key '47-FV-2001' is already used by a superseded tag" "$out"
  as demo tl tag report summary --project P123
  out="$(as demo tl tag report violations --project P123)"; echo "$out"
  expect "FV1009" "$out"
  as demo tl tag report missing --project P123 | head -n 5
  echo "PASS 5: 11 tags imported, 3 rows refused, the legacy numbers kept as violations"

  step "[$backend] clause 6: a user cannot change the registry"
  if out="$(as amy tl standards load "$STANDARDS" 2>&1)"; then fail "a user loaded the standards"; fi
  echo "$out"
  expect "needs the admin role" "$out"
  driver refused

  step "[$backend] clause 7: the API, the TUI tag register and an agent read the same tags"
  export TL_DEMO_TAG=47-FV-2002
  driver reads

  stop_server
  drop_pg
  echo "[$backend] all clauses passed"
}

for backend in ${TL_DEMO_BACKENDS:-sqlite postgres}; do
  run_backend "$backend"
done

echo
echo "P1-I1 demo OK on: ${TL_DEMO_BACKENDS:-sqlite postgres}"
