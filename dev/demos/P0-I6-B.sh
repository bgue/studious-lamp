#!/usr/bin/env bash
# Demo for P0-I6 workstream B (MCP write tools, the proposal review queue, the feed over the API).
# An MCP agent proposes two records, posts to the feed and is refused a fourth proposal (budget 3);
# nothing changes until a person accepts from the CLI or the API; the record is then made by that
# person, tagged with the agent as source and the proposal as cause; an agent cannot decide; a tool
# mode of `write` is refused. Run with `just demo P0-I6-B` from the repository root. Uses a temporary
# ledger, token file and API port; nothing is left behind. Fails (exit 1) when an expectation fails.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
cleanup() {
  [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null || true
  rm -rf "$workdir"
}
trap cleanup EXIT
export TL_DB="$workdir/tl.db"
export TL_TOKENS="$workdir/tokens.json"
export TL_ENV="${TL_ENV:-dev}"
export TL_AGENT_DAILY_PROPOSALS=3
unset TL_SCHEMA_DIR

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
py() { quiet uv run python dev/demos/p0_i6_b_demo.py "$@"; }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>: fail the demo if the pattern is missing
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}
refuse() { # refuse <description> <command...>: the command must fail; its stderr is printed
  local what="$1"
  shift
  if "$@" 2>"$workdir/refused.err"; then
    echo "DEMO FAILED: $what was accepted" >&2
    exit 1
  fi
  cat "$workdir/refused.err"
}

step "tl init, a person (alice), an agent (triage) and the API on a free loopback port"
tl init
alice="$(tl dev token add user:alice)"
robot="$(tl dev token add agent:triage)"
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
export TL_DEMO_URL="http://127.0.0.1:$port"
export TL_DEMO_TOKEN="$alice"
export TL_DEMO_AGENT_TOKEN="$robot"
quiet uv run python -m tl_api --port "$port" >"$workdir/server.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 100); do
  curl -fs "$TL_DEMO_URL/health" >/dev/null 2>&1 && break
  sleep 0.1
done
expect "$(curl -fs "$TL_DEMO_URL/health")" '"status":"ok"'
echo "listening on $TL_DEMO_URL; the agent's daily proposal budget is $TL_AGENT_DAILY_PROPOSALS"

step "the agent, over MCP: two record proposals, a post, a third proposal, then over budget"
out="$(py agent)"
echo "$out"
mapfile -t proposals < <(grep '^proposed ' <<<"$out" | cut -d' ' -f2)
[ "${#proposals[@]}" -eq 3 ]
post_id="$(grep '^posted ' <<<"$out" | cut -d' ' -f2)"
expect "$out" "^posted [0-9A-Z]{26} by agent:triage$"
expect "$out" "^refused .*agent:triage has used its 3 proposals"
expect "$out" "^records visible in project:P123: 0$"
first="${proposals[0]}"
second="${proposals[1]}"
third="${proposals[2]}"

step "nothing changed: no record exists, but the review queue holds three proposals"
refuse "a record that nobody accepted" tl record show --project P123 P123-REC-0001
out="$(tl proposal ls --project P123)"
echo "$out"
[ "$(wc -l <<<"$out")" -eq 3 ]
expect "$out" "^$first  pending  agent:triage  create_record  Create core.Record 'Weld NCR W-12: cracked bevel'"

step "the post is in the feed at once, labelled with the agent (a post is a message, not a record)"
out="$(tl feed ls --project P123 --posts)"
echo "$out"
expect "$out" "^$post_id  post .*  agent:triage !  Found a cracked bevel at weld W-12 #hold"

step "a person looks at a proposal, then accepts it"
out="$(tl proposal show "$first")"
echo "$out"
expect "$out" "^command CreateRecord$"
expect "$out" '^  title "Weld NCR W-12: cracked bevel"$'
out="$(tl proposal accept "$first" --actor user:alice)"
echo "$out"
expect "$out" "^accepted $first$"
out="$(tl record show --project P123 P123-REC-0001)"
echo "$out"
expect "$out" "title: Weld NCR W-12: cracked bevel"

step "the record was made by alice, on the agent's suggestion"
out="$(py provenance P123-REC-0001)"
echo "$out"
expect "$out" "^P123-REC-0001 created by user:alice source mcp:triage$"
expect "$out" "^caused by Proposal.Created $first from agent:triage$"

step "an agent cannot decide; a person rejects the duplicate with a reason"
refuse "an agent accepting" tl proposal accept "$second" --actor agent:triage
tl proposal reject "$second" --reason "Duplicate of the first" --actor user:alice
out="$(tl proposal ls --project P123 --status rejected)"
echo "$out"
expect "$out" "^$second  rejected"
refuse "accepting a rejected proposal" tl proposal accept "$second" --actor user:alice

step "over the API: the agent's token is refused, alice's accepts the third"
py api "$third"
out="$(tl record show --project P123 P123-REC-0002)"
expect "$out" "title: Re-inspect weld W-12 after repair"
curl -fs -H "Authorization: Bearer $alice" "$TL_DEMO_URL/proposals?scope=project:P123&all=true" | python3 -c '
import json, sys
rows = json.load(sys.stdin)
print(", ".join(row["status"] for row in rows))
assert [row["status"] for row in rows] == ["accepted", "rejected", "accepted"]'

step "a tool mode of write is refused: who may write directly is a human gate"
if quiet uv run python -m tl_mcp --actor agent:triage --tool-mode create_record=write 2>"$workdir/mode.err"; then
  echo "DEMO FAILED: write mode was accepted" >&2
  exit 1
fi
cat "$workdir/mode.err"
expect "$(cat "$workdir/mode.err")" "human gate"

step "a rebuild of the projections gives the same queue"
before="$(tl proposal ls --project P123 --status all)"
quiet uv run tl projections rebuild >/dev/null
after="$(tl proposal ls --project P123 --status all)"
if [ "$before" != "$after" ]; then
  echo "DEMO FAILED: the queue changed after a rebuild" >&2
  exit 1
fi
echo "identical after rebuild"

echo
echo "P0-I6-B demo ok"
