# P1-I2-T11b — `tl doc report`: register, history, overdue, transmittals, stale

Status: ready
Tier: haiku
Labels: cli
Depends on: S3, S4 and S6 on `p1/i2`; T11a (merged: `tl_mod_documents.reports`)
Branch: `p1/i2-t11b-cli-doc-report`

## Goal
A document controller reads the base reports from the shell. `packages/tl-cli/src/tl_cli/doc_report.py` has the group, a date helper and the five commands' signatures, options and docstrings final; the five bodies raise `NotImplementedError`. The group is already registered as `tl doc report`. You implement the bodies. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 15 base reports (documents).** Register; revision history of a document; overdue reviews; transmittal log; documents by status or discipline; stale pinned revisions.
>
> **Existing pattern.** `tl tag report summary|missing|violations` (`tag_report.py`) reads through a module's `reports` functions and prints one line per row, or JSON with `--json`.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`) and the project from `--project`. Reports only read: open the unit of work with `readonly=True`.
- `--json` prints the dataclass rows with `json.dumps(..., indent=2)` through `_dump` (final).
- `--on YYYY-MM-DD` fixes the day "overdue" is judged on; `_day` (final) turns a bad date into `error: --on must be a date written YYYY-MM-DD, got '...'`.
- A failure prints `error: <message>` on stderr and exits 1 with no traceback (`_service_errors()`).

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/doc_report.py` (the stub you complete):
```python
"""The `tl doc report` group: the document-control base reports (brief 15; P1-I2-T11b).

Each subcommand reads through `tl_mod_documents.reports` and prints one line per row (or JSON with
`--json`). Nothing is written. The reports are: the document register, one document's revision
history, overdue reviews, the transmittal log and stale pinned revisions.

STUB (P1-I2-T11b): the bodies of the five commands raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_documents import reports

from tl_cli.doc import _fail, _Project, _service_errors

app = typer.Typer(help="Document control reports.", no_args_is_help=True)

_Json = Annotated[bool, typer.Option("--json", help="Print JSON.")]
_On = Annotated[
    str | None,
    typer.Option("--on", help="Judge 'overdue' on this day (YYYY-MM-DD). Default today."),
]


def _day(value: str | None) -> date | None:
    """``value`` as a date, ``None`` when it is ``None``; anything else exits `error: ...`."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail(f"--on must be a date written YYYY-MM-DD, got {value!r}")


def _dump(lines: Sequence[Any]) -> None:
    typer.echo(json.dumps([asdict(line) for line in lines], indent=2))


