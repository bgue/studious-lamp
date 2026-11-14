"""requisitions section: the requisitions and work orders of P200 (P2-SEED-T08).

24 requisitions through ``RaiseRequisition``: 7 labour, 8 material, 5 general, 4 scaffold. The
foremen and the project engineer raise them (``lhartmann``, ``cbrooks``, ``pnair``); the
administrator ``mokafor`` approves, rejects and cancels (the requester may not approve, and the
administrator holds every word). Each approval opens a work order; the work orders are then
driven through the schedule, assign, start, complete and close commands. Every command runs read
through its actor's own viewer (ADR-0016), on its own day through ``world.on(day)``.

The final states are fixed by position (``FINAL``): 10 Approved (each opens a work order), 4
Rejected, 3 Cancelled (one after approval), 7 Requested (3 of them overdue). The work orders
(``WORK``) end as 5 Open (two of them assigned), 2 Scheduled, 1 In progress, 1 Done with the
actual hours, 1 Closed, and 1 Cancelled with its approved requisition.

Without the materials section the eight material requisitions are not raised, and the section
says so in one line. Draws come from the section's own ``rng``; nothing reads the clock.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from tl_adapters.db import open_uow
from tl_core.confidentiality import use_viewer, viewer_for_actor
from tl_mod_requisitions.commands import (
    ApproveRequisition,
    AssignWorkOrder,
    CancelRequisition,
    CloseWorkOrder,
    CompleteWorkOrder,
    RaiseRequisition,
    RejectRequisition,
    ScheduleWorkOrder,
    StartWorkOrder,
)
from tl_mod_requisitions.handlers.requisitions import (
    handle_approve_requisition,
    handle_cancel_requisition,
    handle_raise_requisition,
    handle_reject_requisition,
)
from tl_mod_requisitions.handlers.work_orders import (
    handle_assign_work_order,
    handle_close_work_order,
    handle_complete_work_order,
    handle_schedule_work_order,
    handle_start_work_order,
)

from dev.seed.demo_project.awp import DISCIPLINES
from dev.seed.demo_project.core import ADMIN
from dev.seed.demo_project.materials import COST_CODES
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import PROJECT, TODAY, World, actor_of

RAISERS = ("lhartmann", "cbrooks", "pnair")  # raise; the requester may not approve their own
APPROVER = ADMIN  # approves, rejects, cancels, schedules, assigns and closes
FOREMEN = ("cbrooks", "pnair")  # start and complete the work
BASE = date(2026, 10, 5)  # the first day of the requisitions
KINDS: tuple[str, ...] = ("labor",) * 7 + ("material",) * 8 + ("general",) * 5 + ("scaffold",) * 4
#: The final state of each requisition, by position (0-6 labour, 7-14 material, 15-19 general,
#: 20-23 scaffold).
FINAL: tuple[str, ...] = (
    "Approved",
    "Approved",
    "Approved",
    "Requested",
    "Rejected",
    "Cancelled",
    "Approved",
    "Approved",
    "Approved",
    "Requested",
    "Rejected",
    "Requested",
    "Approved",
    "Cancelled",
    "Approved",
    "Approved",
    "Requested",
    "Rejected",
    "Requested",
    "Requested",
    "Approved",
    "Cancelled",
    "Requested",
    "Rejected",
)
SUBJECTS: tuple[str, ...] = (  # by position, the same order as FINAL
    "Pipefitters for the north pipe rack",
    "Welders for the hydrotest packages",
    "Electricians for the substation",
    "Civil labourers for the tank farm dyke",
    "Insulators for the reactor feed",
    "Riggers for the pipe rack steel",
    "Instrument technicians for the control loops",
    "Flanges and gaskets for the spool sets",
    "Pipe supports and clamps for the headers",
    "Cable tray and fittings for the cable route",
    "Valve set for the tank transfer",
    "Bolts and studs for the heat exchangers",
    "Insulation material for the steam lines",
    "Paint and coatings for the pipe rack",
    "Instrument tubing fittings for the loops",
    "Crane lift for the pipe rack steel",
    "Hot work support for the tie-in",
    "Lift of the reactor platform deck",
    "Crane lift for the substation roof",
    "Hot work support for the tank dyke",
    "Scaffold for the reactor feed tie-in",
    "Scaffold level 3 east face",
    "Scaffold for the tank farm dyke",
    "Scaffold for the substation roof",
)
CRAFTS = ("Pipefitter", "Welder", "Electrician", "Labourer", "Insulator", "Rigger", "Technician")
GENERAL_TYPES = ("crane_lift", "hot_work_support", "other", "crane_lift", "hot_work_support")
REJECT_REASON = "No budget left in this period; resubmit next month"
CANCEL_REASON = "Not needed; the scope moved to the next package"
CANCEL_REQUESTED_REASON = "Duplicate of another requisition"
NO_MATERIALS_NOTE = (
    "requisitions: no materials section (no project items); the eight material requisitions "
    "are not raised"
)
OVERDUE = (3, 9, 16)  # Requested, need-by before TODAY
REJECTED = (4, 10, 17, 23)
CANCELLED_REQUESTED = (5, 21)
#: The work order each approved requisition's order takes, by position. Position 13 is cancelled
#: after its approval, so its work order is Cancelled too.
WORK: dict[int, str] = {
    0: "Open",
    1: "Open",
    2: "Open",
    6: "Open",
    7: "Open",
    8: "Scheduled",
    12: "Scheduled",
    13: "Cancelled",
    14: "In progress",
    15: "Done",
    20: "Closed",
}
ASSIGNEE: dict[int, str] = {6: "cbrooks", 7: "pnair"}  # Open work orders with a named assignee
HOURS_ACTUAL = "38.5"


def _ids(world: World, record_type: str) -> list[str]:
    """The ids of every record of ``record_type`` in the project, in key order."""
    return [
        str(r["id"])
        for r in world.rows(
            "SELECT id FROM cur_core_record WHERE scope = :s AND type = :t ORDER BY key",
            s=PROJECT,
            t=record_type,
        )
    ]


def _cost_codes(world: World) -> dict[str, str]:
    """Cost code key to id, for the project's cost codes."""
    return {
        str(r["key"]): str(r["id"])
        for r in world.rows(
            "SELECT id, key FROM cur_core_record WHERE scope = :s AND type = 'cost.CostCode'",
            s=PROJECT,
        )
    }


