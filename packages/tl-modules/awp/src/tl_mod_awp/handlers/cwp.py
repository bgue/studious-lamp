"""Construction work package commands: create, revise, allocate, move through the workflow.

A package is a project record (``awp.CWP``) numbered by the allocator from the pattern
``{project}-{type}-{discipline}-{seq:4}`` (gap-free per discipline). Its life is the workflow
``awp-cwp``; every move is a command here (``handle_transition_workflow(..., by_module=True)``), and
the states each command takes are the rows of ``actions.RULES`` (``states_for``). The fields are
frozen from Released for IWP development: only ``ReturnCwp`` opens them again. The module keeps the
links ``belongs_to`` the area and each allocated WBS node in step with the typed rows
(``linking.sync_links``; ``by_module=True``, source ``rule``). A change of a budget, an allocation
or a void asks for a rollup. Fixed messages, never a cell of the input. All the events of a command
share one correlation id.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core.ledger import NewEvent, canonical_json
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoChangesError
from tl_core.services.records import create_module_record
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork

from tl_mod_awp import rollup
from tl_mod_awp.actions import states_for
from tl_mod_awp.common import (
    HUNDRED,
    append,
    check_allocations,
    correlated,
    get_cwa,
    load_record,
    package_state,
    percent_text,
    require_code,
    require_list_code,
    require_project,
    resolve_code,
    silent,
    version_of,
)
from tl_mod_awp.errors import (
    AllocationError,
    CwpRuleError,
    CwpStateError,
    ReleaseRefusedError,
    RetiredError,
    StaleVersionError,
    WbsRuleError,
)
from tl_mod_awp.fields import as_rows, check_period, check_quantity_rows
from tl_mod_awp.linking import sync_links
from tl_mod_awp.names import (
    BELONGS_RELATION,
    CWA,
    CWP,
    CWP_ALLOCATED,
    CWP_ALLOCATION_TABLE,
    CWP_DEFINED,
    CWP_RELEASED,
    CWP_REVISED,
    CWP_TABLE,
    EDITABLE_STATES,
    WBS_NODE,
    WBS_NODE_TABLE,
)

if TYPE_CHECKING:
    from tl_mod_awp.commands import (
        AllocateCwpToWbs,
        CloseCwp,
        CompleteCwp,
        CreateCwp,
        ReleaseCwp,
        ReopenCwp,
        RequestRollup,
        ReturnCwp,
        ReviseCwp,
        StartCwpDevelopment,
        StartCwpExecution,
        VoidCwp,
    )

DISCIPLINE_LIST = "Discipline"
COMMODITY_LIST = "Commodity"
UNIT_LIST = "UnitOfMeasure"

MSG_CWA_RETIRED = "a retired area takes no new package"
MSG_FROZEN = "the fields of a package are frozen from release; return it to change them"
MSG_STALE = "the package changed since it was read; read it again"
MSG_NOTHING = "the request changes nothing"
MSG_NODE_UNKNOWN = "a WBS node of the list does not exist in the project"
MSG_NODE_RETIRED = "a retired WBS node takes no new allocation"
MSG_NODE_LEAF = "only a leaf WBS node takes a package allocation"
MSG_NO_AREA = "a package needs an area to be released"
MSG_NO_HOURS = "a package needs budget hours above zero to be released"
MSG_NO_DATES = "a package needs a planned start and a planned finish to be released"
MSG_NO_ALLOCATION = "the allocation of a package must sum to 100.00 to be released"
RELINK_REASON = "the area or the WBS allocation of the package changed"

_CWP_SQL = text(
    "SELECT t.cwa_id, t.discipline, t.planned_start, t.planned_finish, t.budget_hours, "
    f"t.quantities_json, t.contractor_text FROM {CWP_TABLE} t WHERE t.id = :id"
)
_ALLOCATIONS_SQL = text(
    "SELECT a.wbs_node_id, a.percent, w.code FROM "
    f"{CWP_ALLOCATION_TABLE} a JOIN {WBS_NODE_TABLE} w ON w.id = a.wbs_node_id "
    "WHERE a.cwp_id = :id ORDER BY w.code"
)
_NODE_RETIRED_SQL = text(f"SELECT retired FROM {WBS_NODE_TABLE} WHERE id = :id")
_NODE_CHILD_SQL = text(f"SELECT 1 FROM {WBS_NODE_TABLE} WHERE parent_id = :id LIMIT 1")


@dataclass(frozen=True)
class Cwp:
    """A package as the handlers read it: the envelope, the typed row and the workflow state."""

    id: str
    key: str
    title: str
    version: int
    state: str
    discipline: str
    cwa_id: str | None
    planned_start: str | None
    planned_finish: str | None
    budget_hours: str | None
    quantities: list[dict[str, str]] | None
    contractor_text: str | None


@dataclass(frozen=True)
class Allocation:
    wbs_node_id: str
    wbs_code: str
    percent: str


def load_cwp(uow: UnitOfWork, scope: str, cwp_id: str) -> Cwp:
    """The package ``cwp_id``; ``RecordNotFoundError`` (the same words) when it is hidden, absent,
    in another project, void or not a package."""
    ref = load_record(uow, scope, cwp_id, CWP)
    conn = uow.conn()
    row = conn.execute(_CWP_SQL, {"id": ref.id}).first()
    if row is None:
        raise LookupError(f"no {CWP_TABLE} row for {ref.id}")
    quantities = None if row.quantities_json is None else json.loads(row.quantities_json)
    return Cwp(
        id=ref.id,
        key=ref.key or "",
        title=ref.title,
        version=version_of(uow, ref.id),
        state=package_state(conn, ref.id),
        discipline=str(row.discipline),
        cwa_id=None if row.cwa_id is None else str(row.cwa_id),
        planned_start=None if row.planned_start is None else str(row.planned_start),
        planned_finish=None if row.planned_finish is None else str(row.planned_finish),
        budget_hours=None if row.budget_hours is None else str(row.budget_hours),
        quantities=as_rows(quantities),
        contractor_text=None if row.contractor_text is None else str(row.contractor_text),
    )


def allocations_of(conn: Connection, cwp_id: str) -> list[Allocation]:
    return [
        Allocation(str(r.wbs_node_id), str(r.code), str(r.percent))
        for r in conn.execute(_ALLOCATIONS_SQL, {"id": cwp_id})
    ]


def _require_state(cwp: Cwp, command: str) -> None:
    """The package is in a state ``command`` takes (``actions.RULES``)."""
    if cwp.state in states_for(command, CWP):
        return
    if command in ("ReviseCwp", "AllocateCwpToWbs") and cwp.state not in EDITABLE_STATES:
        raise CwpStateError(MSG_FROZEN)
    raise CwpStateError(f"a package that is {cwp.state} does not take {command}")


def _check_period(start: str | None, finish: str | None) -> None:
    try:
        check_period(start, finish)
    except ValueError as exc:
        raise CwpRuleError(str(exc)) from None


def _check_quantities(
    conn: Connection, scope: str, rows: list[dict[str, str]] | None
) -> list[dict[str, str]] | None:
    """Rows with a usable commodity and unit; ``None`` stays ``None``."""
    if rows is None:
        return None
    try:
        checked = check_quantity_rows(rows)
    except ValueError as exc:
        raise CwpRuleError(str(exc)) from None
    for row in checked:
        require_list_code(conn, scope, COMMODITY_LIST, row["commodity"], "a commodity")
        require_list_code(conn, scope, UNIT_LIST, row["uom"], "a unit of measure")
    return checked


def _live_area(conn: Connection, scope: str, code: str) -> str:
    """The id of the area with ``code``; refused when it is retired."""
    cwa_id = require_code(conn, scope, CWA, code, "area")
    area = get_cwa(conn, cwa_id)
    if area is None or area.retired:
        raise RetiredError(MSG_CWA_RETIRED)
    return cwa_id


def _quantity_payload(rows: list[Any] | None) -> list[dict[str, str]] | None:
    if rows is None:
        return None
    return [{"commodity": r.commodity, "qty": r.qty, "uom": r.uom} for r in rows]


def _move(
    uow: UnitOfWork, cmd: Any, cwp_id: str, transition: str, reason: str | None = None
) -> CommandResult:
    """Run workflow transition ``transition`` as the module."""
    return handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            stream_id=cwp_id,
            expected_version=version_of(uow, cwp_id),
            transition=transition,
            reason=reason,
        ),
        by_module=True,
    )


def handle_create_cwp(uow: UnitOfWork, cmd: CreateCwp) -> CommandResult:
    """Create a package: ``Numbering.Allocated``, ``Record.Created``, ``CWP.Defined`` and the
    ``belongs_to`` link to its area. Raises ``CodeNotFoundError`` (the area), ``RetiredError``,
    ``UnknownListCodeError`` (discipline, commodity, unit), ``CwpRuleError``."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    cwa_id = _live_area(conn, cmd.scope, cmd.cwa_code)
    require_list_code(conn, cmd.scope, DISCIPLINE_LIST, cmd.discipline, "the discipline")
    _check_period(cmd.planned_start, cmd.planned_finish)
    rows = _check_quantities(conn, cmd.scope, _quantity_payload(cmd.quantities))
    made = create_module_record(
        uow,
        cmd,
        record_type=CWP,
        title=cmd.title,
        key=None,
        numbering={"discipline": cmd.discipline},
        extra_events=[
            NewEvent(
                event_type=CWP_DEFINED,
                payload={
                    "discipline": cmd.discipline,
                    "cwa_id": cwa_id,
                    "planned_start": cmd.planned_start,
                    "planned_finish": cmd.planned_finish,
                    "budget_hours": cmd.budget_hours,
                    "quantities": rows,
                    "contractor_text": cmd.contractor_text,
                },
            )
        ],
    )
    events = list(made.events)
    events.extend(sync_links(uow, cmd, made.stream_id, BELONGS_RELATION, {cwa_id}, RELINK_REASON))
    if cmd.budget_hours is not None:
        rollup.request(uow, cmd.scope)
    return CommandResult(
        stream_id=made.stream_id, key=made.key, version=made.version, events=events
    )


