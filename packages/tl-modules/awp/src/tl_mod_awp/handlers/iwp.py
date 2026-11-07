"""Interim work package commands: create, move through the workflow, pin a document, split, cancel.

An IWP is a project record (``awp.IWP``) numbered from ``{project}-{type}-{discipline}-{seq:4}``
(gap-free per discipline). Its fields are editable in Draft, In development and Constraint check and
frozen from Ready; every move is a ``by_module`` workflow transition and the states each command
takes are the rows of ``actions.RULES`` (``states_for``). The scope is in ``handlers/scope.py``.

The sizing warning: when the estimated hours of a package are outside ``awp.iwp.size_hours``
[low, high] the command still succeeds and the last IWP event it writes carries
``warnings: ["iwp_oversize"]`` or ``["iwp_undersize"]`` in its payload (``with_warnings``). The
events are the channel a ``CommandResult`` has, as ``Workflow.Transitioned`` carries the expected
links a release misses. Fixed messages, never a cell of the input.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_awp.actions import states_for
from tl_mod_awp.common import (
    account_actor_exists,
    append,
    correlated,
    load_record,
    move,
    record_state,
    require_list_code,
    require_project,
    setting_value,
    version_of,
)
from tl_mod_awp.errors import IwpRuleError, IwpStateError, ScopeRuleError
from tl_mod_awp.fields import check_period
from tl_mod_awp.linking import sync_links
from tl_mod_awp.names import (
    BELONGS_RELATION,
    CWP,
    DOCUMENT_TYPE,
    IWP,
    IWP_CREATED,
    IWP_DOCUMENT_PINNED,
    IWP_DRAFT,
    IWP_EDITABLE,
    PIN_RELATION,
    WARN_OVERSIZE,
    WARN_UNDERSIZE,
)

if TYPE_CHECKING:
    from tl_mod_awp.commands import (
        CancelIwp,
        CreateIwp,
        PinIwpDocument,
        ReturnIwpToDevelopment,
        SendIwpToConstraintCheck,
        StartIwpDevelopment,
    )

DISCIPLINE_LIST = "Discipline"
SIZE_SETTING = "awp.iwp.size_hours"
MSG_FROZEN = "the fields and the scope of a package are frozen from Ready"
MSG_FOREMAN = "the foreman is not an account of this system"
MSG_NO_DOCUMENT = "no document with that id in the project"
MSG_BAD_PIN = "the pin does not name an issued revision of the document"
MSG_PLANNED = "the planned finish is before the planned start"
MSG_HOURS_BOUND = "the estimated hours would be above 10000000.0"
MSG_CWP_UNKNOWN = "no work package with that id in the project"
CWP_RELINK = "the package was split"

_IWP_SQL = text(
    "SELECT r.id, r.key, r.title, i.discipline, i.cwp_id, i.planned_start, i.planned_finish, "
    "i.foreman, i.estimated_hours, i.crew_text FROM cur_core_record r "
    "JOIN cur_awp_iwp i ON i.id = r.id WHERE r.id = :id"
)
_REVISION_SQL = text(
    "SELECT id, issued_on, voided FROM v_documents_revision "
    "WHERE document_id = :document AND code = :code"
)
_CURRENT_REVISION_SQL = text(
    "SELECT id FROM v_documents_revision WHERE document_id = :document AND is_current = :yes"
)
_DOCUMENT_SQL = text("SELECT id, scope, type, voided FROM cur_core_record WHERE id = :id")


@dataclass(frozen=True)
class Iwp:
    """An IWP as the handlers read it: the envelope, the typed row and the workflow state."""

    id: str
    key: str
    title: str
    version: int
    state: str
    discipline: str
    cwp_id: str | None
    planned_start: str | None
    planned_finish: str | None
    foreman: str | None
    estimated_hours: str | None
    crew_text: str | None


def load_iwp(uow: UnitOfWork, scope: str, iwp_id: str) -> Iwp:
    """The IWP ``iwp_id``; ``RecordNotFoundError`` (the same words) when it is hidden, absent, in
    another project, voided or not an IWP."""
    ref = load_record(uow, scope, iwp_id, IWP)
    conn = uow.conn()
    row = conn.execute(_IWP_SQL, {"id": ref.id}).first()
    if row is None:
        raise LookupError(f"no cur_awp_iwp row for {ref.id}")

    def opt(value: Any) -> str | None:
        return None if value is None else str(value)

    return Iwp(
        id=ref.id,
        key=ref.key or "",
        title=ref.title,
        version=version_of(uow, ref.id),
        state=record_state(conn, ref.id, IWP_DRAFT),
        discipline=str(row.discipline),
        cwp_id=opt(row.cwp_id),
        planned_start=opt(row.planned_start),
        planned_finish=opt(row.planned_finish),
        foreman=opt(row.foreman),
        estimated_hours=opt(row.estimated_hours),
        crew_text=opt(row.crew_text),
    )


def require_state(iwp: Iwp, command: str) -> None:
    """The IWP is in a state ``command`` takes (``actions.RULES``)."""
    if iwp.state in states_for(command, IWP):
        return
    if iwp.state not in IWP_EDITABLE and command in _EDIT_COMMANDS:
        raise IwpStateError(MSG_FROZEN)
    raise IwpStateError(f"a package that is {iwp.state} does not take {command}")


_EDIT_COMMANDS = frozenset({"AddIwpScope", "RemoveIwpScope", "PinIwpDocument", "SplitIwp"})


def with_warnings(events: list[NewEvent], codes: list[str]) -> None:
    """Put the warning codes into the payload of the last event (a no-op without codes)."""
    if codes and events:
        last = events[-1]
        events[-1] = NewEvent(
            event_type=last.event_type, payload={**last.payload, "warnings": codes}
        )


def size_bounds(conn: Connection, scope: str) -> tuple[Decimal, Decimal]:
    """``[low, high]`` of the setting ``awp.iwp.size_hours``."""
    low, high = setting_value(conn, scope, SIZE_SETTING)
    return Decimal(str(low)), Decimal(str(high))


def size_warnings(conn: Connection, scope: str, hours: str | None) -> list[str]:
    """The sizing warning codes for ``hours``: none when unset or inside the bounds."""
    if hours is None:
        return []
    low, high = size_bounds(conn, scope)
    value = Decimal(hours)
    if value > high:
        return [WARN_OVERSIZE]
    if value < low:
        return [WARN_UNDERSIZE]
    return []


def check_foreman(conn: Connection, foreman: str | None) -> None:
    if foreman is not None and not account_actor_exists(conn, foreman):
        raise IwpRuleError(MSG_FOREMAN)


def check_dates(start: str | None, finish: str | None) -> None:
    try:
        check_period(start, finish)
    except ValueError:
        raise IwpRuleError(MSG_PLANNED) from None


def require_cwp(uow: UnitOfWork, scope: str, cwp_id: str | None) -> None:
    if cwp_id is None:
        return
    try:
        load_record(uow, scope, cwp_id, CWP)
    except RecordNotFoundError:
        raise IwpRuleError(MSG_CWP_UNKNOWN) from None


@dataclass(frozen=True)
class IwpFields:
    """What a new IWP carries (a create and the new packages of a split)."""

    discipline: str
    title: str
    cwp_id: str | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    foreman: str | None = None
    estimated_hours: str | None = None
    crew_text: str | None = None


def create_iwp(uow: UnitOfWork, cmd: Command, fields: IwpFields) -> CommandResult:
    """``Numbering.Allocated``, ``Record.Created``, ``IWP.Created`` and, when it names a work
    package, the ``belongs_to`` link to it. The sizing warning rides on ``IWP.Created``."""
    conn = uow.conn()
    payload: dict[str, Any] = {
        "discipline": fields.discipline,
        "cwp_id": fields.cwp_id,
        "planned_start": fields.planned_start,
        "planned_finish": fields.planned_finish,
        "foreman": fields.foreman,
        "estimated_hours": fields.estimated_hours,
        "crew_text": fields.crew_text,
    }
    warnings = size_warnings(conn, cmd.scope, fields.estimated_hours)
    if warnings:
        payload["warnings"] = warnings
    made = create_module_record(
        uow,
        cmd,
        record_type=IWP,
        title=fields.title,
        key=None,
        numbering={"discipline": fields.discipline},
        extra_events=[NewEvent(event_type=IWP_CREATED, payload=payload)],
    )
    events = list(made.events)
    if fields.cwp_id is not None:
        events.extend(
            sync_links(uow, cmd, made.stream_id, BELONGS_RELATION, {fields.cwp_id}, CWP_RELINK)
        )
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=made.version, events=events
    )


def handle_create_iwp(uow: UnitOfWork, cmd: CreateIwp) -> CommandResult:
    """Create an IWP. Raises ``UnknownListCodeError`` (discipline), ``IwpRuleError`` (dates,
    foreman, work package). With no ``estimated_hours`` the value is derived from the scope as it
    is added; the sizing warning is on ``IWP.Created`` when the value is given."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    require_list_code(conn, cmd.scope, DISCIPLINE_LIST, cmd.discipline, "the discipline")
    check_dates(cmd.planned_start, cmd.planned_finish)
    check_foreman(conn, cmd.foreman)
    require_cwp(uow, cmd.scope, cmd.cwp_id)
    return create_iwp(
        uow,
        cmd,
        IwpFields(
            discipline=cmd.discipline,
            title=cmd.title,
            cwp_id=cmd.cwp_id,
            planned_start=cmd.planned_start,
            planned_finish=cmd.planned_finish,
            foreman=cmd.foreman,
            estimated_hours=cmd.estimated_hours,
            crew_text=cmd.crew_text,
        ),
    )


