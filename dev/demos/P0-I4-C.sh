#!/usr/bin/env bash
# Demo for P0-I4 workstream C (REST API, SSE stream, MCP read server, HTTP client).
# Run with `just demo P0-I4-C` from the repository root. Starts the API on a free loopback port over
# a temporary ledger, object root and token file; nothing is left behind. Fails (exit 1) when an
# expectation is not met. The full P0-I4 demo (two TUIs and an MCP agent) is dev/demos/P0-I4.sh.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
server_pid=""
stream_pid=""
cleanup() {
  [ -n "$stream_pid" ] && kill "$stream_pid" 2>/dev/null || true
  [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null || true
  rm -rf "$workdir"
}
trap cleanup EXIT
export TL_DB="$workdir/tl.db"
export TL_OBJECT_ROOT="$workdir/objects"
export TL_TOKENS="$workdir/tokens.json"
export TL_ENV="${TL_ENV:-dev}"
unset TL_SCHEMA_DIR TL_OBJECT_STORE

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

step "a request without a token is refused, with or without a body"
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'content-type: application/json' -d '{broken' "$base/commands/CreateRecord")"
echo "POST /commands/CreateRecord with no token -> $code"
expect "$code" '^401$'
code="$(curl -s -o /dev/null -w '%{http_code}' "$base/openapi.json")"
echo "GET /openapi.json with no token -> $code"
expect "$code" '^401$'

step "an SSE stream on the API while another process writes (the embedded path)"
curl -sN -H "Authorization: Bearer $token" "$base/stream" >"$workdir/stream.txt" 2>/dev/null &
stream_pid=$!
sleep 0.5
tl record create --project P123 --key P123-REC-0001 --title "Written by the CLI" >/dev/null
start_ns="$(date +%s%N)"  # measured from the moment the writer process has exited
seen=""
for _ in $(seq 1 40); do
  if grep -q 'Record.Created' "$workdir/stream.txt"; then seen=yes; break; fi
  sleep 0.05
done
elapsed_ms=$(( ( $(date +%s%N) - start_ns ) / 1000000 ))
[ -n "$seen" ] || { echo "DEMO FAILED: the stream never showed the CLI write" >&2; exit 1; }
echo "the stream showed the CLI's Record.Created ${elapsed_ms} ms after the CLI returned"
grep -E '^(id|event):' "$workdir/stream.txt" | head -n 2
[ "$elapsed_ms" -lt 2000 ] || { echo "DEMO FAILED: slower than 2 s" >&2; exit 1; }

step "resume from Last-Event-ID: nothing missed, nothing repeated"
tl record create --project P123 --key P123-REC-0002 --title "Second" >/dev/null
resumed="$(curl -sN --max-time 2 -H "Authorization: Bearer $token" -H 'Last-Event-ID: 1' "$base/stream" || true)"
ids="$(grep -E '^id:' <<<"$resumed" | tr -d '\r' | tr '\n' ' ')"
echo "events after id 1: $ids"
expect "$ids" '^id: 2 $'

step "the client, the query language, links, files and MCP"
export TL_DEMO_URL="$base" TL_DEMO_TOKEN="$token"
quiet uv run python dev/demos/p0_i4_c_demo.py

echo
echo "P0-I4 workstream C demo OK"
