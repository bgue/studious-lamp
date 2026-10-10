#!/usr/bin/env bash
# Demo for P0-I8 workstream A (about:config settings; brief 30):
#   1. tl config: read, set at the company and the project (origin and the dot), a dangerous key that
#      needs a reason and the risk, an allow-list entry that is too wide, a lock, a scheduled change,
#      history and undo (only the latest), diff, export and import into a second project;
#   2. an MCP agent reads settings and proposes changes; a person decides; a dangerous key is
#      accepted only with the risk accepted; an agent token is refused every write over HTTP;
#   3. tl lake sync --watch waits lake.sync.interval; the TUI screen (F9) as an SVG.
#
#   just demo P0-I8-A
#
# Uses a temporary ledger, token file, lake and API port; nothing is left behind. Fails (exit 1)
# when an expectation is not met.
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
export TL_LAKE_DIR="$workdir/lake"
export TL_ENV="${TL_ENV:-dev}"
unset TL_SCHEMA_DIR

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
py() { quiet uv run python dev/demos/p0_i8_a_demo.py "$@"; }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>: fail the demo if the pattern is missing
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}
refuse() { # refuse <pattern> <command...>: the command must fail with a message matching <pattern>
  local pattern="$1"
  shift
  if "$@" 2>"$workdir/refused.err"; then
    echo "DEMO FAILED: the command was accepted: $*" >&2
    exit 1
  fi
  cat "$workdir/refused.err"
  expect "$(cat "$workdir/refused.err")" "$pattern"
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

step "the defaults a project sees"
out="$(tl config ls --project P123 --prefix feed.)"
echo "$out"
expect "$out" "^feed.reactions.enabled  true  bool  default  -$"
expect "$out" "^feed.signal_tags  \[safety, hold, decision, \+2\]  list  default  -$"

step "set at the company, then at the project: the origin names the layer, the dot marks the project's own value"
tl config set feed.signal_tags "safety,hold,ncr" --company
tl config set feed.reactions.enabled false --project P123
out="$(tl config ls --project P123 --prefix feed.)"
echo "$out"
expect "$out" "^feed.reactions.enabled  false  bool  project ●  -$"
expect "$out" "^feed.signal_tags  \[safety, hold, ncr\]  list  company  -$"
out="$(tl config ls --project P123 --modified)"
echo "$out"
expect "$out" "^feed.reactions.enabled  false"
[ "$(wc -l <<<"$out")" -eq 1 ]

step "a bad value, a missing reason and an unaccepted risk are refused and write nothing"
refuse "not a duration|duration" tl config set lake.sync.interval "five minutes" --company
refuse "say why" tl config set webhooks.retry.max_hours 48 --company
refuse "say why" tl config set webhooks.egress.allowlist hub.example.com --company
refuse "accept the risk" tl config set webhooks.egress.allowlist hub.example.com --company --reason "partner hub"
out="$(tl config history webhooks.egress.allowlist)"
[ -z "$out" ]

step "an allow-list entry that would open too much is refused even with the risk accepted"
refuse "covers too much" tl config set webhooks.egress.allowlist 0.0.0.0/0 --company --reason r --accept-risk
refuse "never allowed" tl config set webhooks.egress.allowlist 169.254.169.254 --company --reason r --accept-risk
refuse "6to4, Teredo or NAT64" tl config set webhooks.egress.allowlist 2002::/16 --company --reason r --accept-risk

step "a dangerous key with a reason and the risk accepted"
out="$(tl config set webhooks.egress.allowlist hub.example.com --company --reason "partner hub" --accept-risk)"
echo "$out"
expect "$out" '^set webhooks.egress.allowlist company \["hub.example.com"\]$'

step "the company locks a key: the project's value stops applying and new ones are refused"
tl config lock feed.reactions.enabled --reason "policy: reactions stay on"
out="$(tl config get feed.reactions.enabled --project P123 --long)"
echo "$out"
expect "$out" "^value true$"
expect "$out" "^locked yes"
refuse "locked by the company" tl config set feed.reactions.enabled false --project P124
tl config lock feed.reactions.enabled --unlock --reason "policy changed"

step "a scheduled change is listed and not yet in force"
later="$(date -u -d '+2 days' +%Y-%m-%dT%H:%M:%SZ)"
out="$(tl config set ai.agents.daily_proposals 200 --company --reason "pilot ends" --at "$later")"
echo "$out"
expect "$out" "^scheduled ai.agents.daily_proposals company 200 at "
out="$(tl config get ai.agents.daily_proposals --long)"
expect "$out" "^value 500$"
expect "$out" "^scheduled "

step "history, undo of the latest change only"
tl config set feed.signal_tags "a" --project P123
tl config set feed.signal_tags "b" --project P123
out="$(tl config history feed.signal_tags --layer project:P123)"
echo "$out"
first="$(head -1 <<<"$out" | cut -d' ' -f1)"
latest="$(tail -1 <<<"$out" | cut -d' ' -f1)"
refuse "latest" tl config revert feed.signal_tags --layer project:P123 --seq "$first"
out="$(tl config revert feed.signal_tags --layer project:P123 --seq "$latest")"
echo "$out"
expect "$out" "^reverted feed.signal_tags project:P123 to \[a\]$"

step "compare layers, export a project's settings and import them into another project"
out="$(tl config diff default company)"
echo "$out"
expect "$out" "feed.signal_tags"
tl config export --project P123 --out "$workdir/p123.yaml"
out="$(tl config import "$workdir/p123.yaml" --project P124)"
echo "$out"
expect "$out" "^imported 2 keys into project:P124$"
out="$(tl config get feed.signal_tags --project P124)"
expect "$out" "^\[a\]$"

step "an agent, over MCP: reads settings, proposes a safe change and a dangerous one; nothing changes"
out="$(py agent)"
echo "$out"
expect "$out" "^agent reads feed.reactions.enabled, feed.signal_tags$"
expect "$out" "^feed.reactions.enabled for P123 is still false$"
mapfile -t proposals < <(grep '^proposed ' <<<"$out" | cut -d' ' -f2)
[ "${#proposals[@]}" -eq 2 ]
safe="${proposals[0]}"
danger="${proposals[1]}"
out="$(tl proposal ls --project P123)"
echo "$out"
out="$(tl proposal ls --company)"
echo "$out"
expect "$out" "\[dangerous\]"

step "a person reads the proposal: the key, the layer, the old and new value, the risk"
out="$(tl proposal show "$danger")"
echo "$out"
expect "$out" "^setting webhooks.egress.allowlist at company$"
expect "$out" "^risk dangerous$"

step "accepting a dangerous change needs the risk accepted; without it the proposal stays pending"
refuse "risk" tl proposal accept "$danger" --actor user:alice
out="$(tl proposal ls --company)"
expect "$out" "$danger  pending"
out="$(tl proposal accept "$safe" --actor user:alice)"
echo "$out"
expect "$out" "^accepted $safe$"
out="$(tl config get feed.reactions.enabled --project P123)"
expect "$out" "^false$"

step "over HTTP: the agent's token reads but never writes; alice decides, the risk accepted in the body"
out="$(py api "$danger")"
echo "$out"
expect "$out" "^agent write refused: 403 agent_must_propose$"
expect "$out" "^accepted with the risk accepted by alice$"

step "tl lake sync --watch waits lake.sync.interval (read again before every wait)"
tl record create --project P123 --key V-1 --title "Valve one" >/dev/null
tl config set lake.sync.interval 10s --company
start=$SECONDS
out="$(tl lake sync --watch --max-runs 2)"
echo "$out"
expect "$out" "^synced seq "
[ $((SECONDS - start)) -ge 9 ]

step "the TUI screen (F9) saved as an SVG"
snapshot="${TL_DEMO_SNAPSHOT:-dev/data/p0-i8-a-about-config.svg}"
mkdir -p "$(dirname "$snapshot")"
out="$(py tui "$snapshot")"
echo "$out"
expect "$out" "^saved "

echo
echo "P0-I8-A demo ok"