def _simple_move(
    uow: UnitOfWork, cmd: Any, command: str, transition: str, reason: str | None = None
) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, command)
    moved = move(uow, cmd, iwp.id, transition, reason)
    return CommandResult(stream_id=iwp.id, key=iwp.key, version=moved.version, events=moved.events)


def handle_start_iwp_development(uow: UnitOfWork, cmd: StartIwpDevelopment) -> CommandResult:
    """Draft to In development."""
    return _simple_move(uow, cmd, "StartIwpDevelopment", "develop", cmd.reason)


def handle_send_iwp_to_constraint_check(
    uow: UnitOfWork, cmd: SendIwpToConstraintCheck
) -> CommandResult:
    """In development to Constraint check."""
    return _simple_move(uow, cmd, "SendIwpToConstraintCheck", "check_constraints", cmd.reason)


def handle_return_iwp_to_development(uow: UnitOfWork, cmd: ReturnIwpToDevelopment) -> CommandResult:
    """Constraint check back to In development."""
    return _simple_move(uow, cmd, "ReturnIwpToDevelopment", "return", cmd.reason)


def handle_cancel_iwp(uow: UnitOfWork, cmd: CancelIwp) -> CommandResult:
    """Any live state to Cancelled (``awp.void``, a controller's word)."""
    return _simple_move(uow, cmd, "CancelIwp", "cancel", cmd.reason)