def handle_revise_cwp(uow: UnitOfWork, cmd: ReviseCwp) -> CommandResult:
    """Change the fields of a package that is Planned or In development.

    A new title also appends ``Record.Updated`` (never the generic ``UpdateRecord``). Raises
    ``RecordNotFoundError``, ``CwpStateError`` (frozen), ``CwpRuleError``, ``RetiredError``,
    ``UnknownListCodeError``, ``NoChangesError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    cwp = load_cwp(uow, cmd.scope, cmd.cwp)
    _require_state(cwp, "ReviseCwp")
    given = cmd.model_fields_set
    changes: dict[str, list[Any]] = {}
    events: list[NewEvent] = []
    if cmd.title is not None and cmd.title != cwp.title:
        changes["title"] = [cwp.title, cmd.title]
        events.append(
            NewEvent(
                event_type="Record.Updated", payload={"changes": {"title": [cwp.title, cmd.title]}}
            )
        )
    cwa_id = cwp.cwa_id
    if cmd.cwa_code is not None:
        found = _live_area(conn, cmd.scope, cmd.cwa_code)
        if found != cwp.cwa_id:
            changes["cwa_id"] = [cwp.cwa_id, found]
            cwa_id = found
    new: dict[str, Any] = {
        "planned_start": cwp.planned_start,
        "planned_finish": cwp.planned_finish,
        "budget_hours": cwp.budget_hours,
        "contractor_text": cwp.contractor_text,
    }
    for name in new:
        if name in given and getattr(cmd, name) != new[name]:
            changes[name] = [new[name], getattr(cmd, name)]
            new[name] = getattr(cmd, name)
    if "quantities" in given:
        rows = _check_quantities(conn, cmd.scope, _quantity_payload(cmd.quantities))
        if rows != cwp.quantities:
            changes["quantities"] = [cwp.quantities, rows]
    if not changes:
        raise NoChangesError(MSG_NOTHING)
    _check_period(new["planned_start"], new["planned_finish"])
    events.append(NewEvent(event_type=CWP_REVISED, payload={"changes": changes}))
    made = append(uow, cmd, cwp.id, CWP, events)
    result = list(made.events)
    if "cwa_id" in changes:
        wanted = {a.wbs_node_id for a in allocations_of(conn, cwp.id)}
        if cwa_id is not None:
            wanted.add(cwa_id)
        result.extend(sync_links(uow, cmd, cwp.id, BELONGS_RELATION, wanted, RELINK_REASON))
    if "budget_hours" in changes:
        rollup.request(uow, cmd.scope)
    return CommandResult(stream_id=cwp.id, key=cwp.key, version=made.new_version, events=result)


def _node_for_allocation(conn: Connection, scope: str, code: str) -> str:
    node_id = resolve_code(conn, scope, WBS_NODE, code)
    if node_id is None:
        raise AllocationError(MSG_NODE_UNKNOWN)
    if bool(conn.execute(_NODE_RETIRED_SQL, {"id": node_id}).scalar_one()):
        raise RetiredError(MSG_NODE_RETIRED)
    if conn.execute(_NODE_CHILD_SQL, {"id": node_id}).first() is not None:
        raise WbsRuleError(MSG_NODE_LEAF)
    return node_id


def handle_allocate_cwp_to_wbs(uow: UnitOfWork, cmd: AllocateCwpToWbs) -> CommandResult:
    """Replace the allocation of a package to WBS leaf nodes (``CWP.AllocatedToWbs``, no card) and
    keep its ``belongs_to`` links in step. Raises ``RecordNotFoundError``, ``CwpStateError``,
    ``AllocationError``, ``RetiredError``, ``WbsRuleError``, ``NoChangesError``."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    cwp = load_cwp(uow, cmd.scope, cmd.cwp)
    _require_state(cwp, "AllocateCwpToWbs")
    lines = check_allocations([(line.wbs_code, line.percent) for line in cmd.allocations])
    allocations: list[dict[str, str]] = []
    for code, percent in sorted(lines, key=lambda line: line[0]):
        node_id = _node_for_allocation(conn, cmd.scope, code)
        allocations.append(
            {"wbs_node_id": node_id, "wbs_code": code, "percent": percent_text(percent)}
        )
    held = [
        {"wbs_node_id": a.wbs_node_id, "wbs_code": a.wbs_code, "percent": a.percent}
        for a in allocations_of(conn, cwp.id)
    ]
    if held == allocations:
        raise NoChangesError(MSG_NOTHING)
    made = append(
        uow,
        cmd,
        cwp.id,
        CWP,
        [NewEvent(event_type=CWP_ALLOCATED, payload=silent({"allocations": allocations}))],
    )
    wanted = {a["wbs_node_id"] for a in allocations}
    if cwp.cwa_id is not None:
        wanted.add(cwp.cwa_id)
    events = list(made.events)
    events.extend(sync_links(uow, cmd, cwp.id, BELONGS_RELATION, wanted, RELINK_REASON))
    rollup.request(uow, cmd.scope)
    return CommandResult(stream_id=cwp.id, key=cwp.key, version=made.new_version, events=events)


