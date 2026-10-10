#!/usr/bin/env bash
# `just seed [scale]`: a synthetic project in the dev ledger, written through the API by the simulator.
# Scales: xs (3 working days), s (10), m (30); see dev/seed/scenarios/seed-*.yaml. If no API answers at
# TL_API_URL (default http://127.0.0.1:8765) this starts one on the dev ledger (TL_DB, TL_TOKENS) for
# the duration of the run and stops it afterwards. Extra arguments go to `tl sim seed`, for example
# `--run-id rmine` to seed a second project.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
scale="${1:-xs}"
shift || true
export TL_API_URL="${TL_API_URL:-http://127.0.0.1:8765}"
server_pid=""
cleanup() { [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null || true; }
trap cleanup EXIT

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }

quiet uv run tl init
if ! curl -fs "$TL_API_URL/health" >/dev/null 2>&1; then
  port="${TL_API_URL##*:}"
  echo "no API at $TL_API_URL: starting one on the dev ledger"
  quiet uv run tl serve --port "$port" >/dev/null 2>&1 &
  server_pid=$!
  for _ in $(seq 1 100); do
    curl -fs "$TL_API_URL/health" >/dev/null 2>&1 && break
    sleep 0.1
  done
  curl -fs "$TL_API_URL/health" >/dev/null || { echo "error: the API did not start" >&2; exit 1; }
fi
quiet uv run tl sim seed --scale "$scale" "$@"
