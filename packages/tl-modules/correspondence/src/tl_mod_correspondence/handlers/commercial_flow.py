"""Issue a Commercial item, record its assessment, close it, refer a dispute to the legal route.

The author's commands are in ``commercial.py``; these are the rest of the life of a Commercial
item (workflow ``correspondence.commercial``). All of them are a document controller's:

* ``IssueCommercial``: approves and issues the notice. Renders it to a PDF, stores it, "sends" it
  (a stub: nothing leaves the machine), **meets the time bar** on the issue day (the notice was
  given; a day after the due date shows as late), starts the clocks that wait for the assessment,
  and moves the item PM approval, Issued, Awaiting assessment.
* ``AssessCommercial``: records the other party's assessment: agreed, disputed or partially
  agreed, with the value they assessed. The clocks that waited for it are met.
* ``CloseCommercial``: the item needs no more work; its open clocks are cancelled.
* ``ReferCommercialToLegal``: a dispute leaves this domain for the legal route (a domain of a
  later phase); the item is Escalated and its clocks are cancelled.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, files, registry
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, LetterRenderError
from tl_mod_correspondence.handlers.clocks import close_clocks_of_item
from tl_mod_correspondence.handlers.commercial import require_controller_viewer
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    require_state,
    resolve_date,
    today,
    transition,
)
from tl_mod_correspondence.handlers.domain import (
    check_money,
    feed_fields,
    open_commercial,
    start_domain_clocks,
)
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.letter import LetterError, LetterFields, compose_letter, render_pdf
from tl_mod_correspondence.limits import MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    ASSESSMENT_STATUSES,
    COMM_ASSESSED,
    CORR_ISSUED,
    DOMAIN_COMMERCIAL,
    ST_AGREED,
    ST_AWAITING_ASSESSMENT,
    ST_DISPUTED,
    ST_PARTLY_AGREED,
    ST_PM_APPROVAL,
)
from tl_mod_correspondence.textcheck import clean_optional_text, clean_text

AssessmentStatus = Literal["agreed", "disputed", "partially_agreed"]
_MOVE = {"agreed": "agree", "disputed": "dispute", "partially_agreed": "part_agree"}
ASSESSMENT_CLOCKS = ("response_from_them",)


class IssueCommercial(Command):
    """Approve and issue a Commercial item that has passed commercial review.

    The notice is rendered from the domain's template for the subtype (or ``template``). The send
    is a stub: nothing leaves the machine. ``issued_on`` is the date on the notice (today by
    default; an earlier day needs ``date_reason``; never later than today). A notice issued after
    its time bar ran out is issued all the same and the clock shows it was late.
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


class AssessCommercial(Command):
    """Record the other party's assessment of an issued item (or of an instruction we received).

    ``status`` is ``agreed``, ``disputed`` or ``partially_agreed``. ``assessed_value`` (in the
    currency of the item) is required unless the item is disputed. ``assessed_on`` is today by
    default; an earlier day needs ``date_reason``.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    status: AssessmentStatus
    assessed_value: str | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=MAX_REASON)
    assessed_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("assessed_value")
    @classmethod
    def _value(cls, value: str | None) -> str | None:
        return check_money(value, "assessed_value")

    @field_validator("note", "date_reason")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class CloseCommercial(Command):
    """Close an assessed item. Its open clocks are cancelled. A disputed item needs a ``reason``."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str | None = Field(default=None, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReferCommercialToLegal(Command):
    """Take a disputed item to the legal route. The item is Escalated; a reason is required."""

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return clean_text(non_blank(value))


def _letter_body(item: registry.ItemRow, text_lines: list[str]) -> str:
    return "\n\n".join(line for line in [item.body or "", *text_lines] if line)


