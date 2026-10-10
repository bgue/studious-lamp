#!/usr/bin/env bash
# Demo for P0-I4 workstream A (query language and change feed).
# Run with `just demo P0-I4-A` from the repository root. Uses a temporary ledger; nothing is left behind.
# Fails (exit 1) when an expectation is not met.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."
# `uv` prints a harmless UV_NATIVE_TLS deprecation warning on every call in the build container.
uv run python dev/demos/p0_i4_a_demo.py 2> >(grep -v 'UV_NATIVE_TLS' >&2)
