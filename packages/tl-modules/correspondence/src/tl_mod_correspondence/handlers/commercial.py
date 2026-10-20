"""Raise, edit, submit and review a Commercial item: an early warning, a change notice, a claim ...

A Commercial item (brief 9, M10) is a notice or a claim under the contract. It is a record of the
type ``correspondence.CommercialItem`` with its own workflow (``correspondence.commercial``) and
the class ``restricted`` (commercial roles and the project manager; the nearest the platform has
is the document controller and admin, ADR-0016). So **every Commercial command is a document
controller's**: a person who cannot read a restricted item cannot make one, and a handler refuses
a viewer below that level before it writes anything.

* ``RaiseCommercial``: a Draft numbered by kind (``P123-EW-0001``) with the contract clause, the
  day the contractor became aware, the estimated value and hours, the effect by cost code, the
  schedule impact and the entitlement basis. The **time bar** of the subtype starts counting at
  once, from the awareness day, so the clock runs while the notice is written and reviewed. A
  site instruction (received) is logged and waits for our assessment instead.
* ``UpdateCommercial``: changes the money, the text and the recipients while the item is a Draft
  or in commercial review. The clause and the awareness day are fixed (the time bar was counted
  from them); correct them by voiding the item and raising it again.
* ``SubmitCommercial``: Draft to Commercial review. Some subtypes need data first (a claim needs
  its basis and its clause).
* ``ReviewCommercial``: Commercial review to PM approval. ``ReturnCommercial``: back to Draft.

``create_commercial`` is the one place an item is made; ``RaiseCommercial`` and the escalation of
an answered RFI (``escalate.py``) both call it.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_core import confidentiality
from tl_core.auth.errors import ForbiddenError
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.domains import DomainDefinition
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
    CostCodeImpact,
    ReferenceList,
    check_currency,
    check_hours,
    check_impacts,
    check_money,
    check_references,
    kind_numbering,
    link_references,
    open_commercial,
    start_domain_clocks,
)
from tl_mod_correspondence.handlers.models import Recipient, non_blank
from tl_mod_correspondence.limits import (
    MAX_BODY,
    MAX_IMPACTS,
    MAX_NUMBER,
    MAX_REASON,
    MAX_RECIPIENTS,
    MAX_TEXT,
)
from tl_mod_correspondence.names import (
    COMM_DEFINED,
    COMM_UPDATED,
    COMMERCIAL,
    CORR_UPDATED,
    DOMAIN_COMMERCIAL,
    ST_COMMERCIAL_REVIEW,
    ST_DRAFT,
    ST_PM_APPROVAL,
)
from tl_mod_correspondence.textcheck import clean_body, clean_optional_text, clean_text

#: Data a subtype needs before it can go to review: the names of ``CommercialData`` fields.
REQUIRED_TO_SUBMIT: dict[str, tuple[str, ...]] = {
    "change_notice": ("entitlement_basis",),
    "claim_notice": ("entitlement_basis", "contract_clause_id"),
    "detailed_claim": (
        "entitlement_basis",
        "contract_clause_id",
        "estimated_value",
        "cost_code_impacts",
    ),
}
_UPDATABLE = (
    "currency",
    "estimated_value",
    "estimated_hours",
    "cost_code_impacts",
    "schedule_impact_days",
    "schedule_impact_note",
    "entitlement_basis",
)


class _CommercialFields(Command):
    """The fields a notice states, with their checks (shared by raising and updating)."""

    model_config = ConfigDict(extra="forbid")

    currency: str | None = Field(default=None, max_length=3)
    estimated_value: str | None = Field(default=None, max_length=20)
    estimated_hours: str | None = Field(default=None, max_length=20)
    cost_code_impacts: list[CostCodeImpact] | None = Field(default=None, max_length=MAX_IMPACTS)
    schedule_impact_days: int | None = Field(default=None, ge=-3650, le=3650)
    schedule_impact_note: str | None = Field(default=None, max_length=MAX_REASON)
    entitlement_basis: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return check_currency(value)

    @field_validator("estimated_value")
    @classmethod
    def _value(cls, value: str | None) -> str | None:
        return check_money(value, "estimated_value")

    @field_validator("estimated_hours")
    @classmethod
    def _hours(cls, value: str | None) -> str | None:
        return check_hours(value, "estimated_hours")

    @field_validator("schedule_impact_note", "entitlement_basis")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)


class RaiseCommercial(_CommercialFields):
    """Raise a Commercial item as a Draft (a document controller's act).

    ``subtype`` is one of the Commercial domain's (``early_warning``, ``change_notice``,
    ``site_instruction`` ...). ``clause`` is ``<contract>/<clause number>`` of an active contract
    clause: its time bar sets the length of the notice clock. ``aware_on`` is the day the
    contractor became aware of the event (today by default, never later); the time bar counts
    from it. ``currency`` is needed when any amount is stated. ``references`` are records the
    item refers to (RFIs, instructions, photos, daily records).
    """

    subtype: str = Field(min_length=1, max_length=MAX_NUMBER)
    subject: str = Field(min_length=1, max_length=MAX_TEXT)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    clause: str | None = Field(default=None, max_length=MAX_NUMBER)
    aware_on: str | None = Field(default=None, max_length=10)
    to: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    references: ReferenceList = Field(default_factory=list)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        return clean_text(non_blank(value))

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("clause")
    @classmethod
    def _clause(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @model_validator(mode="after")
    def _currency_for_amounts(self) -> RaiseCommercial:
        if _states_amount(self.estimated_value, self.cost_code_impacts) and self.currency is None:
            raise ValueError("state the currency of the amounts")
        return self


class UpdateCommercial(_CommercialFields):
    """Change a Commercial item that is a Draft or in commercial review (a controller's act).

    A field you leave out stays as it is; ``null`` clears an optional one. The clause and the
    awareness day cannot be changed. Give a ``reason`` when you change an item that is in review.
    """

    stream_id: str
    expected_version: int | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    body: str | None = Field(default=None, max_length=MAX_BODY)
    to: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    cc: list[Recipient] | None = Field(default=None, max_length=MAX_RECIPIENTS)
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("subject")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        return None if value is None else clean_text(non_blank(value))

    @field_validator("body")
    @classmethod
    def _body(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class SubmitCommercial(Command):
    """Send a Draft to commercial review. A claim needs its basis and its clause first."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None


class ReviewCommercial(Command):
    """Pass an item in commercial review to the project manager's approval."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    note: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReturnCommercial(Command):
    """Send an item in commercial review or PM approval back to its author. A reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


def _states_amount(value: str | None, impacts: list[CostCodeImpact] | None) -> bool:
    return value is not None or any(i.amount is not None for i in impacts or [])


def require_controller_viewer() -> None:
    """Refuse a viewer below a document controller: Commercial items are ``restricted``."""
    if confidentiality.current_viewer().level < 1:
        raise ForbiddenError("commercial items are for the document_controller and admin roles")


def resolve_clause(uow: UnitOfWork, cmd: Command, ref: str | None) -> str | None:
    """The record id of the active clause ``<contract>/<number>``, or ``None`` for none.

    Raises ``InvalidItemError`` for a reference that is not that shape or names no active clause
    of the scope.
    """
    if ref is None:
        return None
    contract, _, number = ref.partition("/")
    found = registry.find_clause(uow.conn(), cmd.scope, contract, number) if number else None
    if found is None or not found.is_active:
        raise InvalidItemError(f"{ref!r} is not an active contract clause of {cmd.scope}")
    return found.id


def _aware_on(value: str | None) -> str:
    try:
        found = plausible_date(value, "aware_on") or today()
    except ValueError as exc:
        raise InvalidItemError(str(exc)) from exc
    if found > today():
        raise InvalidItemError(f"aware_on {found} is after today ({today()})")
    return found


def create_commercial(
    uow: UnitOfWork,
    cmd: RaiseCommercial,
    *,
    definition: DomainDefinition,
    derived_from: registry.ItemRow | None = None,
    confidentiality_class: str | None = None,
    clearances: list[str] | None = None,
) -> CommandResult:
    """Make the item: ``Record.Created``, ``Correspondence.Defined``, ``Commercial.Defined``, the
    links, the awareness clocks and (for an item we receive) the move to Awaiting assessment.

    ``derived_from`` is the item this one was escalated from (a ``derived_from`` link is written
    as the module's own, which a person cannot retract); ``confidentiality_class`` and
    ``clearances`` override the domain's default class when the source asks for a higher one. A
    Python-only path: no field of ``RaiseCommercial`` can set them.
    """
    require_controller_viewer()
    chosen = definition.subtype(cmd.subtype)
    assert chosen is not None  # check_subtype ran
    clause_id = resolve_clause(uow, cmd, cmd.clause)
    aware_on = _aware_on(cmd.aware_on)
    impacts = check_impacts(cmd.cost_code_impacts or [])
    check_references(uow, cmd, cmd.references, None)
    direction = chosen.direction or "out"
    made = create_item(
        uow,
        cmd,
        subject=cmd.subject,
        direction=direction,
        medium="other",
        received_via="manual",
        to=cmd.to,
        cc=cmd.cc,
        received_on=today() if direction == "in" else None,
        body=cmd.body,
        confidentiality=confidentiality_class or definition.confidentiality_default,
        clearances=clearances or [],
        response_required=chosen.response_required,
        domain=DOMAIN_COMMERCIAL,
        subtype=cmd.subtype,
        record_type=COMMERCIAL,
        numbering=kind_numbering(definition, cmd.subtype),
        domain_events=[
            NewEvent(
                event_type=COMM_DEFINED,
                payload={
                    "contract_clause_id": clause_id,
                    "aware_on": aware_on,
                    "derived_from_id": derived_from.id if derived_from else None,
                    "currency": cmd.currency,
                    "estimated_value": cmd.estimated_value,
                    "estimated_hours": cmd.estimated_hours,
                    "cost_code_impacts": impacts,
                    "schedule_impact_days": cmd.schedule_impact_days,
                    "schedule_impact_note": cmd.schedule_impact_note,
                    "entitlement_basis": cmd.entitlement_basis,
                },
            )
        ],
    )
    events: list[Event] = list(made.events)
    version = made.version
    item = registry.get_item(uow.conn(), made.stream_id)
    assert item is not None  # the controller viewer reads what it made
    if derived_from is not None:
        events += handle_add_link(
            uow,
            AddLink(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                from_id=item.id,
                to_id=derived_from.id,
                relation="derived_from",
                link_source="rule",
                note=f"escalated from {derived_from.number}",
            ),
            by_module=True,
        ).events
    events += link_references(uow, cmd, item.id, cmd.references)
    _, clock_events = start_domain_clocks(
        uow, cmd, item, definition, "awareness", aware_on, clause_id=clause_id
    )
    events += clock_events
    if direction == "in":  # an instruction that arrived waits for our assessment
        moved = transition(uow, cmd, item.id, "receive")
        events += moved.events
        version = moved.version
    return CommandResult(stream_id=item.id, key=item.number, version=version, events=events)


def handle_raise_commercial(uow: UnitOfWork, cmd: RaiseCommercial) -> CommandResult:
    """Make a Commercial item (``create_commercial``).

    Raises ``ForbiddenError`` (the viewer is below a document controller),
    ``CorrespondenceScopeError``, ``UnknownDomainError`` (no such subtype), ``InvalidItemError``
    (an unknown clause, a day after today, a party, a text, a repeated reference),
    ``RecordNotFoundError`` (a reference that is unknown, foreign or hidden),
    ``InvalidClockError`` and ``CalendarUnavailableError`` (the time bar cannot be counted), and
    the numbering errors of the core.
    """
    require_controller_viewer()
    require_project(cmd)
    cmd = correlated(cmd)
    definition = catalog.check_subtype(cmd.scope, DOMAIN_COMMERCIAL, cmd.subtype)
    return create_commercial(uow, cmd, definition=definition)


def handle_update_commercial(uow: UnitOfWork, cmd: UpdateCommercial) -> CommandResult:
    """Append ``Record.Updated`` (the subject), ``Correspondence.Updated`` (recipients and text)
    and ``Commercial.Updated`` (the notice's own fields).

    Raises ``ForbiddenError``, ``RecordNotFoundError`` (unknown, foreign, hidden, or not a
    Commercial item), ``ItemStateError`` (not a Draft or in commercial review),
    ``InvalidItemError`` (a text, a party, an amount without a currency) and ``NoChangesError``.
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    item, data = row.item, row.data
    require_state(item, ST_DRAFT, ST_COMMERCIAL_REVIEW)
    given = cmd.model_fields_set
    old: dict[str, Any] = {
        "currency": data.currency,
        "estimated_value": data.estimated_value,
        "estimated_hours": data.estimated_hours,
        "cost_code_impacts": data.cost_code_impacts,
        "schedule_impact_days": data.schedule_impact_days,
        "schedule_impact_note": data.schedule_impact_note,
        "entitlement_basis": data.entitlement_basis,
    }
    new: dict[str, Any] = {}
    for name in _UPDATABLE:
        if name not in given:
            continue
        value = getattr(cmd, name)
        if name == "cost_code_impacts":
            value = check_impacts(value or [])
        new[name] = value
    after = {**old, **new}
    stated = after["estimated_value"] is not None or any(
        i.get("amount") is not None for i in after["cost_code_impacts"]
    )
    if stated and after["currency"] is None:
        raise InvalidItemError("state the currency of the amounts")
    register_old: dict[str, Any] = {"to": item.to, "cc": item.cc}
    register_new: dict[str, Any] = {}
    for name in ("to", "cc"):
        if name not in given:
            continue
        value = getattr(cmd, name)
        if value is None:
            raise InvalidItemError(f"{name} is a list; send [] to clear it")
        check_recipients(uow, cmd, value)
        register_new[name] = [r.as_payload() for r in value]
    if "body" in given:
        register_old["body"], register_new["body"] = item.body, check_body(cmd.body)
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
            NewEvent(event_type=CORR_UPDATED, payload={"changes": register, "reason": cmd.reason})
        )
    if domain:
        events.append(
            NewEvent(event_type=COMM_UPDATED, payload={"changes": domain, "reason": cmd.reason})
        )
    done = append(
        uow, cmd, item.id, item.record_type, events, expected=cmd.expected_version or item.version
    )
    return CommandResult(
        stream_id=item.id, key=item.number, version=done.new_version, events=list(done.events)
    )


def handle_submit_commercial(uow: UnitOfWork, cmd: SubmitCommercial) -> CommandResult:
    """Move a Draft to Commercial review.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (not a Draft) and
    ``InvalidItemError`` (no recipient, or data the subtype needs is missing).
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    item, data = row.item, row.data
    require_state(item, ST_DRAFT)
    missing: list[str] = []
    if item.direction == "out" and not item.to:
        missing.append("a recipient")
    for name in REQUIRED_TO_SUBMIT.get(item.subtype or "", ()):
        if not getattr(data, name):
            missing.append(name)
    if missing:
        raise InvalidItemError(f"item {item.number} needs {', '.join(missing)} before review")
    return transition(uow, cmd, item.id, "submit", expected=cmd.expected_version)


def handle_review_commercial(uow: UnitOfWork, cmd: ReviewCommercial) -> CommandResult:
    """Move an item in commercial review to PM approval.

    Raises ``ForbiddenError``, ``RecordNotFoundError`` and ``ItemStateError`` (not in review).
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    require_state(row.item, ST_COMMERCIAL_REVIEW)
    return transition(
        uow, cmd, row.item.id, "review", reason=cmd.note, expected=cmd.expected_version
    )


def handle_return_commercial(uow: UnitOfWork, cmd: ReturnCommercial) -> CommandResult:
    """Move an item in commercial review or PM approval back to Draft, with the reason.

    Raises ``ForbiddenError``, ``RecordNotFoundError`` and ``ItemStateError``.
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    require_state(row.item, ST_COMMERCIAL_REVIEW, ST_PM_APPROVAL)
    return transition(
        uow, cmd, row.item.id, "return", reason=cmd.reason, expected=cmd.expected_version
    )
