"""Issue a Technical item, record its answer, judge the answer, send it round again, close it.

The raiser's commands are in ``technical.py``; these are the rest of the life of an RFI, a
technical query or a deviation request (workflow ``correspondence.technical``):

* ``IssueTechnical`` (a document controller's act, like issuing a letter): renders the question to
  a PDF, stores it, "sends" it (a stub: nothing leaves the machine), starts the clock that ends on
  the date the answer is needed, and moves the item Internal review, Issued, Awaiting response.
* ``AnswerTechnical``: records the answer with the answerer's statement on cost and schedule. A
  ``yes`` on either is what the RFI to Commercial escalation rule listens for. The clocks that
  waited for the answer are met on the answer's day.
* ``ReviewTechnicalAnswer``: the raiser accepts the answer, or rejects it with a reason.
* ``ReissueTechnical``: a rejected item goes back to internal review for another round; the
  answer of the round before is cleared from the current state (the events keep it).
* ``CloseTechnical``: the item needs no more work; its open clocks are cancelled.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, constraints, files, registry, registry_domain
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, LetterRenderError
from tl_mod_correspondence.handlers.clocks import close_clocks_of_item
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    require_state,
    resolve_date,
    today,
    transition,
)
from tl_mod_correspondence.handlers.domain import (
    Reference,
    check_flag,
    check_references,
    feed_fields,
    link_if_new,
    open_technical,
    require_readers_may_read,
    start_domain_clocks,
)
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.letter import LetterError, LetterFields, compose_letter, render_pdf
from tl_mod_correspondence.limits import MAX_BODY, MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    CORR_ISSUED,
    CORR_RESPONDED,
    DOMAIN_TECHNICAL,
    ST_ACCEPTED,
    ST_ANSWERED,
    ST_AWAITING_RESPONSE,
    ST_INTERNAL_REVIEW,
    ST_REJECTED,
    TECH_ANSWERED,
    TECH_REISSUED,
    TECH_REVIEWED,
)
from tl_mod_correspondence.textcheck import clean_body, clean_optional_text, clean_text

ANSWER_CLOCKS = ("response_from_them", "response_from_us")
_ISSUES_SQL = text(
    "SELECT COUNT(*) FROM events WHERE stream_id = :id AND event_type = 'Correspondence.Issued'"
)
Decision = Literal["accepted", "rejected"]


class IssueTechnical(Command):
    """Issue a Technical item that has passed internal review (a document controller's act).

    The letter is rendered from the domain's template for the subtype (or ``template``). The send
    is a stub: nothing leaves the machine. ``issued_on`` is the date on the letter (today by
    default; an earlier day needs ``date_reason``; never later than today).
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    template: str | None = Field(default=None, max_length=MAX_NUMBER)
    issued_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("date_reason")
    @classmethod
    def _clean_date_reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class AnswerTechnical(Command):
    """Record the answer to an item that is awaiting one.

    ``cost_impact`` and ``schedule_impact`` are the answerer's statement (``yes``, ``no`` or
    ``unknown``). ``answer_item_id`` is the item of the register that carries the answer (the
    client's letter) and ``answering_revision_id`` the document revision that answers (a re-issued
    drawing); each is linked to the item. ``answered_on`` is today by default; an earlier day
    needs ``date_reason``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    answer: str = Field(min_length=1, max_length=MAX_BODY)
    cost_impact: str = Field(default="unknown", max_length=7)
    schedule_impact: str = Field(default="unknown", max_length=7)
    answer_item_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    answering_revision_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    answered_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("answer")
    @classmethod
    def _answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return clean_body(value)

    @field_validator("cost_impact")
    @classmethod
    def _cost(cls, value: str) -> str:
        return check_flag(value, "cost_impact")

    @field_validator("schedule_impact")
    @classmethod
    def _schedule(cls, value: str) -> str:
        return check_flag(value, "schedule_impact")

    @field_validator("date_reason")
    @classmethod
    def _clean_date_reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReviewTechnicalAnswer(Command):
    """Accept the answer, or reject it. A rejection needs a ``note`` that says why."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    decision: Decision
    note: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReissueTechnical(Command):
    """Send a rejected item back to internal review for another round. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


class CloseTechnical(Command):
    """Close an item that needs no more work. Its open clocks are cancelled.

    An item still waiting for its answer, and one whose answer was rejected, need a ``reason``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def _letter_text(question: str, proposed: str | None, required_by: str | None) -> str:
    body = f"Question:\n{question}"
    if proposed:
        body += f"\n\nProposed solution:\n{proposed}"
    if required_by:
        body += f"\n\nAn answer is needed by {required_by}."
    return body


def _tell_the_sink(uow: UnitOfWork, item_id: str, *, issued: bool) -> None:
    """Call the constraint hook (a stub in Phase 1) with the item as it is now."""
    now = registry_domain.get_technical(uow.conn(), item_id)
    if now is None:  # the viewer reads what it just changed; this is not reachable
        return
    sink = constraints.current()
    (sink.rfi_issued if issued else sink.rfi_answered)(uow, now.item, now.data)


def handle_issue_technical(uow: UnitOfWork, cmd: IssueTechnical) -> CommandResult:
    """Render and store the PDF, "send" it, start the issue clocks, append
    ``Correspondence.Issued`` and move the item to Awaiting response.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (not in internal review),
    ``InvalidItemError`` (no recipient), ``UnknownDomainError``, ``LetterRenderError`` (no such
    template, a letter the renderer refuses, no file service), ``InvalidClockError`` (the answer
    is needed by a day that is not after the issue day) and the date errors of ``resolve_date``.
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    item, data = row.item, row.data
    require_state(item, ST_INTERNAL_REVIEW)
    recipients = ", ".join(r.get("name") or r.get("email") or "" for r in item.to).strip(", ")
    if not recipients:
        raise InvalidItemError(f"item {item.number} has no recipient")
    definition = catalog.check_subtype(cmd.scope, DOMAIN_TECHNICAL, item.subtype or "")
    day, date_reason = resolve_date(cmd.issued_on, cmd.date_reason, "the issue day")
    wanted = cmd.template
    templates = [t for t in definition.templates if wanted is None or t.code == wanted]
    if wanted is None:
        templates = [t for t in templates if t.subtype == item.subtype]
    if not templates:
        raise LetterRenderError(
            f"domain {definition.code} has no letter template "
            + (repr(wanted) if wanted else f"for subtype {item.subtype}")
        )
    template = templates[0]
    try:
        lines = compose_letter(
            template.header,
            template.footer,
            LetterFields(
                number=item.number,
                date=day,
                subject=item.subject,
                to=recipients,
                body=_letter_text(data.question, data.proposed_solution, data.required_by),
            ),
        )
        pdf = render_pdf(lines, title=f"{item.number} {item.subject}")
    except LetterError as exc:
        raise LetterRenderError(str(exc)) from exc
    stored = files.write_rendition(
        uow,
        actor=cmd.actor,
        source=cmd.source,
        scope=cmd.scope,
        record_id=item.id,
        filename=f"{item.number}.pdf",
        data=pdf,
        correlation_id=cmd.correlation_id or "",
    )
    clock_ids, clock_events = start_domain_clocks(
        uow, cmd, item, definition, "issue", day, answer_by=data.required_by
    )
    done = append(
        uow,
        cmd,
        item.id,
        item.record_type,
        [
            NewEvent(
                event_type=CORR_ISSUED,
                payload={
                    "issued_on": day,
                    "date_reason": date_reason,
                    "rendition_file_id": stored.file_id,
                    "rendition_sha256": stored.sha256,
                    "template": template.code,
                    "delivery": "stub",
                    "clock_ids": clock_ids,
                    **feed_fields(
                        definition,
                        full=f"{item.number} issued: {item.subject}",
                        minimal="A technical request was issued",
                    ),
                },
            )
        ],
        expected=cmd.expected_version or item.version,
    )
    issued = transition(uow, cmd, item.id, "issue")
    waiting = transition(uow, cmd, item.id, "await_response")
    _tell_the_sink(uow, item.id, issued=True)
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=waiting.version,
        events=[*clock_events, *done.events, *issued.events, *waiting.events],
    )


def _check_revision(uow: UnitOfWork, cmd: Command, revision_id: str, own_id: str) -> None:
    """The revision is a readable ``documents.Revision`` of the scope."""
    check_references(uow, cmd, [Reference(record_id=revision_id)], own_id)
    kind = (
        uow.conn()
        .execute(text("SELECT type FROM cur_core_record WHERE id = :id"), {"id": revision_id})
        .scalar_one()
    )
    if kind != "documents.Revision":
        raise InvalidItemError(f"record {revision_id!r} is not a document revision")


def handle_answer_technical(uow: UnitOfWork, cmd: AnswerTechnical) -> CommandResult:
    """Append ``Technical.Answered`` and ``Correspondence.Responded``, link what answers, move the
    item to Answered and meet the clocks that waited for the answer.

    Raises ``RecordNotFoundError`` (the item, the answering item or the revision is unknown,
    foreign or hidden, or is of a class that some reader of the item may not read: the item's own
    events name it), ``ItemStateError`` (not awaiting a response), ``InvalidItemError`` (the
    answering item is the item itself, or the revision is not a document revision) and the date
    errors of ``resolve_date``.
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    item = row.item
    require_state(item, ST_AWAITING_RESPONSE)
    if cmd.answer_item_id is not None:
        answer = registry.get_item(uow.conn(), cmd.answer_item_id)
        if answer is None or answer.scope != cmd.scope:
            raise RecordNotFoundError(f"no record {cmd.answer_item_id!r}")
        if answer.id == item.id:
            raise InvalidItemError("an item cannot be its own answer")
        require_readers_may_read(uow, item, answer.id)
    if cmd.answering_revision_id is not None:
        _check_revision(uow, cmd, cmd.answering_revision_id, item.id)
        require_readers_may_read(uow, item, cmd.answering_revision_id)
    day, date_reason = resolve_date(cmd.answered_on, cmd.date_reason, "the answer day")
    definition = catalog.check_subtype(cmd.scope, DOMAIN_TECHNICAL, item.subtype or "")
    done = append(
        uow,
        cmd,
        item.id,
        item.record_type,
        [
            NewEvent(
                event_type=TECH_ANSWERED,
                payload={
                    "answer": cmd.answer,
                    "answered_on": day,
                    "date_reason": date_reason,
                    "cost_impact": cmd.cost_impact,
                    "schedule_impact": cmd.schedule_impact,
                    "answer_item_id": cmd.answer_item_id,
                    "answering_revision_id": cmd.answering_revision_id,
                    **feed_fields(
                        definition,
                        full=f"{item.number} answered: {item.subject}",
                        minimal="A technical request was answered",
                    ),
                },
            ),
            NewEvent(
                event_type=CORR_RESPONDED,
                payload={"response_id": cmd.answer_item_id, "responded_on": day},
            ),
        ],
        expected=cmd.expected_version or item.version,
    )
    linked = []
    for target, note in (
        (cmd.answer_item_id, "the answer"),
        (cmd.answering_revision_id, "the answering revision"),
    ):
        if target is not None:
            linked += link_if_new(uow, cmd, item.id, target, note)
    moved = transition(uow, cmd, item.id, "answer")
    met = close_clocks_of_item(
        uow,
        cmd,
        item.id,
        how="met",
        day=day,
        reason="answered",
        response_id=cmd.answer_item_id,
        kinds=ANSWER_CLOCKS,
    )
    _tell_the_sink(uow, item.id, issued=False)
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=moved.version,
        events=[*done.events, *linked, *moved.events, *met],
    )


