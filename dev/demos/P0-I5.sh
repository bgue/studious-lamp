#!/usr/bin/env bash
# Demo for P0-I5 workstream B: a filtered subscription receives a signed event, a replay re-delivers
# it (the receiver dedupes on the event id), a failing endpoint dead-letters and is redriven, and a
# secret rotation overlaps. Run with `just demo P0-I5` from the repository root. Uses a temporary
# ledger and a receiver on 127.0.0.1; nothing is left behind. Exits 1 when an expectation fails.
# (The Postgres half of P0-I5 is demonstrated by workstream A.)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export TL_ENV="${TL_ENV:-dev}"

# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
uv run python dev/demos/p0_i5_demo.py 2> >(grep -v 'UV_NATIVE_TLS' >&2)
