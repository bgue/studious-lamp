# P0-I1-T03 — Codegen wiring

Status: draft (ready when T01 merges; T02 is already on the branch)
Tier: haiku
Labels: tooling
Depends on: P0-I1-T01, P0-I1-T02
Branch: `p0/i1/t03-codegen-wiring`

## Goal
`just gen` runs the LinkML generators over `schema/core/core.yaml` and writes Pydantic models and JSON Schema into
`packages/tl-schema/src/tl_schema/generated/`. `just check` fails when the committed generated files differ from
what the generators produce (codegen drift, brief §25.4), without needing a clean git tree. Output is deterministic.

## Brief references (pasted)
> The model is authored in LinkML (YAML). From it the build generates: Pydantic models (service layer validation); JSON Schema (API contracts, ... pset validation); SQL DDL for projections (SQLite and Postgres dialects); ... (§6.1)
> Codegen in build; checked into repo. (§14, "Schema/semantics")

Build-spec rules (`docs/build-spec/03-repo-and-toolchain.md` §4): generated artefacts live only under
`packages/tl-schema/src/tl_schema/generated/` and are committed; generators are deterministic (sorted keys, no
timestamps, no absolute paths); a ticket that changes a generator includes the regenerated output.

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call.
- pyright runs in strict mode for `tl_schema` source, and `linkml` ships no type stubs. A generator module that imports
  `linkml` starts with the comment line `# pyright: basic` (shown below). Do not add other ignores.

## Interfaces
Already in the repo (do not edit): `schema/core/core.yaml` (imports `annotations`, `record`, `ledger`),
`packages/tl-schema/src/tl_schema/generators/__init__.py` (empty), and the placeholder
`packages/tl-schema/src/tl_schema/generate.py` which you replace.

Create `packages/tl-schema/src/tl_schema/generators/pydantic_gen.py` (exact):
```python
# pyright: basic
"""Pydantic v2 models from the core LinkML schema."""

from __future__ import annotations

from contextlib import chdir
from pathlib import Path

from linkml.generators.pydanticgen import PydanticGenerator

ROOT_SCHEMA = "core.yaml"


def generate(schema_dir: Path) -> dict[str, str]:
    """Return {path relative to generated/: file text}. Runs inside schema_dir."""
    with chdir(schema_dir):
        text = PydanticGenerator(ROOT_SCHEMA).serialize()
    return {"models.py": text}
```
The `chdir` and the relative `ROOT_SCHEMA` are required: they keep the machine's absolute path out of the output
(otherwise the file differs between clones).

Create `packages/tl-schema/src/tl_schema/generators/jsonschema_gen.py` the same way, importing
`from linkml.generators.jsonschemagen import JsonSchemaGenerator`, calling `JsonSchemaGenerator(ROOT_SCHEMA).serialize()`,
and returning `{"json_schema/core.schema.json": text}`.

Replace `packages/tl-schema/src/tl_schema/generate.py` with a module providing exactly this public surface:
```python
GENERATED_DIR: Path   # the generated/ directory next to generate.py: Path(__file__).resolve().parent / "generated"
SCHEMA_DIR: Path      # repo_root/schema/core: Path(__file__).resolve().parents[4] / "schema" / "core"
GENERATORS: list[Callable[[Path], dict[str, str]]]   # [pydantic_gen.generate, jsonschema_gen.generate]; later tickets append

def outputs(schema_dir: Path = SCHEMA_DIR) -> dict[str, str]:
    """Run every generator. Keys are posix paths relative to generated/, sorted. Always includes
    "__init__.py" with the text '"""Generated from schema/ by `just gen`. Do not edit by hand."""\n'.
    Every value is normalised to end with exactly one newline."""

def existing(out_dir: Path) -> set[str]:
    """Posix paths of every file under out_dir, ignoring any __pycache__ directory; empty set if out_dir is absent."""

def problems(out_dir: Path, files: dict[str, str]) -> list[str]:
    """Lines 'missing: <path>', 'differs: <path>', 'stale: <path>' (a file on disk that is not in files); empty list means in sync."""

def write(out_dir: Path, files: dict[str, str]) -> None:
    """Delete stale files, create parent directories, write every file as UTF-8."""

def main(argv: list[str] | None = None) -> int:
    """argparse flags: --check (verify only), --out DIR (default GENERATED_DIR), --schema-dir DIR (default SCHEMA_DIR).
    Without --check: write and print 'wrote N files to <out>', return 0.
    With --check: print each problem to stderr, then 'codegen drift: run `just gen` and commit the result' to stderr and
    return 1 when there are problems; otherwise print 'generated files are up to date (N files)' and return 0."""
```
End the module with `if __name__ == "__main__": raise SystemExit(main())`. The `justfile` already calls
`uv run python -m tl_schema.generate` (gen) and `... --check` (inside `check`); do not edit it.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/generate.py` (the placeholder you replace)
- `schema/core/core.yaml` (only to see the root; do not edit anything under `schema/`)
- `justfile`

## Allowed paths
- `packages/tl-schema/src/tl_schema/generate.py` (replace)
- `packages/tl-schema/src/tl_schema/generators/pydantic_gen.py`, `jsonschema_gen.py` (create)
- `packages/tl-schema/src/tl_schema/generated/**` (create, by running `just gen` only; never edit by hand)
- `packages/tl-schema/tests/test_generate.py` (create)

## Acceptance
```
just gen
just gen            # second run changes nothing: git status --short shows no change after the first commit
just check
uv run pytest packages/tl-schema/tests/test_generate.py -q
```
Plus a drift demonstration, pasted into the report: append `# x` to `generated/models.py`, run `just check` and show it exits
non-zero with `differs: models.py`; run `just gen`, then `just check` passes.
Expected: three generated files (`__init__.py`, `models.py`, `json_schema/core.schema.json`); all tests pass.

## Tests to add
`packages/tl-schema/tests/test_generate.py`:
- `outputs()` has exactly the keys `__init__.py`, `json_schema/core.schema.json`, `models.py`, and a second call returns equal content.
- No output contains `str(SCHEMA_DIR)` or the string of the repo root (determinism across clones).
- `models.py` contains `class Record(` and `class Event(`; the JSON Schema text parses with `json.loads` and its `$defs` has `Record` and `Event`.
- Using `tmp_path`: `main(["--out", str(tmp_path)])` returns 0 and writes the files; `main(["--check", "--out", str(tmp_path)])` returns 0.
  After editing `models.py` in `tmp_path` the check returns 1 and `capsys` shows `differs: models.py`; after deleting a file it shows `missing:`; after adding `extra.py` it shows `stale: extra.py`; `main(["--out", str(tmp_path)])` repairs all three and the check returns 0.
- The committed directory is in sync: `main(["--check"]) == 0`.

## Report requirements
Standard report plus the drift demonstration output and the list of generated files with line counts.

## Escalation triggers
- Stop if a generator output contains an absolute path or timestamp that `chdir` does not remove.
- Stop if `just check` reports pyright errors in `generate.py` that need a change outside *Allowed paths*.

## Blocked

## Decision
