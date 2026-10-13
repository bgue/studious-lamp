# P1-I2-T12e — `tl doc import`: preview and apply a DMS register

Status: ready
Tier: haiku
Labels: cli
Depends on: T12b, T12c and T12d merged on `p1/i2` (the command calls all three)
Branch: `p1/i2-t12e-cli-doc-import`

## Goal
A document controller previews and then applies the import of a legacy DMS register from the shell. `packages/tl-cli/src/tl_cli/doc_import.py` has the command's signature, options and docstring written (already registered as `tl doc import`); `_preview` and `import_documents` raise `NotImplementedError`. You implement them. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1, 29.6.** Bulk import previews first (counts, then a line per row), writes only on `--apply`, and `--apply` is an admin's decision.
>
> **ADR-0011.** Registering a single document is open to any signed-in person; a bulk registration (`--apply`) is the admin's (`require_admin`).

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (do not change the default text).
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure.
- The command makes the calls its STEPS name and prints; the rules are in `tl_mod_documents.imports`. Without `--apply` the unit of work is read-only and nothing is written.
- `require_admin(db)` is called first when `--apply` is given, before the file is read, exactly as `tl tag import --apply` does (P1-I1). The preview stays open to any signed-in person. The command registers documents only, through `apply_plan`; it never passes `by_module`, never issues a revision and never attaches a rendition (ADR-0011). `--skip-invalid` is not a way round the role: the admin check comes first.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/doc_import.py` (the stub you complete):
```python
"""`tl doc import`: preview and apply a legacy document register (brief 9 M1, 29.6; P1-I2-T12d).

The command reads a CSV export of the incumbent DMS with a mapping template, compares it with the
project's register and prints what would happen; with `--apply` it registers the new documents.
Reading, comparing and writing are the module's (`tl_mod_documents.imports`); this command parses
options and prints. It registers documents only: the old register's revision, status and date are a
note in the description, and the revisions come with the P1-I8 legacy loaders. It is registered by
`tl_cli.main` as `tl doc import`.

STUB (P1-I2-T12e): the bodies of _preview and import_documents raise NotImplementedError; their
signatures, options, docstrings and the helpers are final. Each body has a STEPS comment.
Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents.imports.apply import apply_plan
from tl_mod_documents.imports.diff import plan_import
from tl_mod_documents.imports.mapping import MappingError, load_mapping, read_rows
from tl_mod_documents.imports.model import ImportPlan

from tl_cli.doc import _DEFAULT_ACTOR, _Actor, _fail, _Project, _service_errors
from tl_cli.session import require_admin


def _preview(plan: ImportPlan) -> None:
    """The counts line, then one line per new, existing and invalid row.

    ``new=9  exists=1  invalid=7`` and then, in this order: ``+ <number>  <type or ->  <title>``
    for each new row, ``= <number>`` for each number the project already has, and ``! line <n>:
    <problems joined by "; ">`` for each invalid row.
    """
    # STEPS
    # 1. counts = plan.counts(); print "  ".join(f"{name}={counts[name]}" for name in counts).
    # 2. For each row of plan.new print f"+ {row.number}  {row.doc_type or '-'}  {row.title}".
    # 3. For each number of plan.exists print f"= {number}".
    # 4. For each row of plan.invalid print f"! line {row.line}: {'; '.join(row.problems)}".
    raise NotImplementedError


def import_documents(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="The CSV file to import.")],
    project: _Project,
    mapping: Annotated[
        Path, typer.Option("--mapping", help="The mapping template (YAML) for this file.")
    ],
    apply: Annotated[
        bool, typer.Option("--apply", help="Register the new documents (admin). Default: preview.")
    ] = False,
    skip_invalid: Annotated[
        bool, typer.Option("--skip-invalid", help="Import the valid rows and leave the others out.")
    ] = False,
    job: Annotated[
        str | None, typer.Option("--job", help="Names the import in the history (default: file).")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Compare a DMS register export with the project's documents; with --apply, register them."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; job = job or file.stem. When apply
    #    is true call require_admin(db) first (a bulk registration is an admin's decision).
    # 2. `with _service_errors():` template = load_mapping(mapping); text =
    #    file.read_text(encoding="utf-8"); rows = read_rows(text, template). A MappingError from
    #    load_mapping or read_rows is _fail(str(exc)); an OSError or UnicodeDecodeError reading
    #    the file is _fail(f"{file.name}: cannot read file: {exc}").
    # 3. Print f"import {template.name} {file.name} into project {project}".
    # 4. `with open_uow(db, readonly=not apply) as uow:` plan = plan_import(uow.conn(), scope,
    #    rows); _preview(plan). When not apply: print "dry run: nothing written; add --apply to
    #    write" and return. Otherwise results = apply_plan(uow, scope, plan, actor=actor, job=job,
    #    skip_invalid=skip_invalid).
    # 5. Print f"applied {job}: registered={len(results)}  skipped={len(plan.exists) +
    #    len(plan.invalid)}".
    raise NotImplementedError
```

`tl_mod_documents.imports` (finished by T12b, T12c, T12d; signatures):
```python
def load_mapping(path: Path) -> DocumentMapping: ...   # raises MappingError
def read_rows(text: str, mapping: DocumentMapping) -> list[ImportRow]: ...   # raises MappingError
def plan_import(conn: Connection, scope: str, rows: list[ImportRow]) -> ImportPlan: ...
def apply_plan(uow, scope, plan, *, actor: str, job: str, skip_invalid: bool = False) -> list[CommandResult]: ...
# ImportPlan.counts() -> {'new': n, 'exists': n, 'invalid': n}
```

`packages/tl-cli/src/tl_cli/session.py`:
```python
def require_admin(db: DbTarget) -> Principal: ...
# Exits with `error: forbidden: this command needs the admin role` for anyone who is not an admin.
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/doc_import.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/doc.py` (the helpers you import; do not edit)
- `packages/tl-cli/src/tl_cli/tag_import.py` or the nearest equivalent (the same command for tags; style)
- `packages/tl-cli/tests/doccli_support.py` (test helpers, already in the tree)
- `docs/tickets/P1-I2/provided/t12e-test_cli_doc_import.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run only the scoped commands in *Acceptance* (a ticket whose tests do not use the database fixtures has no Postgres command), never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- On Postgres the tl-cli `conftest.py` signs a test admin in for you (L-P1-I0B-8); the test skips the refusal part there (`doccli_support.admin_session` returns False).
- `doc.py` and `main.py` are final; do not edit them.

## Allowed paths
- `packages/tl-cli/src/tl_cli/doc_import.py` (edit)
- `packages/tl-cli/tests/test_cli_doc_import.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T12e.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t12e-test_cli_doc_import.py.txt` to `packages/tl-cli/tests/test_cli_doc_import.py`.
3. Implement `_preview` and `import_documents` by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_doc_import.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_doc_import.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 6 test functions pass (on SQLite and again on Postgres); the whole package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run (the `--adapters sqlite,postgres` command in Acceptance).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `tl_mod_documents` or in another `tl_cli` file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