def _at(offset: int) -> date:
    """The day ``offset`` days after BASE; never after TODAY."""
    day = BASE + timedelta(days=offset)
    assert day <= TODAY, f"{day} is after TODAY"
    return day


def _run(world: World, who: str, day: date, handler: Any, model: Any, **fields: Any) -> Any:
    """One command as ``who`` on ``day``, read through ``who``'s own viewer (ADR-0016)."""
    with open_uow(world.target, readonly=True) as uow:
        viewer = viewer_for_actor(uow.conn(), actor_of(who))
    with world.on(day), use_viewer(viewer):
        return world.run(handler, model, by=who, **fields)


def _work_order_of(world: World, requisition_id: str) -> str:
    """The id of the work order that the approval of ``requisition_id`` opened."""
    return str(
        world.scalar(
            "SELECT id FROM cur_requisitions_work_order WHERE requisition_id = :r",
            r=requisition_id,
        )
    )


def _awp_codes(codes: dict[str, str]) -> list[str]:
    """The ids of the awp section's cost codes (the erection and test code of each discipline)."""
    prefixes = {prefix for _title, prefix in DISCIPLINES.values()}
    return [codes[k] for k in sorted(codes) if k.split("-")[0] in prefixes]


def _body(
    rng: random.Random,
    index: int,
    kind: str,
    items: list[str],
    codes: list[str],
    need_by: date,
) -> dict[str, Any]:
    """The requisition body of the kind at ``index``: the kind's own fields and the common ones."""
    common: dict[str, Any] = {
        "subject": SUBJECTS[index],
        "need_by": need_by.isoformat(),
        "priority": "high" if index in OVERDUE else "normal",
    }
    if kind == "labor":
        return {
            **common,
            "kind": "labor",
            "craft": CRAFTS[index % len(CRAFTS)],
            "headcount": rng.randint(2, 12),
            "start_date": (need_by - timedelta(days=3)).isoformat(),
            "end_date": (need_by + timedelta(days=10)).isoformat(),
        }
    if kind == "material":
        picked = rng.sample(items, rng.randint(1, 3))
        return {
            **common,
            "kind": "material",
            "lines": [
                {
                    "item_id": item,
                    "qty": str(rng.randint(2, 40)),
                    "uom": "EA",
                    "cost_code_id": rng.choice(codes) if codes else None,
                }
                for item in picked
            ],
        }
    if kind == "general":
        return {**common, "kind": "general", "general_type": GENERAL_TYPES[index - 15]}
    return {
        **common,
        "kind": "scaffold",
        "purpose": "Access to the work face",
        "duration_days": rng.randint(5, 30),
        "elevation": "E",
        "gridline": "G-4",
        "length_m": "12.0",
        "width_m": "1.2",
        "height_m": "6.0",
        "load_class": "light",
    }