def pin_document(
    uow: UnitOfWork, cmd: Command, iwp_id: str, document_id: str, pin: str | None
) -> list[Any]:
    """Pin ``pin`` (a revision code; floating when ``None``) of a document to the IWP: the
    ``Link.Added`` (``references`` with the pin, written through ``tl_core``) and the
    ``IWP.DocumentPinned`` event. Returns the events. The documents module is not imported: the
    revision is read from its view."""
    conn = uow.conn()
    confidentiality.require_visible(conn, document_id)
    doc = conn.execute(_DOCUMENT_SQL, {"id": document_id}).first()
    if (
        doc is None
        or doc.type != DOCUMENT_TYPE
        or bool(doc.voided)
        or doc.scope not in (cmd.scope, "company")
    ):
        raise ScopeRuleError(MSG_NO_DOCUMENT)
    revision_id: str | None
    if pin is None:
        found = conn.execute(
            _CURRENT_REVISION_SQL, {"document": document_id, "yes": True}
        ).scalar_one_or_none()
        revision_id = None if found is None else str(found)
    else:
        row = conn.execute(_REVISION_SQL, {"document": document_id, "code": pin}).first()
        if row is None or row.issued_on is None or bool(row.voided):
            raise ScopeRuleError(MSG_BAD_PIN)
        revision_id = str(row.id)
    linked = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=iwp_id,
            to_id=document_id,
            relation=PIN_RELATION,
            pin=pin,
        ),
        by_module=True,
    )
    pinned = append(
        uow,
        cmd,
        iwp_id,
        IWP,
        [
            NewEvent(
                event_type=IWP_DOCUMENT_PINNED,
                payload={"document_id": document_id, "revision_id": revision_id},
            )
        ],
    )
    return [*pinned.events, *linked.events]


def handle_pin_iwp_document(uow: UnitOfWork, cmd: PinIwpDocument) -> CommandResult:
    """Pin a document to an IWP (a revision code, or floating). Raises ``IwpStateError`` (frozen),
    ``ScopeRuleError`` (not a document of the project, a pin that is not an issued revision)."""
    require_project(cmd)
    cmd = correlated(cmd)
    iwp = load_iwp(uow, cmd.scope, cmd.iwp)
    require_state(iwp, "PinIwpDocument")
    events = pin_document(uow, cmd, iwp.id, cmd.document, cmd.pin)
    return CommandResult(
        stream_id=iwp.id, key=iwp.key, version=version_of(uow, iwp.id), events=events
    )


__all__ = [
    "Iwp",
    "IwpFields",
    "check_dates",
    "check_foreman",
    "create_iwp",
    "handle_cancel_iwp",
    "handle_create_iwp",
    "handle_pin_iwp_document",
    "handle_return_iwp_to_development",
    "handle_send_iwp_to_constraint_check",
    "handle_start_iwp_development",
    "load_iwp",
    "pin_document",
    "require_cwp",
    "require_state",
    "size_bounds",
    "size_warnings",
    "with_warnings",
]
