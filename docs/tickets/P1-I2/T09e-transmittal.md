# P1-I2-T09e — `tl transmittal`: create, issue, answer, close, void, ls, show

Status: ready
Tier: haiku
Labels: cli
Depends on: S3, S4 and S6 on `p1/i2`; no other ticket (T08a, the transmittal commands, is merged)
Branch: `p1/i2-t09e-cli-transmittal`

## Goal
A document controller drafts, issues, answers, closes and voids transmittals from the shell. `packages/tl-cli/src/tl_cli/transmittal.py` has the group, its helpers and the seven commands' signatures, options and docstrings final; the seven bodies raise `NotImplementedError`. The group is already registered as `tl transmittal` in `tl_cli/main.py`. You implement the bodies. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1.** `Transmittal`: number, direction, purpose, recipients, items (issued revisions), dates, response code. Workflow Draft -> Issued -> Acknowledged -> Closed, or Void (a draft only). **Brief 9 M10.** Transmittal and review return as items of one register.
>
> **ADR-0011.** Issuing a transmittal is the admin's act (`admin.command.IssueTransmittal`; the CLI calls `require_admin`). Drafting, answering, closing and voiding a draft are open to any signed-in person.
>
> **P1-I2 demo.** `tl transmittal create --project P123 ...` then `tl transmittal issue ...`: the transmittal lists revision B.

