# P1-I2-T08a — Transmittal commands: create, issue, record the answer, close, void

Status: ready
Tier: haiku
Labels: core
Depends on: S3 and S4 on `p1/i2` (projectors, registry reads, workflows); no other ticket
Branch: `p1/i2-t08a-transmittal-commands`

## Goal
A person (or the CLI, API and TUI that come after this ticket) can draft a transmittal of issued revisions, issue it, record the recipients' answer, close it, or void a draft. `packages/tl-modules/documents/src/tl_mod_documents/handlers/transmittals.py` has the command classes, the helpers and the five handler signatures final; the five bodies raise `NotImplementedError`. You implement the bodies. One provided test file (17 test functions) must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1.** `Transmittal`: number, direction, recipients, purpose, due date, response code. Cross-references: revisions included, correspondence. Workflows: a transmittal is a Document-control domain item of the correspondence core (M10), so all formal exchanges sit in one register.
>
> **Brief 24 (ledger).** Events are immutable. A correction is a new event. A void is `Record.Voided`; a move between workflow states is `Workflow.Transitioned`.

### Specification
- A transmittal is the module record `documents.Transmittal` (an envelope row in `cur_core_record` plus a typed row in `cur_documents_transmittal` and one row per revision in `cur_documents_transmittal_item`). The projector `TransmittalProjector` already writes them from `Transmittal.Defined`, `Transmittal.Issued`, `Transmittal.ResponseRecorded`. Your handlers only append events.
- Workflow `documents.transmittal` (`schema/fixtures/workflows/documents-transmittal.yaml`): Draft -> Issued -> Acknowledged -> Closed, and Draft -> Void. A moved record's state is `registry.TransmittalRow.state`. The generic `TransitionWorkflow` is closed to this record type: the module moves it with `transition(...)` from `handlers/common.py` (already written).
- A transmittal carries issued revisions only: state `Issued` or `Superseded` and not voided (`CARRIABLE`, `_check_revisions`). It carries a revision once.
- The number is typed in (`cmd.number`) or, when `None`, allocated by the project's numbering pattern for transmittals (`P123-TRN-0001`). `create_module_record(..., key=cmd.number)` does both; `Transmittal.Defined` carries the final number, so it is appended after `Record.Created` in a second append.
- Every refusal is a `ServiceError` raised before anything is appended; nothing is written when a handler raises. All the events of one command share one correlation id (`correlated(cmd)` makes sure there is one).
- `expected_version` (when the command has one) is passed to the first append or transition of the handler; the helper `append(..., expected=...)` and `transition(..., expected=...)` take it. A wrong version raises `ConcurrencyError`.
- Who may call what is decided by the entry point (the API table gives every transmittal command the `user` access); the handlers do not look at roles.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/documents/src/tl_mod_documents/handlers/transmittals.py` (the stub you complete):
```python
"""Transmittal commands: create, issue, record the answer, close, void (brief 9 M1; P1-I2).

A transmittal (``documents.Transmittal``) is one formal exchange of issued revisions with other
parties. It is drafted with its items and recipients, issued once, answered, and closed. Its number
is typed in or, when the project has a numbering pattern for transmittals, allocated. Only a draft
can be voided: an issued transmittal is the record of what was sent.

=========  =====================================================  =============
State      Meaning                                                Next
=========  =====================================================  =============
Draft      being composed                                         issue, void
Issued     sent; waiting for an answer                            acknowledge, close
Acknowledged  the recipients answered                             close
Closed     finished                                               none
Void       drafted in error                                       none
=========  =====================================================  =============

Each handler runs inside an entered unit of work, appends through it and never commits. A failed
check raises a ``ServiceError`` before anything is appended. All events of one command share one
correlation id.

STUB (P1-I2-T08a): the bodies of the five `handle_*` functions raise NotImplementedError; the
command classes, `_load`, `_require_state`, `_check_revisions` and every signature are final. Each
body has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the
`ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_documents import registry
from tl_mod_documents.errors import (
    InvalidTransmittalError,
    RevisionNotFoundError,
    TransmittalNotFoundError,
    TransmittalStateError,
)
from tl_mod_documents.handlers.common import (
    append,
    check_date,
    correlated,
    load_revision,
    require_project,
    today,
    transition,
)
from tl_mod_documents.limits import (
    MAX_DESCRIPTION,
    MAX_ITEMS,
    MAX_NUMBER,
    MAX_REASON,
    MAX_RECIPIENTS,
    MAX_TEXT,
)
from tl_mod_documents.names import (
    TRANSMITTAL,
    TRANSMITTAL_DEFINED,
    TRANSMITTAL_ISSUED,
    TRANSMITTAL_RESPONSE,
)

Direction = Literal["outgoing", "incoming"]
Purpose = Literal[
    "for_review",
    "for_information",
    "for_approval",
    "for_construction",
    "as_built",
    "for_record",
]
ResponseCode = Literal["approved", "approved_with_comments", "rejected", "noted"]
#: Revision states a transmittal may carry: issued, current or since superseded.
CARRIABLE = ("Issued", "Superseded")


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class Recipient(BaseModel):
    """Who receives a transmittal."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_TEXT)
    organisation: str | None = Field(default=None, max_length=MAX_TEXT)
    email: str | None = Field(default=None, max_length=MAX_TEXT)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _non_blank(value)