def _simple_move(
    uow: UnitOfWork, cmd: Any, command: str, transition: str, reason: str | None = None
) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    cwp = load_cwp(uow, cmd.scope, cmd.cwp)
    _require_state(cwp, command)
    moved = _move(uow, cmd, cwp.id, transition, reason)
    return CommandResult(stream_id=cwp.id, key=cwp.key, version=moved.version, events=moved.events)


def handle_start_cwp_development(uow: UnitOfWork, cmd: StartCwpDevelopment) -> CommandResult:
    """Planned to In development (``Workflow.Transitioned``)."""
    return _simple_move(uow, cmd, "StartCwpDevelopment", "start_development")


def handle_start_cwp_execution(uow: UnitOfWork, cmd: StartCwpExecution) -> CommandResult:
    """Released for IWP development to Executing."""
    return _simple_move(uow, cmd, "StartCwpExecution", "start_execution")


def handle_complete_cwp(uow: UnitOfWork, cmd: CompleteCwp) -> CommandResult:
    """Executing to Complete."""
    return _simple_move(uow, cmd, "CompleteCwp", "complete")


def handle_close_cwp(uow: UnitOfWork, cmd: CloseCwp) -> CommandResult:
    """Complete to Closed."""
    return _simple_move(uow, cmd, "CloseCwp", "close")


