# P1-I2-T08b — Review cycle commands: open, record an outcome, close

Status: ready
Tier: haiku
Labels: core
Depends on: S3 and S4 on `p1/i2`; no other ticket
Branch: `p1/i2-t08b-review-commands`

## Goal
A document controller can open a review of a draft revision with named reviewers, collect each reviewer's outcome, and close the cycle. `packages/tl-modules/documents/src/tl_mod_documents/handlers/reviews.py` has the command classes, `_SEVERITY`, `_load_cycle` and the three handler signatures final; the three bodies raise `NotImplementedError`. You implement the bodies. One provided test file (15 test functions) must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Brief 9 M1.** `ReviewCycle`: reviewers, due dates, outcome codes. Cross-references: revision, comments. `Revision`: status, reviewer comments; parent document, previous revision.
>
> **Brief 9 M1 workflows.** Document: Draft -> Registered -> In Review -> Issued -> Superseded/Void.

### Specification
- A review cycle is the module record `documents.ReviewCycle` (envelope row plus a row in `cur_documents_review_cycle` and one row per reviewer in `cur_documents_reviewer`). `ReviewCycleProjector` writes them from `ReviewCycle.Defined`, `ReviewCycle.OutcomeRecorded` and `ReviewCycle.Closed`. Your handlers only append events.
- A cycle has no workflow of its own; its `state` column is `open` or `closed`.
- While a cycle is open the **revision** is In Review: opening runs the revision workflow transition `start_review` (Draft -> In Review); closing runs `return_to_draft` (In Review -> Draft). Only a Draft revision can be sent for review.
- The **document** follows the first review: if it is `Registered` when the cycle opens it moves to `In Review` (`start_review`); when the cycle closes and the document is `In Review` and has no current revision yet (`current_revision_id is None`) it moves back to `Registered` (`end_review`). An Issued document stays Issued. The generic `TransitionWorkflow` is closed to these record types: the module moves them with `transition(...)` from `handlers/common.py`.
- The overall outcome of a cycle is the worst answer: rejected beats approved_with_comments beats approved (`_SEVERITY`). `outcome` on `CloseReviewCycle` overrides it. Closing before everyone answered needs a `reason`; closing with no answer at all needs an explicit `outcome` too.
- Every refusal is a `ServiceError` raised before anything is appended. All events of one command share one correlation id. `expected_version` goes to the first append of the handler (`append(..., expected=...)`).

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/documents/src/tl_mod_documents/handlers/reviews.py` (the stub you complete):
```python
"""Review cycle commands: open, record an outcome, close (brief 9 M1; P1-I2).

A review cycle (``documents.ReviewCycle``) asks named reviewers to review one revision by a date
and collects an outcome from each. While a cycle is open the revision is In Review: its native and
PDF renditions are frozen (reviewers add markups), and it cannot be issued. Closing the cycle
returns the revision to Draft, with the overall outcome on the cycle; the author revises (a new
cycle, round 2) or issues.

The document follows the first review: a Registered document with no issued revision is In Review
while a cycle is open and Registered again when the last one closes. Once a revision is issued the
document stays Issued whatever later cycles do.

Each handler runs inside an entered unit of work, appends through it and never commits. All
events of one command share one correlation id.

STUB (P1-I2-T08b): the bodies of the three `handle_*` functions raise NotImplementedError; the
command classes, `_SEVERITY`, `_load_cycle` and every signature are final. Each body has a STEPS
comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
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
    InvalidReviewError,
    ReviewNotFoundError,
    ReviewStateError,
    RevisionStateError,
)
from tl_mod_documents.handlers.common import (
    append,
    check_date,
    correlated,
    load_revision,
    open_document,
    require_project,
    today,
    transition,
)
from tl_mod_documents.limits import (
    MAX_DESCRIPTION,
    MAX_REASON,
    MAX_REVIEWERS,
    MAX_TEXT,
)
from tl_mod_documents.names import (
    DOC_IN_REVIEW,
    DOC_REGISTERED,
    REVIEW_CLOSED,
    REVIEW_CYCLE,
    REVIEW_DEFINED,
    REVIEW_OUTCOME,
)

Outcome = Literal["approved", "approved_with_comments", "rejected"]
#: Worst outcome wins: one rejection rejects, otherwise one comment makes it "with comments".
_SEVERITY: dict[str, int] = {"approved": 0, "approved_with_comments": 1, "rejected": 2}


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class ReviewerRequest(BaseModel):
    """A reviewer and, when it differs from the cycle's, the date by which they should answer."""

    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=MAX_TEXT)
    due_date: str | None = None

    @field_validator("reviewer")
    @classmethod
    def _reviewer(cls, value: str) -> str:
        return _non_blank(value)

    @field_validator("due_date")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return check_date(value, "due_date")