class CreateTransmittal(Command):
    """Draft a transmittal of issued revisions to named recipients.

    ``number`` is typed in; without it the project's numbering pattern for transmittals allocates
    one (``P123-TRN-0001``). ``subject`` is the title.
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

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return _non_blank(value)

    @field_validator("due_date")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return check_date(value, "due_date")


class IssueTransmittal(Command):
    """Issue a draft transmittal: it is now the record of what was sent."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    issued_on: str | None = None

    @field_validator("issued_on")
    @classmethod
    def _issued(cls, value: str | None) -> str | None:
        return check_date(value, "issued_on")


class RecordTransmittalResponse(Command):
    """Record the recipients' answer to an issued transmittal."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    response_code: ResponseCode
    response_note: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    responded_on: str | None = None

    @field_validator("responded_on")
    @classmethod
    def _responded(cls, value: str | None) -> str | None:
        return check_date(value, "responded_on")


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

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


def _load(uow: UnitOfWork, cmd: Command, transmittal_id: str) -> registry.TransmittalRow:
    found = registry.get_transmittal(uow.conn(), transmittal_id)
    if found is None or found.scope != cmd.scope:
        raise TransmittalNotFoundError(f"no transmittal {transmittal_id!r} in scope {cmd.scope!r}")
    return found


def _require_state(row: registry.TransmittalRow, *allowed: str, doing: str) -> None:
    if row.voided or row.state not in allowed:
        raise TransmittalStateError(
            f"transmittal {row.number} is {'Void' if row.voided else row.state}; "
            f"it can only be {doing} while {' or '.join(allowed)}"
        )


def _check_revisions(rows: list[registry.RevisionRow]) -> None:
    bad = [
        f"{r.document_number}@{r.code} is {'Void' if r.voided else r.state}"
        for r in rows
        if r.voided or r.state not in CARRIABLE
    ]
    if bad:
        raise InvalidTransmittalError(
            "a transmittal carries issued revisions only; " + "; ".join(bad)
        )


def handle_create_transmittal(uow: UnitOfWork, cmd: CreateTransmittal) -> CommandResult:
    """Append ``Record.Created`` and ``Transmittal.Defined``: a draft with its items.

    Raises ``ProjectScopeError``, ``RevisionNotFoundError`` (an item is unknown or in another
    scope), ``InvalidTransmittalError`` (a revision is repeated, or is not issued),
    ``NoNumberingPatternError`` (no number given and no pattern) and ``DuplicateKeyError``.
    """
    # STEPS
    # 1. require_project(cmd); cmd = correlated(cmd).
    # 2. If cmd.revision_ids has a repeated id raise InvalidTransmittalError("a revision can be
    #    on a transmittal only once").
    # 3. revisions = [load_revision(uow, cmd, rid) for rid in cmd.revision_ids] (it raises
    #    RevisionNotFoundError for an unknown id or another scope); then
    #    _check_revisions(revisions).
    # 4. items = one dict per revision, in the order given, with exactly the keys revision_id
    #    (r.id), document_id, document_number, revision_code (r.code) and issue_status.
    # 5. made = create_module_record(uow, cmd, record_type=TRANSMITTAL, title=cmd.subject,
    #    description=cmd.notes, key=cmd.number). A key of None lets the numbering allocator
    #    number it.
    # 6. The number is known only now, so the typed event is a second append on the same stream:
    #    done = append(uow, cmd, made.stream_id, TRANSMITTAL,
    #    [NewEvent(event_type=TRANSMITTAL_DEFINED, payload={"number": made.key, "direction":
    #    cmd.direction, "purpose": cmd.purpose, "due_date": cmd.due_date, "recipients":
    #    [r.model_dump() for r in cmd.recipients], "items": items})]).
    # 7. Return CommandResult(stream_id=made.stream_id, key=made.key, version=done.new_version,
    #    events=[*made.events, *done.events]).
    raise NotImplementedError


def handle_issue_transmittal(uow: UnitOfWork, cmd: IssueTransmittal) -> CommandResult:
    """Append ``Transmittal.Issued`` and move the transmittal to Issued.

    Raises ``TransmittalNotFoundError``, ``TransmittalStateError`` (not a draft) and
    ``InvalidTransmittalError`` (a revision on it has been voided since it was drafted).
    """
    # STEPS
    # 1. cmd = correlated(cmd); row = _load(uow, cmd, cmd.stream_id); _require_state(row,
    #    "Draft", doing="issued").
    # 2. For each item of registry.transmittal_items(uow.conn(), row.id) read the revision with
    #    registry.get_revision(uow.conn(), item.revision_id) (None: raise RevisionNotFoundError(
    #    f"revision {item.revision_id!r} is gone")); then _check_revisions(the list of
    #    revisions).
    # 3. done = append(uow, cmd, row.id, TRANSMITTAL, [NewEvent(event_type=TRANSMITTAL_ISSUED,
    #    payload={"issued_on": cmd.issued_on or today()})], expected=cmd.expected_version).
    # 4. moved = transition(uow, cmd, row.id, "issue").
    # 5. Return CommandResult(stream_id=row.id, key=row.number, version=moved.version,
    #    events=[*done.events, *moved.events]).
    raise NotImplementedError


def handle_record_transmittal_response(
    uow: UnitOfWork, cmd: RecordTransmittalResponse
) -> CommandResult:
    """Append ``Transmittal.ResponseRecorded`` and move the transmittal to Acknowledged.

    Raises ``TransmittalNotFoundError`` and ``TransmittalStateError`` (not issued).
    """
    # STEPS
    # 1. cmd = correlated(cmd); row = _load(uow, cmd, cmd.stream_id); _require_state(row,
    #    "Issued", doing="answered").
    # 2. done = append(uow, cmd, row.id, TRANSMITTAL, [NewEvent(event_type=TRANSMITTAL_RESPONSE,
    #    payload={"response_code": cmd.response_code, "response_note": cmd.response_note,
    #    "responded_on": cmd.responded_on or today()})], expected=cmd.expected_version).
    # 3. moved = transition(uow, cmd, row.id, "acknowledge").
    # 4. Return CommandResult(stream_id=row.id, key=row.number, version=moved.version,
    #    events=[*done.events, *moved.events]).
    raise NotImplementedError


def handle_close_transmittal(uow: UnitOfWork, cmd: CloseTransmittal) -> CommandResult:
    """Move an issued or answered transmittal to Closed (``Workflow.Transitioned``).

    Raises ``TransmittalNotFoundError`` and ``TransmittalStateError``.
    """
    # STEPS
    # 1. cmd = correlated(cmd); row = _load(uow, cmd, cmd.stream_id); _require_state(row,
    #    "Issued", "Acknowledged", doing="closed").
    # 2. Return transition(uow, cmd, row.id, "close", reason=cmd.reason,
    #    expected=cmd.expected_version).model_copy(update={"key": row.number}).
    raise NotImplementedError


def handle_void_transmittal(uow: UnitOfWork, cmd: VoidTransmittal) -> CommandResult:
    """Move a draft transmittal to Void and void its record.

    Emits ``Workflow.Transitioned`` and ``Record.Voided``. Raises ``TransmittalNotFoundError`` and
    ``TransmittalStateError`` (not a draft).
    """
    # STEPS
    # 1. cmd = correlated(cmd); row = _load(uow, cmd, cmd.stream_id); _require_state(row,
    #    "Draft", doing="voided").
    # 2. moved = transition(uow, cmd, row.id, "void", reason=cmd.reason,
    #    expected=cmd.expected_version).
    # 3. voided = append(uow, cmd, row.id, TRANSMITTAL, [NewEvent(event_type="Record.Voided",
    #    payload={"reason": cmd.reason})]).
    # 4. Return CommandResult(stream_id=row.id, key=row.number, version=voided.new_version,
    #    events=[*moved.events, *voided.events]).
    raise NotImplementedError
```

`packages/tl-modules/documents/src/tl_mod_documents/handlers/common.py` (helpers, already written; signatures):
```python
def require_project(cmd: Command) -> None: ...

def correlated[C: Command](cmd: C) -> C: ...

def check_date(value: str | None, what: str) -> str | None: ...

def today() -> str: ...

def version_of(uow: UnitOfWork, record_id: str) -> int: ...

def append(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    stream_type: str,
    events: list[NewEvent],
    *,
    expected: int | None = None,
) -> AppendResult: ...

def transition(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    name: str,
    *,
    reason: str | None = None,
    expected: int | None = None,
) -> CommandResult: ...

def load_document(uow: UnitOfWork, cmd: Command, document_id: str) -> registry.DocumentRow: ...

def open_document(uow: UnitOfWork, cmd: Command, document_id: str) -> registry.DocumentRow: ...

def load_revision(uow: UnitOfWork, cmd: Command, revision_id: str) -> registry.RevisionRow: ...
```

`packages/tl-modules/documents/src/tl_mod_documents/registry.py` (reads, already written; the parts you use):
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

@dataclass(frozen=True)
class TransmittalItemRow:
    transmittal_id: str
    position: int
    revision_id: str
    document_id: str
    document_number: str
    revision_code: str
    issue_status: str | None

@dataclass(frozen=True)
class RevisionRow:
    id: str
    scope: str
    document_id: str
    document_number: str
    key: str
    title: str
    code: str
    ordinal: int
    state: str  # Draft, In Review, Issued, Superseded, Void
    voided: bool
    version: int
    previous_revision_id: str | None
    purpose: str | None
    change_note: str | None
    revision_date: str | None
    intended_status: str | None
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    superseded_by: str | None

    @property
    def issued(self) -> bool:
        return self.issued_on is not None

    @property
    def open(self) -> bool:
        return self.state in OPEN_STATES and not self.voided

def get_transmittal(conn: Connection, transmittal_id: str) -> TransmittalRow | None: ...

def transmittal_items(conn: Connection, transmittal_id: str) -> list[TransmittalItemRow]: ...

def get_revision(conn: Connection, revision_id: str) -> RevisionRow | None: ...
```

`packages/tl-core/src/tl_core/services/commands.py` and `records.py` (the core calls the stub uses; signatures):
```python
class Command(BaseModel):
    actor: str
    source: str
    scope: str
    correlation_id: str | None = None
    causation_id: str | None = None

class CommandResult(BaseModel):
    stream_id: str
    key: str | None
    version: int
    events: list[Event]

def create_module_record(
    uow: UnitOfWork,
    cmd: Command,
    *,
    record_type: str,
    title: str,
    key: str | None,
    description: str | None = None,
    extra_events: Sequence[NewEvent] = (),
    numbering: dict[str, str] | None = None,
) -> CommandResult: ...
# It appends Record.Created then extra_events in one append; key None allocates a number.
```

## Context (read these, nothing else)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/transmittals.py` (the file you edit)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/revisions.py` (a finished file of the same shape; read it for style)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/common.py`
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `docs/tickets/P1-I2/provided/t08a-test_transmittal_commands.py.txt` (the test)
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
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run the scoped command in *Acceptance*, never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.

## Allowed paths
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/transmittals.py` (edit)
- `packages/tl-modules/documents/tests/test_transmittal_commands.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T08a.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t08a-test_transmittal_commands.py.txt` to `packages/tl-modules/documents/tests/test_transmittal_commands.py`.
3. Implement the five `handle_*` functions by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/documents/tests/test_transmittal_commands.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/documents/tests/test_transmittal_commands.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules/documents -q
```
Expected: `just check` clean; 17 passed on SQLite; 34 passed with both adapters (every test uses the `world` fixture); the whole `documents` package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of the parity run.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change in another file of `tl_mod_documents`, in `tl_core` or in a fixture.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
