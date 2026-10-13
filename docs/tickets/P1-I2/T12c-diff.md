# P1-I2-T12c — Import: the plan (what a file would do)

Status: ready
Tier: haiku
Labels: module
Depends on: T12b merged on `p1/i2` (the plan test reads the sample file through `read_rows`)
Branch: `p1/i2-t12c-import-plan`

## Goal
Before anything is written, an import says what it would do: which rows would register a document, which numbers the project already has, and which rows cannot be imported and why. `packages/tl-modules/documents/src/tl_mod_documents/imports/diff.py` has `plan_import`'s signature and docstring written; its body raises `NotImplementedError`. You implement it. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1, 29.6.** The import previews: new, existing and invalid, each invalid row with its reasons, before `--apply` writes.
>
> **Existing rule.** `RegisterDocument` is the one place that decides whether a number, a type and a discipline are acceptable; `register_problems` (in `handlers/documents.py`, final) asks it the same questions without writing.

### Specification
- `plan_import` reads and writes nothing (one `Connection`, no unit of work).
- The reasons added to a row are text the test compares exactly; the STEPS give them. Rows are judged in file order and the plan lists them in file order.
- A repeated number in the file is refused from its second occurrence on; the first is judged normally.
- Do not change `model.py`, `register_problems` or the mapping.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/documents/src/tl_mod_documents/imports/diff.py` (the stub you complete):
```python
"""Comparing a read file with the project's register: the import plan (brief 9 M1; P1-I2-T12c).

``plan_import`` checks every row the way ``RegisterDocument`` will (the number against the registry
pattern, the type and discipline against their code lists) and against the register, and says what
would happen: register it, skip it because the project already has the number, or refuse it with
the reasons. It reads and writes nothing.

STUB (P1-I2-T12c): the bodies of plan_import raise NotImplementedError; their signatures, options,
docstrings and the helpers are final. Each body has a STEPS comment. Implement them, then delete
this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import Connection

from tl_mod_documents import registry
from tl_mod_documents.handlers.documents import register_problems
from tl_mod_documents.imports.model import ImportPlan, ImportRow


def plan_import(conn: Connection, scope: str, rows: list[ImportRow]) -> ImportPlan:
    """What importing ``rows`` into ``scope`` would do, row by row, in file order.

    A row is **invalid** when it carries problems from the mapping, has no title, repeats a number
    an earlier row of the file has, or breaks a rule of ``RegisterDocument``
    (``register_problems``); its reasons are added to its ``problems``. A valid row whose number the
    scope already holds is **exists** (listed by number, once); the others are **new**.
    """
    # STEPS
    # 1. plan = ImportPlan(); first_line: dict[str, int] = {} (number to the line it first appeared
    #    on, for every row with a non-blank number).
    # 2. For each row, in order: problems = list(row.problems). If row.number is non-blank and in
    #    first_line, append f"the number appears again; first on line {first_line[row.number]}";
    #    otherwise (and when non-blank) first_line[row.number] = row.line. If row.title is None,
    #    append "the title is blank". When problems is still empty and the number is non-blank,
    #    extend it with register_problems(conn, scope, row.number, row.doc_type, row.discipline).
    # 3. With problems: plan.invalid.append(replace(row, problems=problems)). Else if
    #    registry.find_document(conn, scope, row.number) is not None: plan.exists.append(row.number)
    #    (no repeats: the second occurrence of a number was already refused above). Else
    #    plan.new.append(row).
    # 4. Return plan.
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/imports/model.py` (final; read-only): `ImportRow` (line, number, title, doc_type, discipline, originator, legacy_revision, legacy_status, legacy_date, problems, raw) and `ImportPlan` (new, exists, invalid; `counts()`).
```text
ImportPlan.new: list[ImportRow]; ImportPlan.exists: list[str]; ImportPlan.invalid: list[ImportRow]
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/documents.py` (excerpts; read-only, do not edit):
```python
def register_problems(
    conn: Connection, scope: str, number: str, doc_type: str | None, discipline: str | None
) -> list[str]:
    """Why ``RegisterDocument`` would refuse this number, type and discipline (else empty)."""
    ...
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (excerpts; read-only, do not edit):
```python
def find_document(conn: Connection, scope: str, number: str) -> DocumentRow | None:
    ...
```

## Context (read these, nothing else)
- `packages/tl-modules/documents/src/tl_mod_documents/imports/diff.py` (the file you edit)
- `packages/tl-modules/documents/src/tl_mod_documents/imports/model.py` and `packages/tl-modules/documents/src/tl_mod_documents/imports/mapping.py` (final)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/documents.py` (`register_problems`)
- `packages/tl-modules/documents/tests/docworld.py` (the test world, already in the tree)
- `docs/tickets/P1-I2/provided/t12c-test_imports_plan.py.txt` (the test)
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
- A test that uses the `world` fixture runs once per adapter; run it on both (Acceptance).

## Allowed paths
- `packages/tl-modules/documents/src/tl_mod_documents/imports/diff.py` (edit)
- `packages/tl-modules/documents/tests/test_imports_plan.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T12c.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t12c-test_imports_plan.py.txt` to `packages/tl-modules/documents/tests/test_imports_plan.py`.
3. Implement `plan_import` by its STEPS comment; remove the STUB paragraph, the STEPS comment and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/documents/tests/test_imports_plan.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/documents/tests/test_imports_plan.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules/documents -q
```
Expected: `just check` clean; 7 test functions pass (on SQLite and again on Postgres); the whole package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run (the `--adapters sqlite,postgres` command in Acceptance).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