### Specification
- **Output is part of the contract**: the test compares lines exactly. The STEPS give the formats.
- A command takes the ledger from the root `--db` (`ctx.obj`), the project from `--project`, and an actor from `--actor` (do not change the default text).
- A failure prints `error: <message>` on stderr and exits 1 with no traceback. `_service_errors()` does that for every service failure and turns an input-validation failure into `error: <field>: <message>`.
- Rules are in the handlers: a command makes the calls its STEPS name and prints. A transmittal is looked up by number with `_transmittal(...)`; revisions are written `NUMBER@CODE` and resolved by `_revision_ids(...)` (both final).
- `issue` calls `require_admin(db)` before anything else; the other commands are open to any signed-in person.
- Reads (`ls`, `show`) open the unit of work with `readonly=True`; writes use `open_uow(db)`.
- Dates: the handlers default to today, refuse the future and need a reason for an earlier date; the commands only pass `--date` and `--date-reason` through.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-cli/src/tl_cli/transmittal.py` (the stub you complete):
```python
"""The `tl transmittal` group: draft, issue, answer, close and void transmittals (brief 9 M1).

A transmittal is one formal exchange of issued revisions with other parties. Each subcommand parses
options, makes one call into `tl_mod_documents` (a handler or a read) and prints. The rules (only
issued revisions, the number pattern, the dates, which state allows what) live in the module.
Transmittals are named by number; revisions as `NUMBER@CODE` (`ISO-1234@B`); the project comes from
`--project`. Issuing a transmittal is an admin's act (ADR-0011).

STUB (P1-I2-T09e): the bodies of the seven commands raise NotImplementedError; their signatures,
options, docstrings and the helpers are final. Each body has a STEPS comment. Implement them,
then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry, views
from tl_mod_documents.handlers.transmittals import (
    CloseTransmittal,
    CreateTransmittal,
    IssueTransmittal,
    Recipient,
    RecordTransmittalResponse,
    VoidTransmittal,
    handle_close_transmittal,
    handle_create_transmittal,
    handle_issue_transmittal,
    handle_record_transmittal_response,
    handle_void_transmittal,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _document,
    _fail,
    _Project,
    _Reason,
    _service_errors,
)
from tl_cli.session import require_admin

app = typer.Typer(help="Draft, issue, answer, close and void transmittals.", no_args_is_help=True)

_Number = Annotated[str, typer.Argument(help="The transmittal number, for example P123-TRN-0001.")]
_Date = Annotated[
    str | None, typer.Option("--date", help="YYYY-MM-DD. Default today; never later.")
]
_DateReason = Annotated[
    str | None, typer.Option("--date-reason", help="Required for a date before today.")
]


def _transmittal(uow: UnitOfWork, scope: str, project: str, number: str) -> registry.TransmittalRow:
    """The transmittal ``number``; exits `error: no transmittal 'X' in project 'P'`."""
    found = registry.find_transmittal(uow.conn(), scope, number)
    if found is None:
        _fail(f"no transmittal {number!r} in project {project!r}")
    return found


def _recipient(text: str) -> Recipient:
    """``Name``, ``Name:Organisation`` or ``Name:Organisation:email`` as a recipient."""
    name, organisation, email = ([*text.split(":", 2), None, None])[:3]
    return Recipient(name=name, organisation=organisation or None, email=email or None)


def _revision_ids(uow: UnitOfWork, scope: str, project: str, items: list[str]) -> list[str]:
    """The revision ids of `NUMBER@CODE` items; exits `error: ...` for a bad item."""
    ids: list[str] = []
    for item in items:
        number, at, code = item.rpartition("@")
        if not at or not number or not code:
            _fail(f"revision {item!r} must be written NUMBER@CODE, for example ISO-1234@B")
        doc = _document(uow, scope, project, number)
        rev = registry.find_revision(uow.conn(), doc.id, code)
        if rev is None:
            _fail(f"no revision {code!r} of {number}")
        ids.append(rev.id)
    return ids


@app.command("create")
def create(
    ctx: typer.Context,
    project: _Project,
    subject: Annotated[str, typer.Option("--subject", help="The transmittal title.")],
    purpose: Annotated[
        str,
        typer.Option(
            "--purpose",
            help="for_review, for_information, for_approval, for_construction, as_built "
            "or for_record.",
        ),
    ],
    to: Annotated[
        list[str],
        typer.Option(
            "--to", help="A recipient: NAME, NAME:ORGANISATION or NAME:ORGANISATION:EMAIL."
        ),
    ],
    revisions: Annotated[
        list[str], typer.Option("--revision", help="An issued revision, NUMBER@CODE. Repeat it.")
    ],
    number: Annotated[
        str | None, typer.Option("--number", help="Default: allocated by the pattern.")
    ] = None,
    direction: Annotated[
        str, typer.Option("--direction", help="outgoing or incoming.")
    ] = "outgoing",
    due: Annotated[str | None, typer.Option("--due", help="YYYY-MM-DD.")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Draft a transmittal of issued revisions to named recipients."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` ids = _revision_ids(uow, scope, project,
    #    revisions); made = handle_create_transmittal(uow, CreateTransmittal(actor=actor,
    #    source="cli", scope=scope, number=number, subject=subject, direction=direction,
    #    purpose=purpose, due_date=due, recipients=[_recipient(t) for t in to],
    #    revision_ids=ids, notes=notes)). `direction` and `purpose` are checked by the model; a
    #    bad value is reported by _service_errors as `error: <field>: <message>`.
    # 3. Print `created transmittal <made.key>` and then `items <len(ids)>`.
    raise NotImplementedError


@app.command("issue")
def issue(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    issued_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Issue a draft transmittal (admin): it is now the record of what was sent."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}"; call require_admin(db) first.
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _transmittal(uow, scope, project,
    #    number); handle_issue_transmittal(uow, IssueTransmittal(actor=actor, source="cli",
    #    scope=scope, stream_id=row.id, issued_on=issued_on, date_reason=date_reason));
    #    after = _transmittal(uow, scope, project, number).
    # 3. Print `issued <number> on <after.issued_on>`.
    raise NotImplementedError


@app.command("answer")
def answer(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    code: Annotated[
        str,
        typer.Option("--code", help="approved, approved_with_comments, rejected or noted."),
    ],
    note: Annotated[str | None, typer.Option("--note")] = None,
    responded_on: _Date = None,
    date_reason: _DateReason = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record the recipients' answer to an issued transmittal."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _transmittal(uow, scope, project,
    #    number); handle_record_transmittal_response(uow, RecordTransmittalResponse.model_validate(
    #    {"actor": actor, "source": "cli", "scope": scope, "stream_id": row.id,
    #    "response_code": code, "response_note": note, "responded_on": responded_on,
    #    "date_reason": date_reason})). A bad `--code` is reported by _service_errors.
    # 3. Print `answered <number>: <code>`.
    raise NotImplementedError


@app.command("close")
def close(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Close an issued or answered transmittal."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _transmittal(uow, scope, project,
    #    number); handle_close_transmittal(uow, CloseTransmittal(actor=actor, source="cli",
    #    scope=scope, stream_id=row.id, reason=reason)).
    # 3. Print `closed <number>`.
    raise NotImplementedError


@app.command("void")
def void(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    reason: _Reason,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Void a draft transmittal drafted in error. An issued one is closed, not voided."""
    # STEPS
    # 1. db: DbTarget = ctx.obj; scope = f"project:{project}".
    # 2. `with _service_errors(), open_uow(db) as uow:` row = _transmittal(uow, scope, project,
    #    number); handle_void_transmittal(uow, VoidTransmittal(actor=actor, source="cli",
    #    scope=scope, stream_id=row.id, reason=reason)).
    # 3. Print `voided <number>`.
    raise NotImplementedError


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    state: Annotated[str | None, typer.Option("--state", help="For example Issued.")] = None,
    direction: Annotated[str | None, typer.Option("--direction")] = None,
) -> None:
    """List a project's transmittals by number: number, state, direction, purpose, items, title."""
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` rows =
    #    registry.list_transmittals(uow.conn(), f"project:{project}", state=state,
    #    direction=direction).
    # 3. For each row print, joined by two spaces: number, "Void" if row.voided else row.state,
    #    direction, purpose, f"items={item_count}", title.
    raise NotImplementedError


@app.command("show")
def show(ctx: typer.Context, number: _Number, project: _Project) -> None:
    """Show a transmittal: its fields, its recipients and its items."""
    # STEPS
    # 1. db: DbTarget = ctx.obj.
    # 2. `with _service_errors(), open_uow(db, readonly=True) as uow:` view =
    #    views.transmittal_view(uow.conn(), f"project:{project}", number) (an unknown number is
    #    the module's TransmittalNotFoundError, printed by _service_errors).
    # 3. Print one `name: value` line each, in this order, with "-" for None: number, title,
    #    state, direction, purpose, issued, due, response (response_code), responded
    #    (responded_on).
    # 4. Then one line per recipient, `recipient <name>` plus `, <organisation>` and
    #    ` <<email>>` when given (for example `recipient Site, Acme <site@acme.test>`).
    # 5. Then one line per item, `item <document_number>@<revision_code> <issue_status or ->`.
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/transmittals.py` (excerpts; read-only, do not edit):
```python
class Recipient(BaseModel):
    """Who receives a transmittal."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_TEXT)
    organisation: str | None = Field(default=None, max_length=MAX_TEXT)
    email: str | None = Field(default=None, max_length=MAX_TEXT)


class CreateTransmittal(Command):
    """Draft a transmittal of issued revisions to named recipients.

    ``number`` is typed in; without it the project's numbering pattern for transmittals allocates
    one (``P123-TRN-0001``). A typed number must fit that pattern for this project. ``subject`` is
    the title.
    """

    model_config = ConfigDict(extra="forbid")

    number: str | None = Field(default=None, min_length=1, max_length=MAX_NUMBER)
    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    direction: Direction = "outgoing"
    purpose: Purpose
    due_date: str | None = None
    recipients: list[Recipient] = Field(min_length=1, max_length=MAX_RECIPIENTS)
    revision_ids: list[str] = Field(min_length=1, max_length=MAX_ITEMS)
    notes: str | None = Field(default=None, max_length=MAX_DESCRIPTION)


class IssueTransmittal(Command):
    """Issue a draft transmittal: it is now the record of what was sent (an admin's act).

    ``issued_on`` defaults to today and is never in the future; an earlier date needs
    ``date_reason``, which the event keeps.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    issued_on: str | None = None
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)


class RecordTransmittalResponse(Command):
    """Record the recipients' answer to an issued transmittal.

    ``responded_on`` follows the same rule as ``IssueTransmittal.issued_on``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    response_code: ResponseCode
    response_note: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    responded_on: str | None = None
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)


class CloseTransmittal(Command):
    """Close an issued or answered transmittal."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class VoidTransmittal(Command):
    """Void a draft transmittal drafted in error. An issued one is closed, not voided."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (excerpts; read-only, do not edit):
```python
@dataclass(frozen=True)
class TransmittalRow:
    id: str
    scope: str
    number: str
    title: str
    description: str | None
    state: str  # Draft, Issued, Acknowledged, Closed, Void
    voided: bool
    version: int
    direction: str
    purpose: str
    due_date: str | None
    issued_on: str | None
    response_code: str | None
    response_note: str | None
    responded_on: str | None
    recipients: list[dict[str, Any]]
    item_count: int
    created_at: str


