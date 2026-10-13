"""Review cycle commands: open, record an outcome, close (brief 9 M1; P1-I2).

A review cycle (``documents.ReviewCycle``) asks named reviewers to review one revision by a date
and collects an outcome from each. Reviewers are people with an account, and at least one of them is
not the revision's author. A reviewer records their own answer; a controller can record one on their
behalf (with a comment), and only a controller can close a cycle with an outcome milder than the
worst answer given (P1-I2 security review, ADR-0011, ADR-0013).

While a cycle is open the revision is In Review: its native and PDF renditions are frozen
(reviewers add markups), and it cannot be issued. Closing the cycle returns the revision to Draft,
with the overall outcome on the cycle; the author revises (a new cycle, round 2) or issues.

The document follows the first review: a Registered document with no issued revision is In Review
while a cycle is open and Registered again when the last one closes. Once a revision is issued the
document stays Issued whatever later cycles do.

Each handler runs inside an entered unit of work, appends through it and never commits. All
events of one command share one correlation id.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from tl_core.auth.queries import find_account
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_documents import registry
from tl_mod_documents.errors import (
    InvalidReviewError,
    NotYourReviewError,
    ReviewNotFoundError,
    ReviewStateError,
    RevisionStateError,
)
from tl_mod_documents.handlers.common import (
    append,
    correlated,
    load_revision,
    open_document,
    plausible_date,
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
#: What a cycle closes with: an answer's outcome, or ``withdrawn`` when nobody answered.
CloseOutcome = Literal["approved", "approved_with_comments", "rejected", "withdrawn"]
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
        return plausible_date(value, "due_date")


class OpenReviewCycle(Command):
    """Open a review round on a draft revision. The revision moves to In Review."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    reviewers: list[ReviewerRequest] = Field(min_length=1, max_length=MAX_REVIEWERS)
    due_date: str | None = None

    @field_validator("due_date")
    @classmethod
    def _due(cls, value: str | None) -> str | None:
        return plausible_date(value, "due_date")


class RecordReviewOutcome(Command):
    """A reviewer's own answer: approved, approved with comments, or rejected. Given once.

    ``reviewer`` may be left out (it is the caller); if given it must be the caller. To record an
    answer for someone else a controller uses ``RecordReviewOutcomeOnBehalf``.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    reviewer: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    outcome: Outcome
    comment: str | None = Field(default=None, max_length=MAX_DESCRIPTION)


class RecordReviewOutcomeOnBehalf(Command):
    """Controller: record a reviewer's answer for them (say, by mail). A comment says how.

    The event keeps who recorded it (``recorded_by``) next to the reviewer it is for.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    reviewer: str = Field(min_length=1, max_length=MAX_TEXT)
    outcome: Outcome
    comment: str = Field(min_length=1, max_length=MAX_DESCRIPTION)

    @field_validator("comment")
    @classmethod
    def _comment(cls, value: str) -> str:
        return _non_blank(value)


