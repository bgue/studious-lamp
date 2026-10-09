# P0-I1-T01 — Monorepo scaffold

Status: ready
Tier: haiku
Labels: tooling
Depends on: —
Branch: `p0/i1/t01-monorepo-scaffold`

## Goal
A `uv` workspace with empty but importable packages, a `justfile` whose `check` and `test` recipes run, shared
ruff/pyright/pytest configuration, and a CI workflow that runs `just check` and `just test` on every PR.

## Brief references (pasted)
> Tooling: `uv`, `ruff`, `mypy`/`pyright`, `pytest`, `hypothesis`, `textual-dev` snapshot tests. Packaging: `uv` workspace monorepo; one package per module. (§14)
> Task runner: one documented interface (`just`): `gen`, `test`, `test-parity`, `test-tui`, `lint`, `rebuild-projections`, `seed`, `serve`. (§25.2)

## Interfaces
Package list and import names, from `docs/build-spec/03-repo-and-toolchain.md` §1:

| Directory | Import name |
|---|---|
| `packages/tl-schema` | `tl_schema` |
| `packages/tl-core` | `tl_core` |
| `packages/tl-adapters` | `tl_adapters` |
| `packages/tl-api` | `tl_api` |
| `packages/tl-mcp` | `tl_mcp` |
| `packages/tl-tui` | `tl_tui` |
| `packages/tl-cli` | `tl_cli` |

`just` recipes to define now (others may be stubs that print "not yet"): `gen`, `check`, `test`, `test-parity`, `test-tui`, `seed`, `serve`, `tui`, `rebuild-projections`, `dev up`, `dev down`, `demo <id>`.

## Context (read these, nothing else)
- `AGENTS.md`
- `docs/build-spec/03-repo-and-toolchain.md` §1–§4

## Allowed paths
- `pyproject.toml`, `uv.lock`, `.python-version`, `justfile` (create)
- `.github/workflows/ci.yml` (create)
- `packages/<each>/pyproject.toml`, `packages/<each>/src/<import_name>/__init__.py`, `packages/<each>/tests/test_import.py` (create)
- `tests/conftest.py` (create, may be empty)
- `dev/docker-compose.yml` (create: MinIO only; Postgres added in I5)

## Steps
1. Root `pyproject.toml`: `[tool.uv.workspace] members = ["packages/*"]`; `[tool.ruff]` line-length 100, target py312, select `E,F,I,UP,B`; `[tool.pyright]` strict for `tl_core`, `tl_schema`, `tl_adapters`, standard otherwise; `[tool.pytest.ini_options]` testpaths `packages tests`.
2. Each package `pyproject.toml`: name `tl-<x>`, version `0.0.1`, `requires-python >=3.12`, hatchling build, `src` layout. Dependencies: only `pydantic>=2` for `tl-core`, `tl-schema`; `sqlalchemy>=2` for `tl-adapters`; `typer` for `tl-cli`; `textual` for `tl-tui`; `fastapi` for `tl-api`; `mcp` for `tl-mcp`. Dev group at root: `ruff`, `pyright`, `pytest`, `hypothesis`, `pytest-textual-snapshot`.
3. `justfile`: `check` = `uv run ruff check . && uv run ruff format --check . && uv run pyright && just gen && git diff --exit-code -- packages/tl-schema/src/tl_schema/generated`; `gen` = `uv run python -m tl_schema.generate` (prints "no generators yet" and exits 0 until T03); `test` = `uv run pytest -q`.
4. CI: ubuntu, `astral-sh/setup-uv`, `extractions/setup-just`, `uv sync`, `just check`, `just test`.
5. One `test_import.py` per package asserting the import works.

## Acceptance
```
uv sync
just check
just test
```
Expected: `just check` exits 0; `just test` reports 7 passed.

## Tests to add
- `packages/<each>/tests/test_import.py` — `import <name>` succeeds.

## Report requirements
Standard report plus the `uv --version`, `ruff --version`, `pyright --version` lines.

## Escalation triggers
- Stop if any dependency fails to resolve on Python 3.12; report the resolver output.
- Do not add dependencies beyond the list in step 2.

## Blocked

## Decision
