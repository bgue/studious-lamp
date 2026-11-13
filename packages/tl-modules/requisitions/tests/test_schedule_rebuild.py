"""The planned hours ScheduleWorkOrder writes ride on WorkOrder.Scheduled, so a rebuild keeps them.

The payload slot is in ``schema/modules/requisitions/events.yaml`` (WorkOrderScheduledPayload);
the projector reads it back from the ledger when the projections are rebuilt.
"""

from __future__ import annotations

from req_world import World
from tl_adapters.db import open_uow, rebuild_projections
from tl_mod_requisitions import api


def test_a_rebuild_keeps_the_planned_hours_the_schedule_wrote(world: World) -> None:
    rid, wid = world.approved()
    world.call(
        "sue",
        "ScheduleWorkOrder",
        work_order=wid,
        expected_version=world.version(wid),
        planned_start="2026-11-02",
        planned_finish="2026-11-13",
        hours_planned="480.0",
    )
    assert world.row("requisitions.WorkOrder", wid)["hours_planned"] == "480.0"
    payloads = world.rows(
        "SELECT payload FROM events WHERE stream_id = :s AND event_type = 'WorkOrder.Scheduled'",
        s=wid,
    )
    assert len(payloads) == 1 and "480.0" in str(payloads[0]["payload"])

    rebuild_projections(world.db)

    wo = world.row("requisitions.WorkOrder", wid)
    assert (wo["hours_planned"], wo["planned_start"], wo["planned_finish"]) == (
        "480.0",
        "2026-11-02",
        "2026-11-13",
    )
    assert world.state(wid) == "Scheduled"
    with open_uow(world.db, readonly=True) as uow:
        found = api.work_order_for(uow.conn(), rid)
    assert found is not None and found.hours_planned == "480.0"