class CloseReviewCycle(Command):
    """Close a cycle. The outcome is the worst answer unless the command states a stricter one.

    Only the person who opened the cycle or the revision's author may close it (a controller closes
    any cycle with ``OverrideReviewOutcome``). A person cannot close with an outcome milder than
    the worst answer. If a reviewer has not answered, ``reason`` is required (why the cycle closes
    early). If nobody has answered, the round is ``withdrawn``: that is the only outcome, and the
    default.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    outcome: CloseOutcome | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class OverrideReviewOutcome(Command):
    """Controller: close a cycle with a stated outcome, even a milder one than the answers given.

    ``reason`` is required; the event keeps the worst recorded answer (``worst_answer``) so the
    record shows what was overruled.
    """

    model_config = ConfigDict(extra="forbid")

    review_cycle_id: str
    expected_version: int | None = None
    outcome: Outcome
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _non_blank(value)


def _load_cycle(uow: UnitOfWork, cmd: Command, cycle_id: str) -> registry.ReviewCycleRow:
    found = registry.get_review_cycle(uow.conn(), cycle_id)
    if found is None or found.scope != cmd.scope:
        raise ReviewNotFoundError(f"no review cycle {cycle_id!r} in scope {cmd.scope!r}")
    return found


def _person(uow: UnitOfWork, raw: str) -> str:
    """``user:<username>`` of the active person ``raw`` names, else ``InvalidReviewError``."""
    name = raw.strip()
    found = find_account(uow.conn(), username=name[5:]) if name.startswith("user:") else None
    if found is None or found.kind != "person" or found.status != "active":
        raise InvalidReviewError(
            f"{name!r} is not an active person account; write a reviewer as user:<username>"
        )
    return f"user:{found.username}"


def _author_of(uow: UnitOfWork, revision_id: str) -> str | None:
    """Who created the revision: the actor of its first event."""
    history = uow.ledger.read_stream(revision_id)
    return history[0].actor if history else None


def handle_open_review_cycle(uow: UnitOfWork, cmd: OpenReviewCycle) -> CommandResult:
    """Append ``Record.Created`` and ``ReviewCycle.Defined``; the revision (and document) move.

    Raises ``ProjectScopeError``, ``RevisionNotFoundError``, ``DocumentClosedError``,
    ``RevisionStateError`` (not a draft), ``InvalidReviewError`` (a reviewer listed twice, not an
    active person account, or only the revision's author).
    """
    require_project(cmd)
    cmd = correlated(cmd)
    rev = load_revision(uow, cmd, cmd.revision_id)
    doc = open_document(uow, cmd, rev.document_id)
    if rev.voided or rev.state != "Draft":
        raise RevisionStateError(
            f"revision {rev.code} of {doc.number} is {rev.state}; "
            "only a draft can be sent for review"
        )
    names = [_person(uow, r.reviewer) for r in cmd.reviewers]
    if len(set(names)) != len(names):
        raise InvalidReviewError("a reviewer can be listed only once")
    author = _author_of(uow, rev.id)
    if all(name == author for name in names):
        raise InvalidReviewError(
            f"{author} wrote revision {rev.code}; a review needs at least one other reviewer"
        )
    round_number = len(registry.review_cycles_of(uow.conn(), rev.id)) + 1
    made = create_module_record(
        uow,
        cmd,
        record_type=REVIEW_CYCLE,
        title=f"Review of {rev.key}, round {round_number}",
        key=f"{rev.key}/RC{round_number}",
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=REVIEW_DEFINED,
                payload={
                    "revision_id": rev.id,
                    "document_id": doc.id,
                    "round": round_number,
                    "due_date": cmd.due_date,
                    "opened_on": today(),
                    "reviewers": [
                        {"reviewer": name, "due_date": r.due_date}
                        for name, r in zip(names, cmd.reviewers, strict=True)
                    ],
                },
            )
        ],
    )
    events: list[Event] = list(made.events)
    events += transition(uow, cmd, rev.id, "start_review").events
    if doc.state == DOC_REGISTERED:
        events += transition(uow, cmd, doc.id, "start_review").events
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=made.version, events=events
    )


def _record(
    uow: UnitOfWork,
    cmd: Command,
    cycle_id: str,
    reviewer_raw: str,
    outcome: str,
    comment: str | None,
    expected: int | None,
    *,
    recorded_by: str | None,
) -> CommandResult:
    cycle = _load_cycle(uow, cmd, cycle_id)
    if cycle.state != "open":
        raise ReviewStateError(f"review cycle {cycle.key} is closed")
    reviewer = reviewer_raw.strip()
    mine = [r for r in registry.reviewers_of(uow.conn(), cycle.id) if r.reviewer == reviewer]
    if not mine:
        raise InvalidReviewError(f"{reviewer!r} is not a reviewer of {cycle.key}")
    if mine[0].outcome is not None:
        raise ReviewStateError(f"{reviewer} has already answered {cycle.key}")
    done = append(
        uow,
        cmd,
        cycle.id,
        REVIEW_CYCLE,
        [
            NewEvent(
                event_type=REVIEW_OUTCOME,
                payload={
                    "reviewer": reviewer,
                    "outcome": outcome,
                    "comment": comment,
                    "responded_on": today(),
                    "recorded_by": recorded_by,
                },
            )
        ],
        expected=expected,
    )
    return CommandResult(
        stream_id=cycle.id, key=cycle.key, version=done.new_version, events=list(done.events)
    )


def handle_record_review_outcome(uow: UnitOfWork, cmd: RecordReviewOutcome) -> CommandResult:
    """Append ``ReviewCycle.OutcomeRecorded`` for the caller, who must be a reviewer of the cycle.

    Raises ``NotYourReviewError`` (``reviewer`` names someone else), ``ReviewNotFoundError``,
    ``ReviewStateError`` (the cycle is closed, or this reviewer already answered) and
    ``InvalidReviewError`` (the caller is not a reviewer of the cycle).
    """
    cmd = correlated(cmd)
    reviewer = (cmd.reviewer or cmd.actor).strip()
    if reviewer != cmd.actor:
        raise NotYourReviewError(
            f"{cmd.actor} cannot answer for {reviewer}; a document controller can record it "
            "on their behalf"
        )
    return _record(
        uow,
        cmd,
        cmd.review_cycle_id,
        reviewer,
        cmd.outcome,
        cmd.comment,
        cmd.expected_version,
        recorded_by=None,
    )


def handle_record_review_outcome_on_behalf(
    uow: UnitOfWork, cmd: RecordReviewOutcomeOnBehalf
) -> CommandResult:
    """Append ``ReviewCycle.OutcomeRecorded`` for another reviewer; the event names the controller.

    Raises what ``handle_record_review_outcome`` raises, bar ``NotYourReviewError``.
    """
    cmd = correlated(cmd)
    return _record(
        uow,
        cmd,
        cmd.review_cycle_id,
        cmd.reviewer,
        cmd.outcome,
        cmd.comment,
        cmd.expected_version,
        recorded_by=cmd.actor,
    )


def _close(
    uow: UnitOfWork,
    cmd: Command,
    cycle: registry.ReviewCycleRow,
    outcome: str,
    reason: str | None,
    worst: str | None,
    expected: int | None,
) -> CommandResult:
    done = append(
        uow,
        cmd,
        cycle.id,
        REVIEW_CYCLE,
        [
            NewEvent(
                event_type=REVIEW_CLOSED,
                payload={
                    "outcome": outcome,
                    "closed_on": today(),
                    "reason": reason,
                    "worst_answer": worst,
                },
            )
        ],
        expected=expected,
    )
    events: list[Event] = list(done.events)
    rev = registry.get_revision(uow.conn(), cycle.revision_id)
    if rev is not None and rev.state == "In Review":
        events += transition(uow, cmd, rev.id, "return_to_draft").events
    doc = registry.get_document(uow.conn(), cycle.document_id)
    if doc is not None and doc.state == DOC_IN_REVIEW and doc.current_revision_id is None:
        events += transition(uow, cmd, doc.id, "end_review").events
    return CommandResult(stream_id=cycle.id, key=cycle.key, version=done.new_version, events=events)


def _open_cycle(uow: UnitOfWork, cmd: Command, cycle_id: str) -> registry.ReviewCycleRow:
    cycle = _load_cycle(uow, cmd, cycle_id)
    if cycle.state != "open":
        raise ReviewStateError(f"review cycle {cycle.key} is already closed")
    return cycle


def handle_close_review_cycle(uow: UnitOfWork, cmd: CloseReviewCycle) -> CommandResult:
    """Append ``ReviewCycle.Closed``; the revision returns to Draft; the document may leave review.

    Raises ``ReviewNotFoundError``, ``ReviewStateError`` (already closed), ``NotYourReviewError``
    (the caller neither opened the cycle nor wrote the revision) and ``InvalidReviewError`` (a
    reviewer is missing and no reason is given; the outcome is milder than the worst answer;
    ``withdrawn`` with answers, or any other outcome with none).
    """
    cmd = correlated(cmd)
    cycle = _open_cycle(uow, cmd, cmd.review_cycle_id)
    opener = uow.ledger.read_stream(cycle.id)[0].actor
    if cmd.actor not in (opener, _author_of(uow, cycle.revision_id)):
        raise NotYourReviewError(
            f"{cmd.actor} neither opened {cycle.key} nor wrote the revision; "
            "a document controller closes it with OverrideReviewOutcome"
        )
    reviewers = registry.reviewers_of(uow.conn(), cycle.id)
    answered = [r.outcome for r in reviewers if r.outcome is not None]
    if any(r.outcome is None for r in reviewers) and not (cmd.reason or "").strip():
        missing = ", ".join(r.reviewer for r in reviewers if r.outcome is None)
        raise InvalidReviewError(
            f"{missing} have not answered; give a reason to close {cycle.key} early"
        )
    if answered:
        worst = max(answered, key=lambda o: _SEVERITY[o])
        outcome = cmd.outcome or worst
        if outcome == "withdrawn":
            raise InvalidReviewError(f"{cycle.key} has answers; it cannot be withdrawn")
        if _SEVERITY[outcome] < _SEVERITY[worst]:
            raise InvalidReviewError(
                f"{cycle.key} has a {worst} answer; only a document controller can close it as "
                f"{outcome} (OverrideReviewOutcome)"
            )
    else:
        outcome = cmd.outcome or "withdrawn"
        if outcome != "withdrawn":
            raise InvalidReviewError(
                f"nobody has answered {cycle.key}; it is closed as withdrawn, "
                "or by a document controller with OverrideReviewOutcome"
            )
    return _close(uow, cmd, cycle, outcome, cmd.reason, None, cmd.expected_version)


def handle_override_review_outcome(uow: UnitOfWork, cmd: OverrideReviewOutcome) -> CommandResult:
    """Append ``ReviewCycle.Closed`` with the outcome the controller states and why.

    Raises ``ReviewNotFoundError`` and ``ReviewStateError`` (already closed).
    """
    cmd = correlated(cmd)
    cycle = _open_cycle(uow, cmd, cmd.review_cycle_id)
    answered = [
        r.outcome for r in registry.reviewers_of(uow.conn(), cycle.id) if r.outcome is not None
    ]
    worst = max(answered, key=lambda o: _SEVERITY[o]) if answered else None
    milder = worst if worst is not None and _SEVERITY[cmd.outcome] < _SEVERITY[worst] else None
    return _close(uow, cmd, cycle, cmd.outcome, cmd.reason, milder, cmd.expected_version)
