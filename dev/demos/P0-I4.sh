#!/usr/bin/env bash
# Demo for P0-I4: one record change, seen by a remote TUI, a remote client and an MCP agent in < 2 s.
# Run with `just demo P0-I4` from the repository root. Starts `tl serve` on a free loopback port over a
# temporary ledger and token file; an embedded writer (the CLI, then an embedded client) changes a
# record; the observers are a headless remote TUI (Textual Pilot, no terminal), the SSE client the
# TUI uses, and an in-process MCP server. Measured latencies are printed; the demo fails above 2 s.
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
unset TL_SCHEMA_DIR TL_OBJECT_STORE TL_REMOTE TL_TOKEN TL_PROJECT

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }

step "tl init, a dev token, tl serve on a free loopback port"
tl init
token="$(tl dev token add user:alice)"
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
base="http://127.0.0.1:$port"
quiet uv run tl serve --port "$port" >"$workdir/server.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 100); do
  curl -fs "$base/health" >/dev/null 2>&1 && break
  sleep 0.1
done
curl -fs "$base/health" | grep -q '"status":"ok"' || { echo "DEMO FAILED: the server did not start" >&2; cat "$workdir/server.log" >&2; exit 1; }
echo "listening on $base (tl tui --remote $base --token <token> opens the same screens)"

step "a remote TUI, an SSE client and an MCP agent watch while an embedded writer changes a record"
export TL_DEMO_URL="$base" TL_DEMO_TOKEN="$token"
quiet uv run python dev/demos/p0_i4_demo.py

echo
echo "P0-I4 demo OK"