def find_revision(conn: Connection, document_id: str, code: str) -> RevisionRow | None:
    ...


def find_transmittal(conn: Connection, scope: str, number: str) -> TransmittalRow | None:
    ...


def list_transmittals(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    direction: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[TransmittalRow]:
    """The transmittals of a scope by number; void ones are left out unless asked for by state."""
    ...
```

`packages/tl-modules/documents/src/tl_mod_documents/views.py` (excerpts; read-only, do not edit):
```python
class TransmittalItemView(BaseModel):
    position: int
    document_number: str
    revision_code: str
    issue_status: str | None


class TransmittalView(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    state: str
    direction: str
    purpose: str
    due_date: str | None
    issued_on: str | None
    response_code: str | None
    response_note: str | None
    responded_on: str | None
    recipients: list[dict[str, str | None]]
    version: int
    items: list[TransmittalItemView] = []


def transmittal_view(conn: Connection, scope: str, number: str) -> TransmittalView:
    """One transmittal with its items. Raises ``TransmittalNotFoundError``."""
    ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/transmittal.py` (the file you edit)
- `packages/tl-cli/src/tl_cli/doc.py` and `packages/tl-cli/src/tl_cli/doc_rev.py` (the helpers you import; do not edit)
- `packages/tl-cli/src/tl_cli/tag.py` (a finished group of the same shape; style)
- `packages/tl-cli/tests/doccli_support.py` (the test helpers, already in the tree)
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `packages/tl-modules/documents/src/tl_mod_documents/views.py`
- `docs/tickets/P1-I2/provided/t09e-test_cli_transmittal.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-cli`, `packages/tl-mcp` and `packages/tl-api`.
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
- `packages/tl-cli/src/tl_cli/transmittal.py` (edit)
- `packages/tl-cli/tests/test_cli_transmittal.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T09e.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t09e-test_cli_transmittal.py.txt` to `packages/tl-cli/tests/test_cli_transmittal.py`.
3. Implement the commands by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_transmittal.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-cli/tests/test_cli_transmittal.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 9 test functions pass on SQLite and again on Postgres; the whole tl-cli package passes.

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