def handle_return_cwp(uow: UnitOfWork, cmd: ReturnCwp) -> CommandResult:
    """Released for IWP development back to In development; the reason is the transition's note."""
    return _simple_move(uow, cmd, "ReturnCwp", "return", cmd.reason)


def handle_reopen_cwp(uow: UnitOfWork, cmd: ReopenCwp) -> CommandResult:
    """Complete back to Executing."""
    return _simple_move(uow, cmd, "ReopenCwp", "reopen", cmd.reason)


def record_hash(cwp: Cwp, allocations: list[Allocation]) -> str:
    """SHA-256 (hex) of the package as released: its number, title, fields and allocation."""
    body = {
        "number": cwp.key,
        "title": cwp.title,
        "discipline": cwp.discipline,
        "cwa_id": cwp.cwa_id,
        "planned_start": cwp.planned_start,
        "planned_finish": cwp.planned_finish,
        "budget_hours": cwp.budget_hours,
        "quantities": cwp.quantities,
        "contractor_text": cwp.contractor_text,
        "allocations": [{"wbs_node_id": a.wbs_node_id, "percent": a.percent} for a in allocations],
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def release_problems(cwp: Cwp, allocations: list[Allocation]) -> list[str]:
    """The preconditions of a release the package does not meet (fixed messages)."""
    problems: list[str] = []
    if cwp.cwa_id is None:
        problems.append(MSG_NO_AREA)
    if cwp.budget_hours is None or Decimal(cwp.budget_hours) <= 0:
        problems.append(MSG_NO_HOURS)
    if cwp.planned_start is None or cwp.planned_finish is None:
        problems.append(MSG_NO_DATES)
    if sum((Decimal(a.percent) for a in allocations), Decimal("0.00")) != HUNDRED:
        problems.append(MSG_NO_ALLOCATION)
    return problems


def handle_release_cwp(uow: UnitOfWork, cmd: ReleaseCwp) -> CommandResult:
    """Release a package for IWP development: ``CWP.Released`` {by, record_hash}, then
    ``Workflow.Transitioned``. A missing ``awp.EWPRef`` link is reported by the workflow as an
    expected link that is missing; it never refuses. Raises ``RecordNotFoundError``,
    ``CwpStateError``, ``StaleVersionError`` (``expected_version`` is not the package's version),
    ``ReleaseRefusedError`` (an area, budget hours above zero, both dates, allocations summing to
    100.00)."""
    require_project(cmd)
    cmd = correlated(cmd)
    cwp = load_cwp(uow, cmd.scope, cmd.cwp)
    _require_state(cwp, "ReleaseCwp")
    if cmd.expected_version != cwp.version:
        raise StaleVersionError(MSG_STALE)
    allocations = allocations_of(uow.conn(), cwp.id)
    problems = release_problems(cwp, allocations)
    if problems:
        raise ReleaseRefusedError("; ".join(problems))
    released = append(
        uow,
        cmd,
        cwp.id,
        CWP,
        [
            NewEvent(
                event_type=CWP_RELEASED,
                payload={"by": cmd.actor, "record_hash": record_hash(cwp, allocations)},
            )
        ],
    )
    moved = _move(uow, cmd, cwp.id, "release")
    return CommandResult(
        stream_id=cwp.id,
        key=cwp.key,
        version=moved.version,
        events=[*released.events, *moved.events],
    )


def handle_void_cwp(uow: UnitOfWork, cmd: VoidCwp) -> CommandResult:
    """Void a package that is not Closed: ``Workflow.Transitioned`` to Void, ``Record.Voided``,
    and a rollup request (its budget no longer counts)."""
    require_project(cmd)
    cmd = correlated(cmd)
    cwp = load_cwp(uow, cmd.scope, cmd.id)
    _require_state(cwp, "VoidCwp")
    moved = _move(uow, cmd, cwp.id, "void", cmd.reason)
    voided = append(
        uow,
        cmd,
        cwp.id,
        CWP,
        [NewEvent(event_type="Record.Voided", payload={"reason": cmd.reason})],
    )
    rollup.request(uow, cmd.scope)
    return CommandResult(
        stream_id=cwp.id,
        key=cwp.key,
        version=voided.new_version,
        events=[*moved.events, *voided.events],
    )


def handle_request_rollup(uow: UnitOfWork, cmd: RequestRollup) -> CommandResult:
    """Queue the budget rollup of the project (no event; a job row). Idempotent."""
    require_project(cmd)
    rollup.request(uow, cmd.scope)
    return CommandResult(stream_id=rollup.job_id(cmd.scope), key=None, version=0, events=[])


__all__ = [
    "Allocation",
    "Cwp",
    "allocations_of",
    "handle_allocate_cwp_to_wbs",
    "handle_close_cwp",
    "handle_complete_cwp",
    "handle_create_cwp",
    "handle_release_cwp",
    "handle_reopen_cwp",
    "handle_request_rollup",
    "handle_return_cwp",
    "handle_revise_cwp",
    "handle_start_cwp_development",
    "handle_start_cwp_execution",
    "handle_void_cwp",
    "load_cwp",
    "record_hash",
    "release_problems",
]
