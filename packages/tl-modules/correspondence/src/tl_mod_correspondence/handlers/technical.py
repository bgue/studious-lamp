"""Raise, edit, submit and return a Technical item: an RFI, a technical query, a deviation request.

A Technical item (brief 9, M10) is a question to the designer or the client, or a request to
deviate from the design. It is a record of the type ``correspondence.TechnicalItem`` with its own
workflow (``correspondence.technical``): the raiser writes a Draft, submits it to internal review,
and a document controller issues it (``technical_flow.py``). These four commands are the raiser's
side; any signed-in person may run them. Each handler runs inside an entered unit of work,
appends through it and never commits; a failed check raises a ``ServiceError`` before anything is
appended.

* ``RaiseTechnical``: a Draft numbered by kind (``P123-RFI-0001``), with the question, what is
  proposed, the discipline, the date an answer is needed, the raiser's own cost and schedule
  flags, the recipients, and the records it refers to (a document pinned at a revision, say).
* ``UpdateTechnical``: changes those fields while the item is a Draft or in internal review.
* ``SubmitTechnical``: Draft to Internal review; it needs a recipient and a date for the answer.
* ``ReturnTechnical``: Internal review back to Draft, with a reason.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog
from tl_mod_correspondence.actions import states_for
from tl_mod_correspondence.errors import InvalidItemError
from tl_mod_correspondence.handlers.common import (
    append,
    changes_of,
    correlated,
    plausible_date,
    require_project,
    require_state,
    today,
    transition,
)
from tl_mod_correspondence.handlers.create import check_body, check_recipients, create_item
from tl_mod_correspondence.handlers.domain import (
    ReferenceList,
    check_flag,
    check_references,
    kind_numbering,
    link_references,
    open_technical,
)
from tl_mod_correspondence.handlers.models import Recipient, non_blank
from tl_mod_correspondence.limits import (
    MAX_BODY,
    MAX_NUMBER,
    MAX_REASON,
    MAX_RECIPIENTS,
    MAX_TEXT,
)
from tl_mod_correspondence.names import (
    CORR_UPDATED,
    DOMAIN_TECHNICAL,
    ST_DRAFT,
    ST_INTERNAL_REVIEW,
    TECH_DEFINED,
    TECH_UPDATED,
    TECHNICAL,
)
from tl_mod_correspondence.textcheck import clean_body, clean_optional_text, clean_text


class RaiseTechnical(Command):
    """Raise an RFI, a technical query or a deviation request as a Draft.

    ``subtype`` is ``rfi``, ``tq`` or ``deviation``. ``required_by`` is the date an answer is
    needed (today or later). ``potential_cost_impact`` and ``potential_schedule_impact`` are the
    raiser's own flags (``yes``, ``no`` or ``unknown``) before there is an answer. ``references``
    are records the item refers to; a ``pin`` pins the link to a document at a revision label.
    The question is also the text of the item in the register.
    """

    model_config = ConfigDict(extra="forbid")

    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    question: str = Field(min_length=1, max_length=MAX_BODY)
    proposed_solution: str | None = Field(default=None, max_length=MAX_BODY)
    discipline: str | None = Field(default=None, max_length=32)
    required_by: str | None = Field(default=None, max_length=10)
    potential_cost_impact: str = Field(default="unknown", max_length=7)
    potential_schedule_impact: str = Field(default="unknown", max_length=7)
    to: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    references: ReferenceList = Field(default_factory=list)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return clean_text(non_blank(value))

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return clean_body(value)

    @field_validator("proposed_solution")
    @classmethod
    def _solution(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("discipline")
    @classmethod
    def _discipline(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("potential_cost_impact")
    @classmethod
    def _cost_flag(cls, value: str) -> str:
        return check_flag(value, "potential_cost_impact")

    @field_validator("potential_schedule_impact")
    @classmethod
    def _schedule_flag(cls, value: str) -> str:
        return check_flag(value, "potential_schedule_impact")


class UpdateTechnical(Command):
    """Change a Technical item that is a Draft or in internal review.

    A field you leave out stays as it is; ``null`` clears ``proposed_solution``, ``discipline``
    and ``required_by`` (the question, the subject and the flags cannot be cleared). The number
    and the subtype never change. Say why in ``reason`` when you change an item that is in review:
    it is recorded with the change (it is not required).
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    question: str | None = Field(default=None, min_length=1, max_length=MAX_BODY)
    proposed_solution: str | None = Field(default=None, max_length=MAX_BODY)
    discipline: str | None = Field(default=None, max_length=32)
    required_by: str | None = Field(default=None, max_length=10)
    potential_cost_impact: str | None = Field(default=None, max_length=7)
    potential_schedule_impact: str | None = Field(default=None, max_length=7)
    to: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(non_blank(value))

    @field_validator("question")
    @classmethod
    def _question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("must not be blank")
        return clean_body(value)

    @field_validator("proposed_solution")
    @classmethod
    def _solution(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("discipline", "reason")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("potential_cost_impact", "potential_schedule_impact")
    @classmethod
    def _flag(cls, value: str | None) -> str | None:
        return None if value is None else check_flag(value, "the flag")


class SubmitTechnical(Command):
    """Send a Draft to internal review. It needs a recipient and a date for the answer."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None


class ReturnTechnical(Command):
    """Send an item in internal review back to its raiser. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


def _required_by(value: str | None) -> str | None:
    """``value`` as a plausible date that is not before today; ``InvalidItemError`` otherwise."""
    try:
        found = plausible_date(value, "required_by")
    except ValueError as exc:
        raise InvalidItemError(str(exc)) from exc
    if found is not None and found < today():
        raise InvalidItemError(f"required_by {found} is before today ({today()})")
    return found


def handle_raise_technical(uow: UnitOfWork, cmd: RaiseTechnical) -> CommandResult:
    """Append ``Record.Created``, ``Correspondence.Defined`` and ``Technical.Defined``; link the
    references.

    The item is a Draft, outgoing, ``internal`` (the domain's default class), numbered by kind
    and answer-required. Raises ``CorrespondenceScopeError`` (not a project scope),
    ``UnknownDomainError`` (no such subtype), ``InvalidItemError`` (a date before today, a party,
    a text, a repeated reference), ``RecordNotFoundError`` (a reference that is unknown, foreign
    or hidden) and the numbering errors of the core.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    definition = catalog.check_subtype(cmd.scope, DOMAIN_TECHNICAL, cmd.subtype)
    chosen = definition.subtype(cmd.subtype)
    assert chosen is not None
    required_by = _required_by(cmd.required_by)
    check_references(uow, cmd, cmd.references, None)
    made = create_item(
        uow,
        cmd,
        subject=cmd.subject,
        direction="out",
        medium="other",
        received_via="manual",
        to=cmd.to,
        cc=cmd.cc,
        body=cmd.question,
        confidentiality=definition.confidentiality_default,
        response_required=chosen.response_required,
        response_due=required_by,
        domain=DOMAIN_TECHNICAL,
        subtype=cmd.subtype,
        record_type=TECHNICAL,
        numbering=kind_numbering(definition, cmd.subtype),
        domain_events=[
            NewEvent(
                event_type=TECH_DEFINED,
                payload={
                    "question": cmd.question,
                    "proposed_solution": cmd.proposed_solution,
                    "discipline": cmd.discipline,
                    "required_by": required_by,
                    "potential_cost_impact": cmd.potential_cost_impact,
                    "potential_schedule_impact": cmd.potential_schedule_impact,
                },
            )
        ],
    )
    linked = link_references(uow, cmd, made.stream_id, cmd.references)
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=made.version,
        events=[*made.events, *linked],
    )


def handle_update_technical(uow: UnitOfWork, cmd: UpdateTechnical) -> CommandResult:
    """Append ``Record.Updated`` (the subject), ``Correspondence.Updated`` (recipients, the text
    and the answer date as the register shows them) and ``Technical.Updated`` (the domain fields).

    Raises ``RecordNotFoundError`` (unknown, foreign, hidden, or not a Technical item),
    ``ItemStateError`` (not a Draft or in internal review), ``InvalidItemError`` (a date before
    today, a party, a text) and ``NoChangesError`` (nothing differs).
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    item, data = row.item, row.data
    require_state(item, ST_DRAFT, ST_INTERNAL_REVIEW)
    given = cmd.model_fields_set
    old: dict[str, Any] = {
        "question": data.question,
        "proposed_solution": data.proposed_solution,
        "discipline": data.discipline,
        "required_by": data.required_by,
        "potential_cost_impact": data.potential_cost_impact,
        "potential_schedule_impact": data.potential_schedule_impact,
    }
    new: dict[str, Any] = {}
    for name in old:
        if name not in given:
            continue
        value = getattr(cmd, name)
        if value is None and name in (
            "question",
            "potential_cost_impact",
            "potential_schedule_impact",
        ):
            raise InvalidItemError(f"{name} cannot be cleared")
        new[name] = value
    if "required_by" in new:
        new["required_by"] = _required_by(new["required_by"])
    register_old: dict[str, Any] = {"to": item.to, "cc": item.cc}
    register_new: dict[str, Any] = {}
    for name in ("to", "cc"):
        if name not in given:
            continue
        recipients = getattr(cmd, name)
        if recipients is None:
            raise InvalidItemError(f"{name} is a list; send [] to clear it")
        check_recipients(uow, cmd, recipients)
        register_new[name] = [r.as_payload() for r in recipients]
    if "question" in new:
        register_old["body"], register_new["body"] = item.body, check_body(new["question"])
    if "required_by" in new:
        register_old["response_due"], register_new["response_due"] = (
            item.response_due,
            new["required_by"],
        )
    domain = changes_of(old, new)
    register = changes_of(register_old, register_new)
    envelope = changes_of({"title": item.subject}, {"title": cmd.subject} if cmd.subject else {})
    if not (domain or register or envelope):
        raise NoChangesError(f"no field of item {item.number} differs from the request")
    events: list[NewEvent] = []
    if envelope:
        events.append(NewEvent(event_type="Record.Updated", payload={"changes": envelope}))
    if register:
        events.append(
            NewEvent(
                event_type=CORR_UPDATED,
                payload={"changes": register, "reason": cmd.reason},
            )
        )
    if domain:
        events.append(
            NewEvent(
                event_type=TECH_UPDATED,
                payload={"changes": domain, "reason": cmd.reason},
            )
        )
    done = append(
        uow,
        cmd,
        item.id,
        item.record_type,
        events,
        expected=cmd.expected_version or item.version,
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=done.new_version,
        events=list(done.events),
    )


def handle_submit_technical(uow: UnitOfWork, cmd: SubmitTechnical) -> CommandResult:
    """Move a Draft to Internal review.

    Raises ``RecordNotFoundError``, ``ItemStateError`` (not a Draft) and ``InvalidItemError`` (no
    recipient, or no date for the answer, or that date has passed).
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    item, data = row.item, row.data
    require_state(item, *states_for("SubmitTechnical", TECHNICAL))
    missing: list[str] = []
    if not item.to:
        missing.append("a recipient")
    if data.required_by is None:
        missing.append("required_by")
    if missing:
        raise InvalidItemError(f"item {item.number} needs {' and '.join(missing)} before review")
    if data.required_by is not None and data.required_by < today():
        raise InvalidItemError(f"required_by {data.required_by} is before today ({today()})")
    return transition(uow, cmd, item.id, "submit", expected=cmd.expected_version)


def handle_return_technical(uow: UnitOfWork, cmd: ReturnTechnical) -> CommandResult:
    """Move an item in internal review back to Draft, with the reason.

    Raises ``RecordNotFoundError`` and ``ItemStateError`` (not in internal review).
    """
    cmd = correlated(cmd)
    row = open_technical(uow, cmd, cmd.stream_id)
    require_state(row.item, *states_for("ReturnTechnical", TECHNICAL))
    return transition(
        uow,
        cmd,
        row.item.id,
        "return",
        reason=cmd.reason,
        expected=cmd.expected_version,
    )