def handle_issue_commercial(uow: UnitOfWork, cmd: IssueCommercial) -> CommandResult:
    """Render and store the PDF, "send" it, meet the time bar, start the issue clocks, append
    ``Correspondence.Issued`` and move the item to Awaiting assessment.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (not in PM approval),
    ``InvalidItemError`` (no recipient), ``UnknownDomainError``, ``LetterRenderError`` and the
    date errors of ``resolve_date``.
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    item, data = row.item, row.data
    require_state(item, ST_PM_APPROVAL)
    recipients = ", ".join(r.get("name") or r.get("email") or "" for r in item.to).strip(", ")
    if not recipients:
        raise InvalidItemError(f"item {item.number} has no recipient")
    definition = catalog.check_subtype(cmd.scope, DOMAIN_COMMERCIAL, item.subtype or "")
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
    lines: list[str] = []
    if data.estimated_value is not None:
        lines.append(f"Estimated value: {data.currency} {data.estimated_value}")
    if data.estimated_hours is not None:
        lines.append(f"Estimated hours: {data.estimated_hours}")
    if data.schedule_impact_days is not None:
        lines.append(f"Schedule impact: {data.schedule_impact_days} days")
    if data.schedule_impact_note:
        lines.append(data.schedule_impact_note)
    if data.entitlement_basis:
        lines.append(f"Basis: {data.entitlement_basis}")
    if data.contract_clause_id is not None:
        clause = registry.get_clause(uow.conn(), data.contract_clause_id)
        if clause is not None:
            lines.append(f"Given under clause {clause.contract}/{clause.clause_number}.")
    try:
        letter = compose_letter(
            template.header,
            template.footer,
            LetterFields(
                number=item.number,
                date=day,
                subject=item.subject,
                to=recipients,
                body=_letter_body(item, lines),
            ),
        )
        pdf = render_pdf(letter, title=f"{item.number} {item.subject}")
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
    met = close_clocks_of_item(
        uow,
        cmd,
        item.id,
        how="met",
        day=day,
        reason="the notice was issued",
        kinds=("time_bar",),
    )
    clock_ids, clock_events = start_domain_clocks(uow, cmd, item, definition, "issue", day)
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
                        minimal="A commercial notice was issued",
                    ),
                },
            )
        ],
        expected=cmd.expected_version or item.version,
    )
    issued = transition(uow, cmd, item.id, "issue")
    waiting = transition(uow, cmd, item.id, "await_assessment")
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=waiting.version,
        events=[*met, *clock_events, *done.events, *issued.events, *waiting.events],
    )


def handle_assess_commercial(uow: UnitOfWork, cmd: AssessCommercial) -> CommandResult:
    """Append ``Commercial.Assessed``, move the item to Agreed, Disputed or Partially agreed and
    meet the clocks that waited for the assessment.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (not awaiting an
    assessment), ``InvalidItemError`` (a value is missing for an agreed or partly agreed item, or
    the item states no currency) and the date errors of ``resolve_date``.
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    item, data = row.item, row.data
    require_state(item, ST_AWAITING_ASSESSMENT)
    if cmd.status not in ASSESSMENT_STATUSES:  # the model's Literal says the same; belt and braces
        raise InvalidItemError(f"status is one of {', '.join(ASSESSMENT_STATUSES)}")
    if cmd.status != "disputed" and cmd.assessed_value is None:
        raise InvalidItemError(f"an {cmd.status.replace('_', ' ')} item needs the assessed value")
    if cmd.assessed_value is not None and data.currency is None:
        raise InvalidItemError(
            f"item {item.number} states no currency; update it before recording a value"
        )
    day, date_reason = resolve_date(cmd.assessed_on, cmd.date_reason, "the assessment day")
    definition = catalog.check_subtype(cmd.scope, DOMAIN_COMMERCIAL, item.subtype or "")
    append(
        uow,
        cmd,
        item.id,
        item.record_type,
        [
            NewEvent(
                event_type=COMM_ASSESSED,
                payload={
                    "status": cmd.status,
                    "assessed_value": cmd.assessed_value,
                    "assessed_on": day,
                    "date_reason": date_reason,
                    "note": cmd.note,
                    **feed_fields(
                        definition,
                        full=f"{item.number} assessed as {cmd.status.replace('_', ' ')}",
                        minimal="A commercial notice was assessed",
                    ),
                },
            )
        ],
        expected=cmd.expected_version or item.version,
    )
    moved = transition(uow, cmd, item.id, _MOVE[cmd.status], reason=cmd.note)
    met = close_clocks_of_item(
        uow,
        cmd,
        item.id,
        how="met",
        day=day,
        reason="assessed",
        kinds=ASSESSMENT_CLOCKS,
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=moved.version,
        events=[*moved.events, *met],
    )


def handle_close_commercial(uow: UnitOfWork, cmd: CloseCommercial) -> CommandResult:
    """Move the item to Closed and cancel its open clocks.

    Raises ``ForbiddenError``, ``RecordNotFoundError``, ``ItemStateError`` (the item is not
    Agreed, Partially agreed or Disputed; or it is Disputed and no ``reason`` was given).
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    item = row.item
    require_state(item, ST_AGREED, ST_PARTLY_AGREED, ST_DISPUTED)
    if item.state == ST_DISPUTED and not (cmd.reason and cmd.reason.strip()):
        raise ItemStateError(f"item {item.number} is disputed; give the reason for closing it")
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


def handle_refer_commercial_to_legal(uow: UnitOfWork, cmd: ReferCommercialToLegal) -> CommandResult:
    """Move a disputed item to Escalated and cancel its open clocks.

    Raises ``ForbiddenError``, ``RecordNotFoundError`` and ``ItemStateError`` (not Disputed).
    """
    require_controller_viewer()
    cmd = correlated(cmd)
    row = open_commercial(uow, cmd, cmd.stream_id)
    item = row.item
    require_state(item, ST_DISPUTED)
    moved = transition(
        uow, cmd, item.id, "escalate", reason=cmd.reason, expected=cmd.expected_version
    )
    cancelled = close_clocks_of_item(
        uow, cmd, item.id, how="cancelled", day=today(), reason="referred to the legal route"
    )
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=moved.version,
        events=[*moved.events, *cancelled],
    )
