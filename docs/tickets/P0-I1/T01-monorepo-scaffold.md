# P0-I1-T01 — Monorepo scaffold

Status: ready
Tier: haiku
Labels: tooling
Depends on: —
Branch: `p0/i1/t01-monorepo-scaffold`

## Goal
A `uv` workspace with seven empty but importable packages, a `justfile` whose `check` and `test` recipes run clean,
shared ruff/pyright/pytest configuration, and a CI workflow that runs `just check` and `just test`. Every file is given
verbatim below; this ticket is transcription plus verification. It gates every other ticket in the increment.

## Brief references (pasted)
> Tooling: `uv`, `ruff`, `mypy`/`pyright`, `pytest`, `hypothesis`, `textual-dev` snapshot tests. Packaging: `uv` workspace monorepo; one package per module. (§14)
> Task runner: one documented interface (`just`): `gen`, `test`, `test-parity`, `test-tui`, `lint`, `rebuild-projections`, `seed`, `serve`. (§25.2)

Learnings that apply (from `docs/memory/LEARNINGS.md`):
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call. It is harmless; do not count it as a failure.
- `just` and `uv` live in `$HOME/.local/bin`; put that on `PATH` (`export PATH="$HOME/.local/bin:$PATH"`).
- No Docker daemon exists. `dev/docker-compose.yml` is documentation only; never run it.

## Interfaces
Package list and import names (`docs/build-spec/03-repo-and-toolchain.md` §1):

| Directory | Distribution name | Import name | Dependencies (exact) |
|---|---|---|---|
| `packages/tl-schema` | `tl-schema` | `tl_schema` | `pydantic>=2`, `linkml>=1.8`, `linkml-runtime>=1.8`, `jsonschema>=4` |
| `packages/tl-core` | `tl-core` | `tl_core` | `pydantic>=2`, `sqlalchemy>=2`, `python-ulid>=2`, `tl-schema` |
| `packages/tl-adapters` | `tl-adapters` | `tl_adapters` | `sqlalchemy>=2`, `python-ulid>=2`, `tl-core` |
| `packages/tl-api` | `tl-api` | `tl_api` | `fastapi`, `tl-core` |
| `packages/tl-mcp` | `tl-mcp` | `tl_mcp` | `mcp`, `tl-core` |
| `packages/tl-tui` | `tl-tui` | `tl_tui` | `textual`, `tl-core` |
| `packages/tl-cli` | `tl-cli` | `tl_cli` | `typer`, `rich`, `tl-core`, `tl-adapters` |

Dependencies are exactly these: do not add, remove, or pin anything else. They are pre-declared for the whole increment
so later tickets never edit `pyproject.toml` files.

### Root `pyproject.toml` (exact)
```toml
[project]
name = "throughline"
version = "0.0.1"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["ruff", "pyright", "pytest", "hypothesis", "pytest-textual-snapshot"]

[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv.sources]
tl-schema = { workspace = true }
tl-core = { workspace = true }
tl-adapters = { workspace = true }
tl-api = { workspace = true }
tl-mcp = { workspace = true }
tl-tui = { workspace = true }
tl-cli = { workspace = true }

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["packages/tl-schema/src/tl_schema/generated"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["packages", "tests"]
addopts = "--import-mode=importlib"

[tool.pyright]
include = ["packages", "tests"]
exclude = ["**/generated", "**/.venv"]
pythonVersion = "3.12"
typeCheckingMode = "standard"
strict = [
  "packages/tl-core/src",
  "packages/tl-schema/src",
  "packages/tl-adapters/src",
]
```

### `packages/<pkg>/pyproject.toml` (exact pattern; shown for `tl-cli`, adapt name, `packages` path, and dependencies from the table)
```toml
[project]
name = "tl-cli"
version = "0.0.1"
requires-python = ">=3.12"
dependencies = [
  "typer",
  "rich",
  "tl-core",
  "tl-adapters",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/tl_cli"]
```

### Each `packages/<pkg>/src/<import_name>/__init__.py` (exact; replace `<import_name>`)
```python
"""<import_name>: see the package README."""
```
Also create an empty `packages/<pkg>/src/<import_name>/py.typed`.

### `packages/<pkg>/tests/test_import.py` (exact pattern; shown for `tl_core`, adapt the import name in all three places)
```python
def test_import() -> None:
    import tl_core

    assert tl_core.__name__ == "tl_core"
```