def handle_review_technical_answer(uow: UnitOfWork, cmd: ReviewTechnicalAnswer) -> CommandResult:
    """Append ``Technical.Reviewed`` and move the item to Accepted or Rejected.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (no answer to judge) and
    ``InvalidItemError`` (a rejection without a note).
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    item = row.item
    require_state(item, ST_ANSWERED)
    if cmd.decision == "rejected" and not (cmd.note and cmd.note.strip()):
        raise InvalidItemError("say why the answer is rejected")
    append(
        uow,
        cmd,
        item.id,
        item.record_type,
        [
            NewEvent(
                event_type=TECH_REVIEWED,
                payload={"decision": cmd.decision, "note": cmd.note, "reviewed_on": today()},
            )
        ],
        expected=cmd.expected_version or item.version,
    )
    return transition(
        uow, cmd, item.id, "accept" if cmd.decision == "accepted" else "reject", reason=cmd.note
    )


def handle_reissue_technical(uow: UnitOfWork, cmd: ReissueTechnical) -> CommandResult:
    """Append ``Technical.Reissued`` (with the number of the round that starts) and move the item
    back to Internal review.

    Raises ``RecordNotFoundError`` and ``ItemStateError`` (the answer was not rejected).
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    item = row.item
    require_state(item, ST_REJECTED)
    rounds = int(uow.conn().execute(_ISSUES_SQL, {"id": item.id}).scalar_one()) + 1
    append(
        uow,
        cmd,
        item.id,
        item.record_type,
        [NewEvent(event_type=TECH_REISSUED, payload={"reason": cmd.reason, "round": rounds})],
        expected=cmd.expected_version or item.version,
    )
    return transition(uow, cmd, item.id, "reissue", reason=cmd.reason)


def handle_close_technical(uow: UnitOfWork, cmd: CloseTechnical) -> CommandResult:
    """Move the item to Closed and cancel its open clocks.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (the item is not awaiting a response,
    accepted or rejected; or it is waiting for an answer, or was rejected, and no ``reason`` was
    given).
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    item = row.item
    require_state(item, ST_AWAITING_RESPONSE, ST_ACCEPTED, ST_REJECTED)
    if item.state != ST_ACCEPTED and not (cmd.reason and cmd.reason.strip()):
        raise ItemStateError(f"item {item.number} is {item.state}; give the reason for closing it")
    moved = transition(uow, cmd, item.id, "close", reason=cmd.reason, expected=cmd.expected_version)
    cancelled = close_clocks_of_item(
        uow, cmd, item.id, how="cancelled", day=today(), reason=cmd.reason or "item closed"
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=moved.version,
        events=[*moved.events, *cancelled],
    )
