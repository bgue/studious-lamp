#!/usr/bin/env bash
# Demo for P0-I6 workstream C (simulator v0). Run with `just demo P0-I6-C` from the repository root.
# Starts the API on a free loopback port over a temporary ledger, creates a simulated project, plays one
# working day through the API, shows the crew's records and posts as the API serves them, runs
# `tl sim assert` (green), plays the same seed on a second fresh ledger to get the identical ground
# truth, and shows the assertion fail when a person adds a record. Nothing is left behind. Exits 1
# when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
root="$(mktemp -d)"
server_pid=""
stop_server() {
  if [ -n "$server_pid" ]; then kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true; fi
  server_pid=""
}
trap 'stop_server; rm -rf "$root"' EXIT
export TL_ENV="${TL_ENV:-dev}"
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_SEED_DIR

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
json() { python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }

# new_world <name>: a fresh ledger, token file and run directory, and the API on a free port.
new_world() {
  local dir="$root/$1"
  mkdir -p "$dir"
  export TL_DB="$dir/tl.db" TL_TOKENS="$dir/tokens.json" TL_SIM_DIR="$dir/sim"
  tl init >/dev/null
  local port
  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  export TL_API_URL="http://127.0.0.1:$port"
  quiet uv run tl serve --port "$port" >"$dir/server.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 100); do
    curl -fs "$TL_API_URL/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  expect "$(curl -fs "$TL_API_URL/health")" '"status":"ok"'
}

# api <path>: GET as the simulator's orchestrator identity.
api() {
  local token
  token="$(json "print(next(t for t, a in d.items() if a == 'user:sim-orchestrator'))" <"$TL_TOKENS")"
  curl -fs -H "Authorization: Bearer $token" "$TL_API_URL$1"
}

step "the API on an empty ledger, and a simulated project from a scenario"
new_world one
out="$(tl sim create north-unit-small)"
echo "$out"
expect "$out" '^run r[0-9a-f]{6}$'
expect "$out" '^seeded 8 records$'
run="$(head -n1 <<<"$out" | cut -d' ' -f2)"
scope="project:sim-$run"

step "one working day: three actors act through the API as user:sim-* identities"
out="$(tl sim advance --days 1)"
echo "$out"
expect "$out" '^played 2026-11-02$'
expect "$out" '^ground truth \+[0-9]+ '

step "the crew's valves arrived as records (read back through the API)"
valves="$(api "/records?scope=$scope&q=title~Valve&limit=50" | json "print(len(d))")"
echo "$valves valve records"
[ "$valves" -ge 1 ]
api "/records?scope=$scope&q=title~Valve&limit=3" |
  json "[print('  ', r['key'], r['title'], r['psets']['valve_data']['manufacturer']) for r in d]"
docs="$(api "/records?scope=$scope&q=title~Doc&limit=50" | json "print(len(d))")"
echo "$docs document records, submitted for review by the document controller"
[ "$docs" -ge 1 ]

step "the crew's posts are in the project feed, tagged with the new valve keys"
posts="$(api "/feed?scope=$scope&item_type=post&limit=50" |
  json "[print(i['actor'], '|', i['summary']) for i in d['items']]")"
echo "$posts"
expect "$posts" '^user:sim-crew \| Installed [0-9]+ valves?: #SIMR[0-9A-F]{6}-REC-'
expect "$posts" '^user:sim-document_controller \| Registered '

step "every simulator event carries simulated time, source sim:<run> and a simulated actor"
api "/events?scope=$scope&limit=500" | json "
ev = d['events']
assert ev, 'no events'
assert {e['source'] for e in ev} == {'sim:$run'}, {e['source'] for e in ev}
assert all(e['actor'].startswith('user:sim-') for e in ev)
assert all(e['effective_at'].startswith('2026-11-02') for e in ev)
assert all(e['effective_at'] != e['recorded_at'] for e in ev)
print(len(ev), 'events, effective_at', min(e['effective_at'] for e in ev)[:16], 'to', max(e['effective_at'] for e in ev)[:16])
"

step "sim_assert: the suite holds what the scenario intended"
out="$(tl sim assert)"
echo "$out"
expect "$out" '^ok: [0-9]+ checks$'
digest_one="$(tl sim status | grep '^digest:')"
echo "$digest_one"
cp "$TL_SIM_DIR/$run/ground_truth.ndjson" "$root/truth_one.ndjson"

step "a person adds a record to the simulated project: sim_assert names it and exits 1"
tl record create --project "sim-$run" --key STRAY-0001 --title "Added by a person" >/dev/null
if out="$(tl sim assert 2>&1)"; then
  echo "DEMO FAILED: sim_assert passed with a stray record" >&2
  exit 1
fi
echo "$out"
expect "$out" '^FAILED: '
expect "$out" 'unexpected_record STRAY-0001'
stop_server

step "the same seed on a second, empty ledger writes the identical ground truth"
new_world two
tl sim create north-unit-small >/dev/null
tl sim advance --days 1 >/dev/null
digest_two="$(tl sim status | grep '^digest:')"
echo "$digest_two"
if [ "$digest_one" != "$digest_two" ]; then
  echo "DEMO FAILED: the ground-truth digests differ" >&2
  exit 1
fi
cmp "$root/truth_one.ndjson" "$TL_SIM_DIR/$run/ground_truth.ndjson"
echo "ground_truth.ndjson is byte-identical ($(wc -l <"$root/truth_one.ndjson") lines)"
expect "$(tl sim assert)" '^ok: '

echo
echo "P0-I6-C demo ok"