def build(world: World, rng: random.Random) -> None:
    items = _ids(world, "materials.ProjectItem")
    if not items:
        print(NO_MATERIALS_NOTE)
    pool = _ids(world, "awp.IWP") + _ids(world, "awp.CWP")
    codes = _cost_codes(world)
    awp_codes = _awp_codes(codes)
    material_codes = [codes[code] for code, _ in COST_CODES if code in codes]
    for index, state in enumerate(FINAL):
        kind = KINDS[index]
        if kind == "material" and not items:
            continue
        raiser = RAISERS[rng.randrange(len(RAISERS))]
        need_by = (
            TODAY - timedelta(days=rng.randint(2, 9))
            if index in OVERDUE
            else TODAY + timedelta(days=rng.randint(5, 40))
        )
        raised_off = rng.randint(20, 29) if state == "Requested" else rng.randint(0, 14)
        made = _run(
            world,
            raiser,
            _at(raised_off),
            handle_raise_requisition,
            RaiseRequisition,
            requisition=_body(rng, index, kind, items, material_codes, need_by),
            for_record_id=rng.choice(pool) if pool else None,
            cost_code_id=rng.choice(awp_codes) if awp_codes else None,
        )
        rid = str(made.stream_id)
        if state == "Requested":
            continue
        if index in CANCELLED_REQUESTED:
            _run(
                world,
                APPROVER,
                _at(raised_off + 2),
                handle_cancel_requisition,
                CancelRequisition,
                requisition=rid,
                expected_version=world.version(rid),
                reason=CANCEL_REQUESTED_REASON,
            )
            continue
        decision_off = raised_off + rng.randint(1, 4)
        if index in REJECTED:
            _run(
                world,
                APPROVER,
                _at(decision_off),
                handle_reject_requisition,
                RejectRequisition,
                requisition=rid,
                expected_version=world.version(rid),
                reason=REJECT_REASON,
            )
            continue
        assert index in WORK, f"position {index} is {state} but has no work order plan"
        _run(
            world,
            APPROVER,
            _at(decision_off),
            handle_approve_requisition,
            ApproveRequisition,
            requisition=rid,
            expected_version=world.version(rid),
        )
        _work(world, rng, index, rid, decision_off)


def _work(world: World, rng: random.Random, index: int, rid: str, decision_off: int) -> None:
    """Drive the work order that the approval of ``rid`` opened to its planned state."""
    wo = _work_order_of(world, rid)
    plan = WORK[index]
    if plan == "Cancelled":
        _run(
            world,
            APPROVER,
            _at(decision_off + 1),
            handle_cancel_requisition,
            CancelRequisition,
            requisition=rid,
            expected_version=world.version(rid),
            reason=CANCEL_REASON,
        )
        return
    if index in ASSIGNEE:
        _run(
            world,
            APPROVER,
            _at(decision_off + 1),
            handle_assign_work_order,
            AssignWorkOrder,
            work_order=wo,
            expected_version=world.version(wo),
            assigned_to=f"user:{ASSIGNEE[index]}",
        )
    if plan == "Open":
        return
    sched_off = decision_off + rng.randint(2, 4)
    _run(
        world,
        APPROVER,
        _at(sched_off),
        handle_schedule_work_order,
        ScheduleWorkOrder,
        work_order=wo,
        expected_version=world.version(wo),
        planned_start=_at(sched_off).isoformat(),
        planned_finish=(_at(sched_off) + timedelta(days=rng.randint(3, 8))).isoformat(),
        hours_planned=f"{rng.randint(20, 80)}.0",
    )
    if plan == "Scheduled":
        return
    foreman = FOREMEN[rng.randrange(len(FOREMEN))]
    _run(
        world,
        foreman,
        _at(sched_off + 3),
        handle_start_work_order,
        StartWorkOrder,
        work_order=wo,
        expected_version=world.version(wo),
    )
    if plan == "In progress":
        return
    _run(
        world,
        foreman,
        _at(sched_off + 6),
        handle_complete_work_order,
        CompleteWorkOrder,
        work_order=wo,
        expected_version=world.version(wo),
        hours_actual=HOURS_ACTUAL,
    )
    if plan == "Done":
        return
    _run(
        world,
        APPROVER,
        _at(sched_off + 7),
        handle_close_work_order,
        CloseWorkOrder,
        work_order=wo,
        expected_version=world.version(wo),
    )


register("requisitions", build, needs=("requisitions.LaborRequisition",))
