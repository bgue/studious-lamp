# Throughline task runner. `just` is the only entry point for builds, checks, and demos.
set shell := ["bash", "-euo", "pipefail", "-c"]

# Every recipe is a dev command: the object store signs with the public dev secret (TL_ENV=dev).
# Set TL_ENV and TL_OBJECT_SECRET yourself to run against anything real.
export TL_ENV := env_var_or_default("TL_ENV", "dev")

default:
    @just --list

# Run every generator from schema/ into packages/tl-schema/src/tl_schema/generated/
gen:
    uv run python -m tl_schema.generate

# Lint, format check, types, and codegen drift (fails if `just gen` would change committed output)
check:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    uv run python -m tl_schema.generate --check
    uv run python dev/tools/check_licences.py

# Unit and integration tests on SQLite
test *args:
    uv run pytest -q {{args}}

# Parity suite: every test that uses the `new_db`/`db`/`adapter` fixtures runs on SQLite and on
# Postgres (TL_PG_URL, default the native dev cluster), plus the Postgres-only tests. Postgres being
# unreachable is a failure here, never a skip.
test-parity *args:
    #!/usr/bin/env bash
    set -euo pipefail
    just dev up
    export TL_REQUIRE_POSTGRES=1
    export TL_PG_URL="${TL_PG_URL:-postgresql://postgres:postgres@localhost:5432/tl_test}"
    uv run pytest -q -m "parity or requires_postgres" --adapters sqlite,postgres {{args}}

# TUI tests: widget behaviour and snapshot tests, with terminal sizes pinned in the tests
test-tui *args:
    uv run pytest packages/tl-tui -q {{args}}

# Synthetic project into the dev ledger (arrives with P0-I6)
seed scale="xs":
    @echo "seed {{scale}}: not yet (arrives with P0-I6)"

# API and workers on the dev ledger (arrives with P0-I4)
serve:
    @echo "serve: not yet (arrives with P0-I4)"

# TUI in embedded mode against the dev ledger (TL_DB, default ./dev/data/tl.db; TL_PROJECT, default P123)
tui:
    uv run tl init
    uv run python -m tl_tui

# Rebuild projections from the ledger: all of them, or one by projector name (e.g. core_record)
rebuild-projections name="":
    uv run tl projections rebuild {{ if name == "" { "" } else { "--only " + name } }}

# Dev services: `just dev up` or `just dev down`. No Docker daemon is assumed (ADR-0002).
dev action:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{action}}" in
      up)
        mkdir -p dev/data
        if command -v pg_isready >/dev/null 2>&1 && ! pg_isready -q -h localhost -p 5432; then
          sudo pg_ctlcluster 16 main start || echo "dev up: could not start native Postgres; parity tests will skip"
        fi
        echo "dev up: skipped MinIO (no Docker daemon); the fs object store is used instead"
        ;;
      down)
        echo "dev down: nothing to stop (native Postgres is left running)"
        ;;
      *)
        echo "usage: just dev up|down" >&2
        exit 2
        ;;
    esac

# Run the demo script for an increment, e.g. `just demo P0-I1`
demo id:
    bash dev/demos/{{id}}.sh
