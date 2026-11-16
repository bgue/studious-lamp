"""Scaffold commands: register, design, erect, inspect, tag green, release, modify, dismantle,
remove.

A scaffold is one record of ``scaffold.Scaffold``; an inspection is a record of
``scaffold.ScaffoldInspection`` made with the ``Scaffold.Inspected`` event. Every state move is a
``by_module`` workflow transition run in the same unit of work as the module's own event. Refusals
use fixed messages: an id the viewer may not read, one in another project and one that does not
exist answer alike. Who may act is the access word of the command, checked by the platform before
the handler runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.ledger import NewEvent
from tl_core.services.commands import CommandResult
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow
from tl_mod_requisitions import api as requisitions_api

from tl_mod_scaffold import rules
from tl_mod_scaffold.errors import DismantleRefused, ScaffoldRuleError, ScaffoldStateError
from tl_mod_scaffold.guards import STATES, require_not_removed
from tl_mod_scaffold.handlers.common import (
    RecordRef,
    append,
    correlated,
    interval_days,
    load_record,
    move,
    record_state,
    require_project,
    require_version,
    silent,
    valid_time,
)
from tl_mod_scaffold.names import (
    BELONGS_TO,
    DESIGNED,
    DISMANTLE_STARTED,
    ERECTING,
    ERECTING_STATE,
    FAIL,
    GREEN,
    IN_USE,
    INSPECTED,
    INSPECTED_STATE,
    INSPECTION,
    IWP_INITIAL,
    IWP_TYPE,
    MODIFIED,
    MODIFY,
    PASS,
    REGISTERED,
    RELEASED,
    REMOVED_EVENT,
    REQUEST_REGISTERABLE,
    REQUEST_TABLE,
    REQUEST_TYPE,
    REQUESTED,
    REQUIRES,
    RULE_LINK_SOURCE,
    SCAFFOLD,
    SCAFFOLD_TABLE,
    T_DESIGN,
    T_DISMANTLE,
    T_ERECT,
    T_MODIFY,
    T_PASS,
    T_RELEASE,
    T_REMOVE,
)

if TYPE_CHECKING:
    from tl_mod_scaffold.commands import (
        DesignScaffold,
        DismantleScaffold,
        ErectScaffold,
        InspectScaffold,
        ModifyScaffold,
        RegisterScaffold,
        ReleaseScaffold,
        RemoveScaffold,
        TagScaffoldGreen,
    )

MSG_REQUEST_STATE = "a scaffold needs an approved scaffold request"
MSG_ONE_PER_REQUEST = "that scaffold request already has a scaffold"
MSG_NOT_GREEN = "a scaffold is released only with a green tag"
MSG_HIDDEN_IWP = rules.MSG_HIDDEN_IWP
MSG_FAILED_INSPECTION = "failed inspection"
_ROW_SQL = text(f"SELECT * FROM {SCAFFOLD_TABLE} WHERE id = :id")
_REQUEST_SQL = text(
    f"SELECT for_record_id, elevation, gridline, load_class FROM {REQUEST_TABLE} WHERE id = :id"
)
_ONE_SQL = text(f"SELECT 1 FROM {SCAFFOLD_TABLE} WHERE request_id = :request")
_REQUIRING_SQL = text(
    "SELECT cr.id, cr.key, COALESCE(cr.status, :initial) AS state FROM cur_links l "
    "JOIN cur_core_record cr ON cr.id = l.from_id "
    "WHERE l.scope = :scope AND l.relation = :relation AND l.to_id = :scaffold "
    "AND l.status <> 'retracted' AND cr.type = :iwp AND cr.voided = :no "
    "ORDER BY cr.key, cr.id"
)


@dataclass(frozen=True)
class Scaffold:
    """A scaffold as the handlers read it: the envelope, the typed row and the state."""

    ref: RecordRef
    state: str
    row: dict[str, Any]

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def key(self) -> str:
        return self.ref.key or ""


def load_scaffold(uow: UnitOfWork, scope: str, scaffold_id: str) -> Scaffold:
    """The scaffold; ``RecordNotFoundError`` (the same words) when it is hidden, absent, in another
    project, voided or not a scaffold."""
    ref = load_record(uow, scope, scaffold_id, (SCAFFOLD,))
    row = uow.conn().execute(_ROW_SQL, {"id": ref.id}).mappings().first()
    if row is None:
        raise LookupError(f"no scaffold row for {ref.id}")
    return Scaffold(ref=ref, state=record_state(uow, ref.id, REQUESTED), row=dict(row))


def require_state(scaffold: Scaffold, command: str) -> None:
    """The scaffold is not removed and is in a state ``command`` takes (``guards.STATES``)."""
    require_not_removed(scaffold.state)
    needed = STATES[command]
    if scaffold.state not in needed:
        raise ScaffoldStateError(
            f"a scaffold that is {scaffold.state} does not take {command}; "
            f"it needs {' or '.join(needed)}"
        )


def _start(uow: UnitOfWork, cmd: Any, command: str) -> tuple[Any, Scaffold]:
    """The common opening of a command on a scaffold: project, correlation, load, state, version."""
    require_project(cmd)
    cmd = correlated(cmd)
    scaffold = load_scaffold(uow, cmd.scope, cmd.scaffold)
    require_state(scaffold, command)
    require_version(uow, scaffold.id, cmd.expected_version)
    return cmd, scaffold


def _step(
    uow: UnitOfWork,
    cmd: Any,
    scaffold: Scaffold,
    transition: str | None,
    events: list[tuple[str, dict[str, Any]]],
) -> CommandResult:
    """Append the module's events, then run the workflow transition (one unit of work)."""
    done = append(
        uow,
        cmd,
        scaffold.id,
        SCAFFOLD,
        [NewEvent(event_type=t, payload=silent(p)) for t, p in events],
    )
    if transition is None:
        return CommandResult(
            stream_id=scaffold.id,
            key=scaffold.key,
            version=done.new_version,
            events=list(done.events),
        )
    moved = move(uow, cmd, scaffold.id, transition)
    return CommandResult(
        stream_id=scaffold.id,
        key=scaffold.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def handle_register_scaffold(uow: UnitOfWork, cmd: RegisterScaffold) -> CommandResult:
    """Register a scaffold in state Requested from an approved scaffold request, numbered per
    project, with a ``belongs_to`` link to the request. The request's elevation, gridline, load
    class and subject are copied."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    request = load_record(uow, cmd.scope, cmd.request_id, (REQUEST_TYPE,))
    if record_state(uow, request.id, REQUESTED) not in REQUEST_REGISTERABLE:
        raise ScaffoldRuleError(MSG_REQUEST_STATE)
    if conn.execute(_ONE_SQL, {"request": request.id}).first() is not None:
        raise ScaffoldRuleError(MSG_ONE_PER_REQUEST)
    found = conn.execute(_REQUEST_SQL, {"id": request.id}).mappings().first()
    if found is None:
        raise LookupError(f"no scaffold request row for {request.id}")
    made = create_module_record(
        uow, cmd, record_type=SCAFFOLD, title=cmd.title, description=None, key=None
    )
    # the payload names the stream (`record_id` is required by the catalog), which exists only now;
    # same unit of work, so the envelope and this event commit together
    registered = append(
        uow,
        cmd,
        made.stream_id,
        SCAFFOLD,
        [
            NewEvent(
                event_type=REGISTERED,
                payload=silent(
                    {
                        "record_id": made.stream_id,
                        "request_id": request.id,
                        "for_record_id": found["for_record_id"],
                        "location_text": cmd.location_text,
                        "elevation": found["elevation"],
                        "gridline": found["gridline"],
                        "load_class": found["load_class"],
                    }
                ),
            )
        ],
    )
    linked = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=made.stream_id,
            to_id=request.id,
            relation=BELONGS_TO,
            link_source=RULE_LINK_SOURCE,
        ),
        by_module=True,
    )
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=registered.new_version,
        events=[*made.events, *registered.events, *linked.events],
    )


def handle_design_scaffold(uow: UnitOfWork, cmd: DesignScaffold) -> CommandResult:
    """Requested to Designed."""
    cmd, scaffold = _start(uow, cmd, "DesignScaffold")
    return _step(uow, cmd, scaffold, T_DESIGN, [(DESIGNED, {"note": cmd.note})])


def handle_erect_scaffold(uow: UnitOfWork, cmd: ErectScaffold) -> CommandResult:
    """Designed to Erecting; the first inspection falls due one interval after today."""
    cmd, scaffold = _start(uow, cmd, "ErectScaffold")
    due = rules.next_due(utcnow().date(), interval_days(uow, cmd.scope))
    payload = {"note": cmd.note, "next_due_on": due.isoformat()}
    return _step(uow, cmd, scaffold, T_ERECT, [(ERECTING, payload)])


def _inspect(
    uow: UnitOfWork,
    cmd: Any,
    scaffold: Scaffold,
    *,
    result: str,
) -> CommandResult:
    """Record an inspection (its record, ``Scaffold.Inspected``), set the tag by ``rules.tag_for``
    and the next due day by ``rules.next_due``; a pass from Erecting or Modify also does ``pass``,
    a fail on Inspected or In Use also does ``modify``."""
    at = valid_time(cmd.at, scaffold.ref.created_on)
    inspected_on = at[:10]
    due = rules.next_due(date.fromisoformat(inspected_on), interval_days(uow, cmd.scope))
    tag = rules.tag_for(result)
    inspection = create_module_record(
        uow,
        cmd,
        record_type=INSPECTION,
        title=f"Inspection of {scaffold.key}",
        description=None,
        key=None,
    )
    events: list[tuple[str, dict[str, Any]]] = [
        (
            INSPECTED,
            {
                "inspection_id": inspection.stream_id,
                "result": result,
                "tag": tag,
                "inspected_on": inspected_on,
                "next_due_on": due.isoformat(),
                "note": cmd.note,
                "at": at,
            },
        )
    ]
    transition: str | None = None
    if result == PASS and scaffold.state in (ERECTING_STATE, MODIFY):
        transition = T_PASS
    elif result == FAIL and scaffold.state in (INSPECTED_STATE, IN_USE):
        events.append((MODIFIED, {"reason": MSG_FAILED_INSPECTION}))
        transition = T_MODIFY
    done = _step(uow, cmd, scaffold, transition, events)
    return CommandResult(
        stream_id=done.stream_id,
        key=done.key,
        version=done.version,
        events=[*inspection.events, *done.events],
    )


def handle_inspect_scaffold(uow: UnitOfWork, cmd: InspectScaffold) -> CommandResult:
    """A conditional (tag yellow) or failed (tag red) inspection."""
    cmd, scaffold = _start(uow, cmd, "InspectScaffold")
    return _inspect(uow, cmd, scaffold, result=cmd.result)


def handle_tag_scaffold_green(uow: UnitOfWork, cmd: TagScaffoldGreen) -> CommandResult:
    """A passed inspection: the tag is green; from Erecting or Modify the scaffold is Inspected."""
    cmd, scaffold = _start(uow, cmd, "TagScaffoldGreen")
    return _inspect(uow, cmd, scaffold, result=PASS)


def handle_release_scaffold(uow: UnitOfWork, cmd: ReleaseScaffold) -> CommandResult:
    """Inspected to In Use, with a green tag."""
    cmd, scaffold = _start(uow, cmd, "ReleaseScaffold")
    if scaffold.row["tag"] != GREEN:
        raise ScaffoldRuleError(MSG_NOT_GREEN)
    return _step(uow, cmd, scaffold, T_RELEASE, [(RELEASED, {})])


def handle_modify_scaffold(uow: UnitOfWork, cmd: ModifyScaffold) -> CommandResult:
    """Inspected or In Use to Modify; the tag stays until the next inspection."""
    cmd, scaffold = _start(uow, cmd, "ModifyScaffold")
    return _step(uow, cmd, scaffold, T_MODIFY, [(MODIFIED, {"reason": cmd.reason})])


def _hidden(conn: Connection, record_ids: list[str]) -> set[str]:
    """The ids among ``record_ids`` the actor (the ambient viewer) may not read."""
    return confidentiality.hidden_among(conn, record_ids)


def dismantle_inputs(
    conn: Connection, scope: str, scaffold: Scaffold
) -> tuple[dict[str, str], list[str], list[str]]:
    """What ``rules.dismantle_blockers`` takes: the states of the visible work packages with a live
    ``requires`` link to this scaffold, the states of the hidden ones (a list: they are counted,
    never named), and the keys of the other open scaffold requests of those
    packages. The
    requests are read as the lowest viewer, so a hidden one is left out."""
    rows = conn.execute(
        _REQUIRING_SQL,
        {
            "initial": IWP_INITIAL,
            "scope": scope,
            "relation": REQUIRES,
            "scaffold": scaffold.id,
            "iwp": IWP_TYPE,
            "no": False,
        },
    ).all()
    hidden = _hidden(conn, [str(r.id) for r in rows])
    states: dict[str, str] = {}
    hidden_states: list[str] = []
    requests: set[str] = set()
    own = str(scaffold.row["request_id"])
    for r in rows:
        if str(r.id) in hidden:
            hidden_states.append(str(r.state))
        else:
            states[str(r.key)] = str(r.state)
        for found in requisitions_api.open_requisitions_for(
            conn, str(r.id), kinds=["scaffold"], viewer=confidentiality.LOWEST
        ):
            if found.id != own:
                requests.add(found.key)
    return states, sorted(requests), hidden_states


def handle_dismantle_scaffold(uow: UnitOfWork, cmd: DismantleScaffold) -> CommandResult:
    """The dismantle check, then Inspected, In Use or Modify to Dismantle."""
    cmd, scaffold = _start(uow, cmd, "DismantleScaffold")
    states, requests, hidden_states = dismantle_inputs(uow.conn(), cmd.scope, scaffold)
    reasons = rules.dismantle_blockers(states, requests, hidden_states)
    if reasons:
        raise DismantleRefused("; ".join(reasons))
    return _step(uow, cmd, scaffold, T_DISMANTLE, [(DISMANTLE_STARTED, {"reason": cmd.reason})])


def handle_remove_scaffold(uow: UnitOfWork, cmd: RemoveScaffold) -> CommandResult:
    """Dismantle to Removed, or Requested or Designed to Removed (withdrawn)."""
    cmd, scaffold = _start(uow, cmd, "RemoveScaffold")
    return _step(uow, cmd, scaffold, T_REMOVE, [(REMOVED_EVENT, {"reason": cmd.reason})])


__all__ = [
    "Scaffold",
    "dismantle_inputs",
    "handle_design_scaffold",
    "handle_dismantle_scaffold",
    "handle_erect_scaffold",
    "handle_inspect_scaffold",
    "handle_modify_scaffold",
    "handle_register_scaffold",
    "handle_release_scaffold",
    "handle_remove_scaffold",
    "handle_tag_scaffold_green",
]