@app.command("register")
def register(
    ctx: typer.Context,
    project: _Project,
    doc_type: Annotated[str | None, typer.Option("--type")] = None,
    discipline: Annotated[str | None, typer.Option("--discipline")] = None,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    as_json: _Json = False,
) -> None:
    """The document register: number, state, current revision, type, discipline, counts, title."""
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.document_register(uow.conn(), f"project:{project}", doc_type=doc_type,
    #    discipline=discipline, state=state).
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: number, state, current (`<code>(<status>)` from
    #    current_code and current_status, or "-"), doc_type or "-", discipline or "-",
    #    f"revisions={revisions}", f"open={open_code or '-'}", f"stale={stale_links}", title.
    raise NotImplementedError


@app.command("history")
def history(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The document number.")],
    project: _Project,
    as_json: _Json = False,
) -> None:
    """One document's revisions, oldest first, with renditions, transmittals and review outcome."""
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.revision_history(uow.conn(), f"project:{project}", number). An unknown number
    #    raises a ServiceError that _service_errors prints as `error: ...`.
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: code, state, issue_status or "-", status_class or
    #    "-", issued_on or "-", "current" or "-" (is_current), f"renditions={renditions}",
    #    f"transmittals={','.join(transmittals) or '-'}", f"review={review_outcome or '-'}",
    #    f"superseded_by={superseded_by or '-'}".
    raise NotImplementedError


@app.command("overdue")
def overdue(ctx: typer.Context, project: _Project, on: _On = None, as_json: _Json = False) -> None:
    """Reviews still open and unanswered after their date: the revision, the cycle, the reviewer."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; day = _day(on) (final helper).
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.overdue_reviews(uow.conn(), f"project:{project}", on=day).
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: f"{document_number}@{revision_code}", cycle_key,
    #    reviewer, f"due={due_date}", f"{days_overdue}d overdue".
    raise NotImplementedError


@app.command("transmittals")
def transmittals(
    ctx: typer.Context,
    project: _Project,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    direction: Annotated[
        str | None, typer.Option("--direction", help="outgoing or incoming.")
    ] = None,
    on: _On = None,
    as_json: _Json = False,
) -> None:
    """The transmittal log: number, state, direction, purpose, dates, answer, items, overdue."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; day = _day(on).
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.transmittal_log(uow.conn(), f"project:{project}", state=state,
    #    direction=direction, on=day).
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: number, state, direction, purpose,
    #    f"issued={issued_on or '-'}", f"due={due_date or '-'}", f"response={response_code or
    #    '-'}", f"items={items}", and the word "overdue" last only when `overdue` is true.
    raise NotImplementedError


@app.command("stale")
def stale(ctx: typer.Context, project: _Project, as_json: _Json = False) -> None:
    """Stale pinned revisions: the document, the pin, what is current, who links, the link id."""
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` lines =
    #    reports.stale_pins(uow.conn(), f"project:{project}").
    # 3. With --json call _dump(lines) and return.
    # 4. Otherwise print, joined by two spaces: document_number, f"pinned={pinned_code or '-'}",
    #    f"current={current_code or '-'}", f"newer={','.join(newer_codes) or '-'}",
    #    f"{linked_key or '-'}", link_id.
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/reports.py` (excerpts; read-only, do not edit):
```python
@dataclass(frozen=True)
class RegisterLine:
    """One document in the register."""

    number: str
    title: str
    doc_type: str | None
    discipline: str | None
    state: str
    current_code: str | None
    current_status: str | None
    current_class: str | None
    current_issued_on: str | None
    revisions: int  # revisions that are not void
    open_code: str | None  # the revision being prepared or reviewed
    stale_links: int  # links to the document whose status is stale


@dataclass(frozen=True)
class HistoryLine:
    """One revision in a document's history."""

    code: str
    ordinal: int
    state: str
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    purpose: str | None
    change_note: str | None
    renditions: int  # current renditions
    transmittals: list[str]  # numbers of the transmittals that carry it
    review_outcome: str | None  # outcome of the latest closed review cycle
    superseded_by: str | None  # the code of the revision that replaced it


@dataclass(frozen=True)
class OverdueLine:
    """A reviewer who should have answered by now."""

    document_number: str
    revision_code: str
    cycle_key: str
    reviewer: str
    due_date: str
    days_overdue: int


@dataclass(frozen=True)
class TransmittalLine:
    """One transmittal in the log."""

    number: str
    title: str
    direction: str
    purpose: str
    state: str
    issued_on: str | None
    due_date: str | None
    response_code: str | None
    responded_on: str | None
    items: int
    overdue: bool  # issued, not answered, and the due date has passed


@dataclass(frozen=True)
class StalePinLine:
    """A link pinned to a revision that a newer issue has replaced (or flagged stale)."""

    document_number: str
    document_title: str
    pinned_code: str | None
    current_code: str | None
    current_status: str | None
    linked_key: str | None
    linked_type: str
    link_id: str
    link_status: str
    newer_codes: list[str]


def document_register(
    conn: Connection,
    scope: str,
    *,
    doc_type: str | None = None,
    discipline: str | None = None,
    state: str | None = None,
    limit: int = 1000,
) -> list[RegisterLine]:
    """The documents of a project by number, with the facts a register shows."""
    ...


def revision_history(conn: Connection, scope: str, number: str) -> list[HistoryLine]:
    """Every revision of a document, oldest first, with its renditions, transmittals and review."""
    ...


def overdue_reviews(conn: Connection, scope: str, *, on: date | None = None) -> list[OverdueLine]:
    """Reviewers of open review cycles who have not answered and whose due date has passed."""
    ...


def transmittal_log(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    on: date | None = None,
) -> list[TransmittalLine]:
    """The transmittals of a project by number. A void one is left out unless ``state`` is Void."""
    ...


def stale_pins(conn: Connection, scope: str) -> list[StalePinLine]:
    """Links pinned to a revision that has been replaced, or flagged stale, by document and record."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/doc_report.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/doc.py` and `packages/tl-cli/src/tl_cli/doc_rev.py` (the helpers you import; do not edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; style)
- `packages/tl-modules/documents/src/tl_mod_documents/reports.py`
- `packages/tl-cli/src/tl_cli/tag_report.py`
- `packages/tl-cli/tests/doccli_support.py` (the test helpers, already in the tree)
- `docs/tickets/P1-I2/provided/t11b-test_cli_doc_report.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-cli`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run the scoped command in *Acceptance*, never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- On Postgres the tl-cli `conftest.py` signs a test admin in for you (L-P1-I0B-8); a command that needs the admin role runs as that admin there, and the test skips the refusal part (`doccli_support.admin_session` returns False).
- A signed-in person is needed for the admin commands of this group on SQLite: the test bootstraps `root` and signs in (`admin_session`), then `ordinary_env` gives a second, non-admin person.
- `doc.py` is merged and final. `doc_rev.py` is another ticket's file (T09b): its helpers `_Number`, `_Code` and `_revision` are final in the tree, its command bodies may still be stubs. Import the helpers; do not copy them and do not edit either file.

## Allowed paths
- `packages/tl-cli/src/tl_cli/doc_report.py` (edit)
- `packages/tl-cli/tests/test_cli_doc_report.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T11b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t11b-test_cli_doc_report.py.txt` to `packages/tl-cli/tests/test_cli_doc_report.py`.
3. Implement the commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_doc_report.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_doc_report.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 6 test functions pass on SQLite and again on Postgres; the whole tl-cli package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in `tl_mod_documents` or in another `tl_cli` file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
