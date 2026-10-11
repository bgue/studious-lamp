#!/usr/bin/env bash
# Demo of P0-I8 workstream D (performance pass; brief 15): the bench suite at a small scale.
#
#   just demo P0-I8-D
#
# It seeds a 2000-record project (and a 300-record one for the rebuilds) through the same
# generator the 100k run uses, on SQLite and, when it is reachable, Postgres; runs the grid, TUI
# grid, realtime and rebuild benches; and prints the tables of the brief section 15 targets.
# Seeded files stay under dev/data/bench (git-ignored) and make the next run faster. The 100k
# run is `just bench-seed` once and then `just bench` (docs/runbooks/performance-benches.md).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

export TL_BENCH_RECORDS="${TL_BENCH_RECORDS:-2000}"
export TL_BENCH_REBUILD_RECORDS="${TL_BENCH_REBUILD_RECORDS:-300}"
export TL_BENCH_ROUNDS="${TL_BENCH_ROUNDS:-2}"
export TL_BENCH_SAMPLES="${TL_BENCH_SAMPLES:-6}"
export TL_BENCH_LABEL="demo"

if [ -z "${TL_BENCH_DIALECTS:-}" ]; then
  if pg_isready -q -h localhost -p 5432 2>/dev/null; then
    TL_BENCH_DIALECTS="sqlite,postgres"
  else
    echo "Postgres is not reachable: the demo runs on SQLite only."
    TL_BENCH_DIALECTS="sqlite"
  fi
fi
export TL_BENCH_DIALECTS

quiet() { "$@" 2> >(grep -v 'UV_NATIVE_TLS' >&2); }
step() { printf '\n== %s\n' "$*"; }

step "seed ${TL_BENCH_RECORDS} and ${TL_BENCH_REBUILD_RECORDS} records on ${TL_BENCH_DIALECTS}"
quiet uv run python tests/bench/bench_data.py seed --records "$TL_BENCH_RECORDS"
quiet uv run python tests/bench/bench_data.py seed --records "$TL_BENCH_REBUILD_RECORDS"

step "run the benches (marker bench; never part of just test)"
before="$(ls dev/data/bench/results 2>/dev/null | grep -c 'demo' || true)"
quiet uv run pytest tests/bench -m bench -q -p no:cacheprovider
latest="$(ls -t dev/data/bench/results/*-demo-*.json | head -1)"
after="$(ls dev/data/bench/results | grep -c 'demo' || true)"
if [ "$after" -le "$before" ]; then
  echo "DEMO FAILED: the bench run wrote no results file" >&2
  exit 1
fi

step "the brief section 15 targets (results file: ${latest})"
quiet uv run python tests/bench/bench_report.py "$latest"
