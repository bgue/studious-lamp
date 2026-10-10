#!/usr/bin/env bash
# Demo of the P0-I8 workstream C (agent-dev baseline; brief 25.2, 25.3):
#   1. the dev MCP server (python -m tl_mcp.dev) over stdio: its tools, resources and refusals;
#   2. the server refusing a database outside dev data and a real environment;
#   3. tl new module / record-type / projector into a temporary tree: ruff and the generated tests pass.
#
#   just demo P0-I8-C
#
# Everything happens in a temporary directory; nothing is left behind. Fails (exit 1) when an
# expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
export TL_DB="$workdir/tl.db"
unset TL_SCHEMA_DIR TL_ENV

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
tl() { quiet uv run tl "$@"; }
step() { printf '\n== %s\n' "$*"; }
expect() { # expect <text> <pattern>
  if ! grep -Eq -- "$2" <<<"$1"; then
    echo "DEMO FAILED: expected /$2/ in:" >&2
    echo "$1" >&2
    exit 1
  fi
}

step "A temporary dev ledger with three records"
tl init
tl record create --project P123 --key V-1 --title "Valve one" >/dev/null
tl record create --project P123 --key V-2 --title "Valve two" >/dev/null
tl record create --project P123 --key V-3 --title "Valve three" >/dev/null

step "The dev MCP server over stdio (tools, resources, refusals)"
quiet uv run python dev/demos/p0_i8_c_demo.py

step "The server refuses what is not dev data"
out="$(quiet uv run python -m tl_mcp.dev --db /etc/hostname 2>&1 || true)"
echo "$out"
expect "$out" "refused"
out="$(TL_ENV=production quiet uv run python -m tl_mcp.dev --db "$TL_DB" 2>&1 || true)"
echo "$out"
expect "$out" "TL_ENV"
out="$(quiet uv run python -m tl_mcp.dev --db postgresql://postgres:x@db.example.com/tl_test 2>&1 || true)"
echo "$out"
expect "$out" "refused"

step "tl new: a module, a record type and a projector into a temporary tree"
tree="$workdir/tree"
mkdir -p "$tree/schema"
cp -r schema/core "$tree/schema/core"
tl new module inspection --root "$tree"
tl new record-type inspection.WeldInspection --root "$tree"
tl new projector inspection.weld_counts --event Weld.Created --root "$tree"
quiet uv run ruff check --config pyproject.toml "$tree"
quiet uv run ruff format --check --config pyproject.toml "$tree"
(cd "$tree" && PYTHONPATH="$tree/packages/tl-modules/inspection/src" quiet uv run --project "$OLDPWD" \
  python -m pytest -q -p no:cacheprovider --rootdir "$tree" "$tree/packages/tl-modules/inspection/tests")
out="$(tl new record-type inspection.WeldInspection --root "$tree" 2>&1 || true)"
expect "$out" "refusing to overwrite"
echo "a second run refuses to overwrite"

echo
echo "DEMO OK"
