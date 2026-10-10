#!/usr/bin/env bash
# Demo of P0-I8 workstream B (extension record types; brief 31): a type package is registered with
# the CLI, an object-backed record is created and read over HTTP, read by an agent over MCP and
# edited by the TUI's embedded client, a damaged body is refused, listed and healed, a broken
# package is quarantined and a retired type takes no new records.
#
#   just demo P0-I8-B
#
# Runs in a temporary directory (ledger, objects, types, tokens, API port); nothing is left behind.
# Fails (exit 1) when an expectation is not met.
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
export TL_OBJECT_ROOT="$workdir/objects"
export TL_ENV="${TL_ENV:-dev}"
unset TL_SCHEMA_DIR

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
demo() { quiet uv run python dev/demos/p0_i8_b_demo.py "$@"; }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}
api() { # api <method> <path> [json]  -> prints "<status> <body>"
  local method="$1" path="$2" data="${3:-}"
  if [ -n "$data" ]; then
    curl -s -X "$method" -H "Authorization: Bearer $token" -H 'content-type: application/json' \
      -d "$data" -w ' %{http_code}' "$base$path"
  else
    curl -s -X "$method" -H "Authorization: Bearer $token" -w ' %{http_code}' "$base$path"
  fi
}

types="$workdir/types"
mkdir -p "$types"
cp -R schema/fixtures/types/. "$types/"

step "tl init, a dev token, the API on a free loopback port"
tl init
token="$(tl dev token add user:alice)"
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
base="http://127.0.0.1:$port"
quiet uv run python -m tl_api --port "$port" >"$workdir/server.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 100); do
  curl -fs "$base/health" >/dev/null 2>&1 && break
  sleep 0.1
done
expect "$(curl -fs "$base/health")" '"status":"ok"'
echo "listening on $base"

step "validate a package, register the packages (a second run changes nothing)"
out="$(tl types validate "$types/co.acme/LiftPlan/1.0.0")"
echo "$out"
expect "$out" '^ok co.acme.LiftPlan@1.0.0 object-backed'
out="$(tl types sync "$types")"
echo "$out"
expect "$out" 'registered co.acme.LiftPlan@1.0.0'
expect "$out" 'registered co.acme.SafetyObservation@1.0.0'
out="$(tl types sync "$types")"
echo "(second run) $out"
if grep -q 'registered' <<<"$out"; then echo "DEMO FAILED: a second sync registered again" >&2; exit 1; fi
tl types ls
tl types show co.acme.LiftPlan@1.0.0

step "the running API serves the new type without a restart (the schema provider notices it)"
for _ in $(seq 1 30); do
  out="$(api GET /types)"
  grep -q 'co.acme.LiftPlan' <<<"$out" && break
  sleep 0.2
done
expect "$out" 'co.acme.LiftPlan@1.0.0'
echo "GET /types lists co.acme.LiftPlan@1.0.0"

step "create an object-backed record over HTTP: the body is validated and stored as an object"
lift='{"scope":"project:P123","title":"Skid lift","key":"LP-1","body":{"lift_date":"2026-11-03","crane":"CR-12","load_tonnes":42.5,"risk_class":"medium","crew":["A. Okafor"]}}'
out="$(api POST /types/co.acme.LiftPlan/records "$lift")"
echo "$out" | cut -c1-120
expect "$out" ' 20[01]$'
record_id="$(sed -E 's/^.*"stream_id":"([^"]+)".*$/\1/' <<<"$out")"
out="$(api GET "/records/$record_id/body")"
expect "$out" '"crane":"CR-12"'
expect "$out" ' 200$'
echo "GET /records/<id>/body -> 200, crane CR-12"

step "an invalid body is refused with its problems, and nothing is created"
bad='{"scope":"project:P123","title":"Bad lift","key":"LP-2","body":{"lift_date":"2026-11-03","crane":"CR-12","load_tonnes":1,"risk_class":"enormous"}}'
out="$(api POST /types/co.acme.LiftPlan/records "$bad")"
echo "$out" | cut -c1-200
expect "$out" 'body_invalid'
expect "$out" ' 422$'

step "an agent reads the types and the body over MCP; the TUI client edits the body"
demo mcp
demo tui-edit
out="$(api GET "/records/$record_id/body")"
expect "$out" '"risk_class":"high"'
echo "the API reads the edited body: risk_class high"

step "a damaged object is refused, listed in the quarantine report, and healed by storing it again"
demo tamper
out="$(api GET "/records/$record_id/body")"
echo "$out" | cut -c1-160
expect "$out" 'body_hash_mismatch'
expect "$out" ' 502$'
out="$(tl types quarantine ls)"
echo "$out"
expect "$out" "$record_id"
out="$(tl types quarantine recheck "$record_id" 2>&1 || true)"
echo "$out"
expect "$out" 'still failing'
healed='{"scope":"project:P123","body":{"lift_date":"2026-11-03","crane":"CR-12","load_tonnes":51.0,"risk_class":"high","crew":["A. Okafor"]}}'
out="$(api PUT "/records/$record_id/body" "$healed")"
expect "$out" ' 200$'
out="$(tl types quarantine recheck "$record_id")"
echo "$out"
expect "$out" "restored $record_id"
expect "$(tl types quarantine ls)" 'nothing quarantined'

step "a package that does not validate is quarantined alone; a registered version cannot be edited"
bad_pkg="$types/co.acme/Broken/1.0.0"
mkdir -p "$bad_pkg"
cp "$types/co.acme/LiftPlan/1.0.0/type.yaml" "$bad_pkg/type.yaml"
tl types lock "$bad_pkg" >/dev/null
out="$(tl types sync "$types")"
echo "$out"
expect "$out" 'quarantined co.acme.Broken@1.0.0'
printf '\nEdited after registration.\n' >> "$types/co.acme/LiftPlan/1.0.0/README.md"
tl types lock "$types/co.acme/LiftPlan/1.0.0" >/dev/null
out="$(tl types sync "$types")"
echo "$out"
expect "$out" 'conflict co.acme.LiftPlan@1.0.0'
out="$(tl types sync --strict "$types" 2>&1 || true)"
expect "$out" 'quarantined'
tl types quarantine ls

step "retire a version: existing records stay, no new ones"
tl types deprecate co.acme.LiftPlan@1.0.0 --reason "demo: replaced by a newer plan type"
out="$(api POST /types/co.acme.LiftPlan/records "${lift//LP-1/LP-3}")"
echo "$out" | cut -c1-160
expect "$out" 'type_not_active'
expect "$out" ' 409$'
out="$(api GET "/records/$record_id/body")"
expect "$out" ' 200$'
echo "the existing record still reads"

printf '\nP0-I8-B demo ok\n'
