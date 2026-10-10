#!/usr/bin/env bash
# Demo for P0-I6 (feed and hashtags, MCP write tools, simulator v0). Run with `just demo P0-I6`.
# One simulated project day, seen through all three workstreams, on a temporary ledger and API:
#   C  a seeded team (document controller, planner, crew) plays a working day through the API as
#      user:sim-* identities, and an agent (agent:sim-assistant) files a proposal over MCP;
#   A  the crew's posts are in the project feed (CLI and a remote TUI), their #KEY tags suggested
#      `references` links and changed no record, and the burst of new records is one event card;
#   B  the agent's proposal waits in the review queue, the agent cannot write a record or decide,
#      and a person accepts it from the CLI: the link is made by that person on the agent's say;
#   C  sim_assert is green, and the same seed on a second empty ledger writes identical ground truth.
# Nothing is left behind. Exits 1 when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
root="$(mktemp -d)"
server_pid=""
stop_server() { # the server has its own process group (setsid): stop the whole group
  [ -n "$server_pid" ] || return 0
  kill -TERM -- "-$server_pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    curl -fs "$TL_API_URL/health" >/dev/null 2>&1 || break
    sleep 0.1
  done
  kill -KILL -- "-$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
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
refuse() { # refuse <description> <command...>: the command must fail; its output is printed
  local what="$1"
  shift
  if "$@" >"$root/refused.out" 2>&1; then
    echo "DEMO FAILED: $what was accepted" >&2
    exit 1
  fi
  cat "$root/refused.out"
}
json() { python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }
token_of() { json "print(next(t for t, a in d.items() if a == '$1'))" <"$TL_TOKENS"; }
api() { curl -fs -H "Authorization: Bearer $(token_of "$1")" "$TL_API_URL$2"; }

# The live scenario: the bundled one with no approver, so the proposal waits for a person.
cat >"$root/live.yaml" <<'YAML'
scenario: p0-i6-live
seed: 4711
start: 2026-11-02
template: small-piping
actors:
  assistant: {proposals_per_day: 1}
YAML

# new_world <name>: a fresh ledger, tokens and run directory, and the API on a free port.
new_world() {
  local dir="$root/$1"
  mkdir -p "$dir"
  export TL_DB="$dir/tl.db" TL_TOKENS="$dir/tokens.json" TL_SIM_DIR="$dir/sim"
  tl init >/dev/null
  local port
  port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
  export TL_API_URL="http://127.0.0.1:$port"
  setsid uv run tl serve --port "$port" >"$dir/server.log" 2>&1 &
  server_pid=$!
  for _ in $(seq 1 100); do
    curl -fs "$TL_API_URL/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  expect "$(curl -fs "$TL_API_URL/health")" '"status":"ok"'
}

step "C: the API on an empty ledger; a seeded team plays one working day"
new_world one
out="$(tl sim create "$root/live.yaml")"
run="$(head -n1 <<<"$out" | cut -d' ' -f2)"
project="sim-$run"
scope="project:$project"
out="$(tl sim advance --days 1)"
echo "$out"
expect "$out" '^played 2026-11-02$'
valves="$(api user:sim-orchestrator "/records?scope=$scope&q=title~Valve&limit=50" | json "print(len(d))")"
echo "$valves valve records, read back through the API"
[ "$valves" -ge 1 ]

step "A: the crew's post is in the project feed, and its #KEY tags did not change the records"
out="$(tl feed ls --project "$project" --posts)"
echo "$out"
expect "$out" ' sim-crew  Installed [0-9]+ valves?: #SIMR'
valve_key="$(api user:sim-orchestrator "/records?scope=$scope&q=title~Valve&limit=1" | json "print(d[0]['key'])")"
out="$(tl feed ls --project "$project" --record "$valve_key" --posts)"
echo "$out"
expect "$out" "Installed .*#$valve_key"
out="$(tl link list --project "$project" "$valve_key")"
echo "$out"
expect "$out" 'referenced by .* suggested'
expect "$(tl record show --project "$project" "$valve_key")" '^version: [0-9]+$'

step "A: ledger activity is aggregated into event cards, one run per actor and kind of change"
out="$(tl feed ls --project "$project" --events)"
echo "$out"
expect "$out" ' card .* created [0-9]+ records'

step "A: the same feed in a remote TUI (headless), over the API's SSE stream"
export TL_DEMO_URL="$TL_API_URL" TL_DEMO_SCOPE="$scope"
TL_DEMO_TOKEN="$(token_of user:sim-orchestrator)" quiet uv run python dev/demos/p0_i6_demo.py >"$root/tui.txt"
grep -E 'Installed|Registered' "$root/tui.txt" | head -n 4
echo "(the remote TUI showed the crew's and the document controller's posts)"

step "B: the agent's proposal waits in the review queue; nothing has changed"
out="$(tl proposal ls --project "$project")"
echo "$out"
expect "$out" '  pending  agent:sim-assistant  link_records  '
proposal="$(head -n1 <<<"$out" | cut -d' ' -f1)"
before="$(api user:sim-orchestrator "/events?scope=$scope&limit=500" | json "print(sum(1 for e in d['events'] if e['event_type'] == 'Link.Added'))")"

step "B: the agent cannot write a record or decide (HTTP 403 agent_must_propose)"
agent_token="$(token_of agent:sim-assistant)"
code="$(curl -s -o "$root/refused.json" -w '%{http_code}' -X POST -H "Authorization: Bearer $agent_token" \
  -H 'content-type: application/json' \
  -d "{\"scope\":\"$scope\",\"record_type\":\"core.Record\",\"title\":\"By an agent\",\"key\":\"AGENT-1\"}" \
  "$TL_API_URL/commands/CreateRecord")"
echo "POST /commands/CreateRecord as the agent -> $code $(json "print(d['error'])" <"$root/refused.json")"
[ "$code" = 403 ]
code="$(curl -s -o "$root/refused.json" -w '%{http_code}' -X POST -H "Authorization: Bearer $agent_token" \
  -H 'content-type: application/json' -d '{"roles":[]}' "$TL_API_URL/proposals/$proposal/accept")"
echo "POST /proposals/<id>/accept as the agent -> $code"
[ "$code" -ge 400 ]

step "B: a person accepts it from the CLI; the link is made by that person on the agent's say"
out="$(tl proposal accept "$proposal" --actor user:sim-approver)"
echo "$out"
expect "$out" "^accepted $proposal$"
after="$(api user:sim-orchestrator "/events?scope=$scope&limit=500" | json "print(sum(1 for e in d['events'] if e['event_type'] == 'Link.Added'))")"
echo "Link.Added events: $before before, $after after"
[ "$after" -eq $((before + 1)) ]
api user:sim-orchestrator "/events?scope=$scope&limit=500" | json "
made = [e for e in d['events'] if e['event_type'] == 'Link.Added'][-1]
print('made by', made['actor'], 'with source', made['source'])
assert made['actor'] == 'user:sim-approver' and made['source'].startswith('mcp:sim-assistant')
"

step "C: sim_assert: the suite holds what the team intended"
out="$(tl sim assert 2>&1)" || { echo "$out"; echo "DEMO FAILED: sim_assert" >&2; exit 1; }
echo "$out"
expect "$out" '^ok: [0-9]+ checks$'
digest_one="$(tl sim status | grep '^digest:')"
echo "$digest_one"
stop_server

step "C: the same seed on a second, empty ledger writes the identical ground truth"
new_world two
tl sim create "$root/live.yaml" >/dev/null
tl sim advance --days 1 >/dev/null
digest_two="$(tl sim status | grep '^digest:')"
echo "$digest_two"
if [ "$digest_one" != "$digest_two" ]; then
  echo "DEMO FAILED: the ground-truth digests differ" >&2
  exit 1
fi
cmp "$root/one/sim/$run/ground_truth.ndjson" "$TL_SIM_DIR/$run/ground_truth.ndjson"
echo "ground_truth.ndjson is byte-identical"

echo
echo "P0-I6 demo ok"
