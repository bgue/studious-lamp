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