class OpenReviewCycle(Command):
    """Open a review round on a draft revision. The revision moves to In Review."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    reviewers: list[ReviewerRequest] = Field(min_length=1, max_length=MAX_REVIEWERS)
    due_date: str | None = None

    @field_validator("due_date")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return check_date(value, "due_date")


class RecordReviewOutcome(Command):
    """A reviewer's answer: approved, approved with comments, or rejected. Given once."""

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    reviewer: str = Field(min_length=1, max_length=MAX_TEXT)
    outcome: Outcome
    comment: str | None = Field(default=None, max_length=MAX_DESCRIPTION)


class CloseReviewCycle(Command):
    """Close a cycle. The overall outcome is the worst answer unless the command states one.

    If a reviewer has not answered, ``reason`` is required (why the cycle closes early); if nobody
    has, ``outcome`` is required too.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    outcome: Outcome | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)


def _load_cycle(uow: UnitOfWork, cmd: Command, cycle_id: str) -> registry.ReviewCycleRow:
    found = registry.get_review_cycle(uow.conn(), cycle_id)
    if found is None or found.scope != cmd.scope:
        raise ReviewNotFoundError(f"no review cycle {cycle_id!r} in scope {cmd.scope!r}")
    return found


def handle_open_review_cycle(uow: UnitOfWork, cmd: OpenReviewCycle) -> CommandResult:
    """Append ``Record.Created`` and ``ReviewCycle.Defined``; the revision (and document) move.

    Raises ``ProjectScopeError``, ``RevisionNotFoundError``, ``DocumentClosedError``,
    ``RevisionStateError`` (not a draft), ``InvalidReviewError`` (a reviewer listed twice).
    """
    # STEPS
    # 1. require_project(cmd); cmd = correlated(cmd); rev = load_revision(uow, cmd,
    #    cmd.revision_id); doc = open_document(uow, cmd, rev.document_id).
    # 2. If rev.voided or rev.state != "Draft" raise RevisionStateError(f"revision {rev.code} of
    #    {doc.number} is {rev.state}; only a draft can be sent for review").
    # 3. names = [r.reviewer.strip() for r in cmd.reviewers]; if names has a repeat raise
    #    InvalidReviewError("a reviewer can be listed only once").
    # 4. round_number = len(registry.review_cycles_of(uow.conn(), rev.id)) + 1.
    # 5. made = create_module_record(uow, cmd, record_type=REVIEW_CYCLE, title=f"Review of
    #    {rev.key}, round {round_number}", key=f"{rev.key}/RC{round_number}",
    #    extra_events=[NewEvent(event_type=REVIEW_DEFINED, payload={...})]) where the payload
    #    has revision_id (rev.id), document_id (doc.id), round (round_number), due_date
    #    (cmd.due_date), opened_on (today()) and reviewers: one {"reviewer": name, "due_date":
    #    r.due_date} per request, in order (zip(names, cmd.reviewers, strict=True)).
    # 6. events = list(made.events); events += transition(uow, cmd, rev.id,
    #    "start_review").events; if doc.state == DOC_REGISTERED also events += transition(uow,
    #    cmd, doc.id, "start_review").events.
    # 7. Return CommandResult(stream_id=made.stream_id, key=made.key, version=made.version,
    #    events=events).
    raise NotImplementedError


def handle_record_review_outcome(uow: UnitOfWork, cmd: RecordReviewOutcome) -> CommandResult:
    """Append ``ReviewCycle.OutcomeRecorded`` for one reviewer.

    Raises ``ReviewNotFoundError``, ``ReviewStateError`` (the cycle is closed, or this reviewer
    already answered) and ``InvalidReviewError`` (not a reviewer of the cycle).
    """
    # STEPS
    # 1. cmd = correlated(cmd); cycle = _load_cycle(uow, cmd, cmd.review_cycle_id); if
    #    cycle.state != "open" raise ReviewStateError(f"review cycle {cycle.key} is closed").
    # 2. reviewer = cmd.reviewer.strip(); mine = [r for r in registry.reviewers_of(uow.conn(),
    #    cycle.id) if r.reviewer == reviewer]. No match: raise InvalidReviewError(f"{reviewer!r}
    #    is not a reviewer of {cycle.key}"). mine[0].outcome is not None: raise
    #    ReviewStateError(f"{reviewer} has already answered {cycle.key}").
    # 3. done = append(uow, cmd, cycle.id, REVIEW_CYCLE, [NewEvent(event_type=REVIEW_OUTCOME,
    #    payload={"reviewer": reviewer, "outcome": cmd.outcome, "comment": cmd.comment,
    #    "responded_on": today()})], expected=cmd.expected_version).
    # 4. Return CommandResult(stream_id=cycle.id, key=cycle.key, version=done.new_version,
    #    events=list(done.events)).
    raise NotImplementedError


def handle_close_review_cycle(uow: UnitOfWork, cmd: CloseReviewCycle) -> CommandResult:
    """Append ``ReviewCycle.Closed``; the revision returns to Draft; the document may leave review.

    Raises ``ReviewNotFoundError``, ``ReviewStateError`` (already closed) and
    ``InvalidReviewError`` (a reviewer is missing and no reason is given; nobody answered and no
    outcome is given).
    """
    # STEPS
    # 1. cmd = correlated(cmd); cycle = _load_cycle(...); if cycle.state != "open" raise
    #    ReviewStateError(f"review cycle {cycle.key} is already closed").
    # 2. reviewers = registry.reviewers_of(uow.conn(), cycle.id); answered = [r.outcome for r in
    #    reviewers if r.outcome is not None].
    # 3. If some reviewer has not answered and cmd.reason is empty or blank: missing = ",
    #    ".join(the reviewers with no outcome); raise InvalidReviewError(f"{missing} have not
    #    answered; give a reason to close {cycle.key} early").
    # 4. outcome = cmd.outcome when given; else the worst answer: max(answered, key=lambda o:
    #    _SEVERITY[o]); else (nobody answered) raise InvalidReviewError(f"nobody has answered
    #    {cycle.key}; give the outcome to close it").
    # 5. done = append(uow, cmd, cycle.id, REVIEW_CYCLE, [NewEvent(event_type=REVIEW_CLOSED,
    #    payload={"outcome": outcome, "closed_on": today(), "reason": cmd.reason})],
    #    expected=cmd.expected_version); events = list(done.events).
    # 6. rev = registry.get_revision(uow.conn(), cycle.revision_id); if rev is not None and
    #    rev.state == "In Review": events += transition(uow, cmd, rev.id,
    #    "return_to_draft").events.
    # 7. doc = registry.get_document(uow.conn(), cycle.document_id); if doc is not None and
    #    doc.state == DOC_IN_REVIEW and doc.current_revision_id is None: events +=
    #    transition(uow, cmd, doc.id, "end_review").events.
    # 8. Return CommandResult(stream_id=cycle.id, key=cycle.key, version=done.new_version,
    #    events=events).
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
class ReviewCycleRow:
    id: str
    scope: str
    key: str
    title: str
    voided: bool
    version: int
    revision_id: str
    document_id: str
    round: int
    state: str  # open | closed
    due_date: str | None
    outcome: str | None
    opened_on: str | None
    closed_on: str | None

@dataclass(frozen=True)
class ReviewerRow:
    review_cycle_id: str
    revision_id: str
    document_id: str
    reviewer: str
    due_date: str | None
    outcome: str | None
    comment: str | None
    responded_on: str | None

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

@dataclass(frozen=True)
class DocumentRow:
    id: str
    scope: str
    number: str
    title: str
    description: str | None
    state: str  # the document workflow state
    voided: bool
    version: int
    conformance: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None
    revision_scheme: str
    pattern_code: str | None
    current_revision_id: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None
    created_at: str
    updated_at: str

    @property
    def closed(self) -> bool:
        """True once the document is void or superseded: it takes no more changes."""
        return self.voided or self.state in ("Void", "Superseded")

def get_review_cycle(conn: Connection, cycle_id: str) -> ReviewCycleRow | None: ...

def review_cycles_of(conn: Connection, revision_id: str) -> list[ReviewCycleRow]: ...

def reviewers_of(conn: Connection, cycle_id: str) -> list[ReviewerRow]: ...

def get_revision(conn: Connection, revision_id: str) -> RevisionRow | None: ...

def get_document(conn: Connection, document_id: str) -> DocumentRow | None: ...
```

`packages/tl-core/src/tl_core/services/records.py` (the core call the stub uses; signature):
```python
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
# It appends Record.Created then extra_events in one append.
```

## Context (read these, nothing else)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/reviews.py` (the file you edit)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/revisions.py` (a finished file of the same shape; read it for style)
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/common.py`
- `packages/tl-modules/documents/src/tl_mod_documents/registry.py`
- `docs/tickets/P1-I2/provided/t08b-test_review_commands.py.txt` (the test)
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
- `packages/tl-modules/documents/src/tl_mod_documents/handlers/reviews.py` (edit)
- `packages/tl-modules/documents/tests/test_review_commands.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T08b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t08b-test_review_commands.py.txt` to `packages/tl-modules/documents/tests/test_review_commands.py`.
3. Implement the three `handle_*` functions by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/documents/tests/test_review_commands.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/documents/tests/test_review_commands.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules/documents -q
```
Expected: `just check` clean; 15 passed on SQLite; 30 passed with both adapters; the whole `documents` package passes.

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
