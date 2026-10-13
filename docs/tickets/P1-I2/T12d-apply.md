# P1-I2-T12d — Import: applying a plan

Status: ready
Tier: haiku
Labels: module
Depends on: T12b and T12c merged on `p1/i2` (the test reads the sample file through `read_rows` and plans it with `plan_import`)
Branch: `p1/i2-t12d-import-apply`

## Goal
Importing writes the plan's new documents, all or nothing, and each one's history says it came from the import. `packages/tl-modules/documents/src/tl_mod_documents/imports/apply.py` has `ImportRefusedError` and `apply_plan`'s signature and docstring written; the body raises `NotImplementedError`. You implement it. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1, 29.6.** Bulk import writes through the same commands as a person does, in one unit of work, with a source that names the import job so the history says where each record came from. Nothing is half-imported.

### Specification
- The caller opens the unit of work and passes it in; `apply_plan` never opens or commits one, so a failure rolls back the lot.
- It writes only through `handle_register_document`; it never writes a table.
- The refusals (`ImportRefusedError`) come before anything is written.
- The events' source is `import:<job>`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/documents/src/tl_mod_documents/imports/apply.py` (the stub you complete):
```python
"""Applying an import plan: register the new documents, all or nothing (brief 9 M1; P1-I2-T12d).

The caller opens one unit of work and passes it in; every document of the plan is registered in
it, so a failure on one rolls back the lot. The source of each event is ``import:<job>``, so the
history says where a document came from. The plan is trusted to have been made against the same
ledger a moment before: ``RegisterDocument`` checks everything again and a number that appeared
in between is refused as it would be for anyone.

STUB (P1-I2-T12d): the bodies of apply_plan raise NotImplementedError; their signatures, options,
docstrings and the helpers are final. Each body has a STEPS comment. Implement them, then delete
this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import re

from tl_core.services.commands import CommandResult
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork

from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document
from tl_mod_documents.imports.model import ImportPlan

JOB = re.compile(r"[A-Za-z0-9_.-]{1,64}")


class ImportRefusedError(ServiceError):
    """The plan cannot be applied as it stands (rows that cannot be imported; a bad job name)."""


def apply_plan(
    uow: UnitOfWork,
    scope: str,
    plan: ImportPlan,
    *,
    actor: str,
    job: str,
    skip_invalid: bool = False,
) -> list[CommandResult]:
    """Register the plan's new documents; the results are in the order of ``plan.new``.

    Raises ``ImportRefusedError`` before anything is written when ``job`` is not a short name of
    letters, digits, ``_``, ``.`` and ``-``, or when the plan has invalid rows and ``skip_invalid``
    is false. Anything ``RegisterDocument`` raises stops the import and leaves nothing registered
    (the caller's unit of work rolls back).
    """
    # STEPS
    # 1. When JOB.fullmatch(job) is None raise ImportRefusedError(f"the job name {job!r} must be 1
    #    to 64 letters, digits, '_', '.' or '-'").
    # 2. When plan.invalid and not skip_invalid raise ImportRefusedError(f"{len(plan.invalid)}
    #    row(s) cannot be imported; fix the file or skip them").
    # 3. For each row of plan.new, in order, results.append(handle_register_document(uow,
    #    RegisterDocument(actor=actor, source=f"import:{job}", scope=scope, number=row.number,
    #    title=row.title, description=row.note, doc_type=row.doc_type, discipline=row.discipline,
    #    originator=row.originator))). Write `title=row.title or row.number`: a new row always has
    #    a title, and the fallback only satisfies the type checker.
    # 4. Return the results.
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/documents.py` (excerpts; read-only, do not edit):
```python
class RegisterDocument(Command):
    """Register a document in a project under its number. The number becomes the record key.

    The number must fit the registry numbering pattern for documents when there is one. The type
    and the discipline must be usable values of the code lists ``DocumentType`` and ``Discipline``
    when the company has registered them. The revision scheme defaults from the scheme file.
    """

    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=1, max_length=MAX_NUMBER)
    title: str = Field(min_length=1, max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    doc_type: str | None = Field(default=None, max_length=MAX_NUMBER)
    discipline: str | None = Field(default=None, max_length=MAX_NUMBER)
    originator: str | None = Field(default=None, max_length=MAX_TEXT)
    confidentiality: str | None = Field(
        default=None, max_length=MAX_NUMBER, description=CONFIDENTIALITY_NOTE
    )
    revision_scheme: str | None = Field(default=None, max_length=MAX_NUMBER)


def handle_register_document(uow: UnitOfWork, cmd: RegisterDocument) -> CommandResult:
    """Append ``Record.Created`` and ``Document.Defined``, then move the document to Registered."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-modules/documents/src/tl_mod_documents/imports/apply.py` (the file you edit)
- `packages/tl-modules/documents/src/tl_mod_documents/imports/model.py`, `packages/tl-modules/documents/src/tl_mod_documents/imports/mapping.py`, `packages/tl-modules/documents/src/tl_mod_documents/imports/diff.py` (final or finished by the other tickets)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/documents.py` (`RegisterDocument`)
- `docs/tickets/P1-I2/provided/t12d-test_imports_apply.py.txt` (the test)
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
- `packages/tl-modules/documents/src/tl_mod_documents/imports/apply.py` (edit)
- `packages/tl-modules/documents/tests/test_imports_apply.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T12d.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t12d-test_imports_apply.py.txt` to `packages/tl-modules/documents/tests/test_imports_apply.py`.
3. Implement `apply_plan` by its STEPS comment; remove the STUB paragraph, the STEPS comment and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/documents/tests/test_imports_apply.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/documents/tests/test_imports_apply.py -q --adapters sqlite,postgres
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