### `packages/tl-schema/src/tl_schema/generate.py` (exact; placeholder that P0-I1-T03 replaces)
```python
"""Run every schema generator and write the outputs under ``generated/``.

This is a placeholder until P0-I1-T03 replaces it. ``--check`` must exit non-zero when the committed
generated files differ from what the generators would write; it never modifies files.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    mode = "check" if "--check" in args else "gen"
    print(f"tl_schema.generate {mode}: no generators yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `conftest.py` at the repository root (exact)
```python
"""Root pytest configuration. Shared fixtures are added here by later tickets."""
```

### `justfile` (exact)
```
# Throughline task runner. `just` is the only entry point for builds, checks, and demos.
set shell := ["bash", "-euo", "pipefail", "-c"]

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

# Unit and integration tests on SQLite
test *args:
    uv run pytest -q {{args}}

# Parity suite on SQLite and Postgres (arrives with P0-I5)
test-parity:
    @echo "test-parity: not yet (arrives with P0-I5)"

# TUI snapshot tests (arrives with P0-I2)
test-tui:
    @echo "test-tui: not yet (arrives with P0-I2)"

# Synthetic project into the dev ledger (arrives with P0-I6)
seed scale="xs":
    @echo "seed {{scale}}: not yet (arrives with P0-I6)"

# API and workers on the dev ledger (arrives with P0-I4)
serve:
    @echo "serve: not yet (arrives with P0-I4)"

# TUI in embedded mode against the dev ledger (arrives with P0-I2)
tui:
    @echo "tui: not yet (arrives with P0-I2)"

# Shadow rebuild of projections from the ledger (arrives with P0-I1-T10)
rebuild-projections *types:
    @echo "rebuild-projections: not yet (arrives with P0-I1-T10)"

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
```

### `.github/workflows/ci.yml` (exact)
```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

jobs:
  check-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: extractions/setup-just@v2
      - run: uv sync --all-packages
      - run: just check
      - run: just test
```

### `dev/docker-compose.yml` (exact)
```yaml
# Documentation of the dev services for machines that have a Docker daemon.
# The build container has none (docs/adr/0002-build-environment-constraints.md); nothing here is required to run tests.
services:
  minio:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: tl-dev
      MINIO_ROOT_PASSWORD: tl-dev-secret
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio-data:/data

volumes:
  minio-data:
```

Also create: `.python-version` containing exactly `3.12`; an empty `tests/.gitkeep`.

## Context (read these, nothing else)
- `AGENTS.md`
- `docs/build-spec/03-repo-and-toolchain.md` §1–§4

## Allowed paths
- `pyproject.toml`, `uv.lock`, `.python-version`, `justfile`, `conftest.py` (create)
- `.github/workflows/ci.yml` (create)
- `dev/docker-compose.yml` (create)
- `tests/.gitkeep` (create)
- `packages/<pkg>/pyproject.toml`, `packages/<pkg>/src/<import_name>/__init__.py`, `packages/<pkg>/src/<import_name>/py.typed`, `packages/<pkg>/tests/test_import.py` (create, for each of the seven packages)
- `packages/tl-schema/src/tl_schema/generate.py` (create)

## Steps
1. `export PATH="$HOME/.local/bin:$PATH"`. Create every file above exactly as given.
2. `uv sync --all-packages` (creates `uv.lock`; commit it).
3. Run the Acceptance commands. If `ruff format --check` reports a file, run `uv run ruff format <file>` and note it as a deviation.

## Acceptance
```
uv sync --all-packages
just check
just test
just dev up
uv run python -c "import tl_schema, tl_core, tl_adapters, tl_api, tl_mcp, tl_tui, tl_cli"
```
Expected: `just check` exits 0 (ruff, pyright "0 errors", generate check prints "no generators yet"); `just test` reports `7 passed`;
`just dev up` prints the "skipped MinIO" line and exits 0; the import line prints nothing and exits 0.

## Tests to add
- `packages/<pkg>/tests/test_import.py` for each package: `import <name>` succeeds (given above).

## Report requirements
Standard report plus the output of `uv --version`, `uv run ruff --version`, `uv run pyright --version`, `uv run pytest --version`, and the number of packages `uv sync` resolved.

## Escalation triggers
- Stop if any dependency fails to resolve on Python 3.12; paste the resolver output under *Blocked*.
- Stop if `just check` fails for a reason you would fix by changing a file not listed in *Allowed paths*.

## Blocked

## Decision
