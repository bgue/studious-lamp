"""T04a: the read views over requisitions and work orders. State changes only through commands."""

from __future__ import annotations

import pytest
from req_world import IWP, SCOPE, World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_requisitions import views

CLEARED = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
GENERAL = {"kind": "general", "subject": "Crane lift", "general_type": "other"}


def read(world: World, function, *args, **kw):  # type: ignore[no-untyped-def]
    with open_uow(world.db, readonly=True) as uow:
        return function(uow.conn(), SCOPE, *args, **kw)


def seed(world: World) -> tuple[str, str]:
    """Two labour requisitions (the first approved) and one general one on an IWP."""
    iwp = world.record(IWP, "IWP-1")
    approved, _ = world.approved()
    world.raise_labor()
    world.call("uma", "RaiseRequisition", requisition=GENERAL, for_record_id=iwp)
    return approved, iwp


def test_the_list_is_by_key_and_filters_narrow_it(world: World) -> None:
    seed(world)
    rows = read(world, views.requisition_list)
    assert [r.key for r in rows] == sorted(r.key for r in rows) and len(rows) == 3
    assert {r.kind for r in rows} == {"labor", "general"}
    assert len(read(world, views.requisition_list, kind="general")) == 1
    assert [r.state for r in read(world, views.requisition_list, state="Requested")] == [
        "Requested",
        "Requested",
    ]
    assert read(world, views.requisition_list, requester="user:nobody") == []
    assert len(read(world, views.requisition_list, limit=2)) == 2


def test_the_list_filters_by_the_record_it_serves(world: World) -> None:
    _, iwp = seed(world)
    rows = read(world, views.requisition_list, for_record=iwp)
    assert [r.kind for r in rows] == ["general"]


def test_the_detail_carries_the_kind_fields_and_the_work_order(world: World) -> None:
    approved, _ = seed(world)
    key = world.rows("SELECT key FROM cur_core_record WHERE id = :i", i=approved)[0]["key"]
    detail = read(world, views.requisition_detail, key)
    assert detail is not None
    assert detail.row.id == approved and detail.row.state == "Approved"
    assert detail.fields["craft"] == "Pipefitter" and str(detail.fields["headcount"]) == "6"
    assert detail.work_order is not None and detail.work_order.state == "Open"
    wo = read(world, views.work_order_detail, detail.work_order.key)
    assert wo is not None
    assert wo.row.requisition_id == approved and wo.requisition_key == key


def test_a_missing_key_answers_none_for_both(world: World) -> None:
    seed(world)
    assert read(world, views.requisition_detail, "P123-REQ-LAB-9999") is None
    assert read(world, views.work_order_detail, "P123-WO-9999") is None


def test_the_work_order_list_follows_the_lifecycle(world: World) -> None:
    _, wid = world.scheduled()
    assert [w.state for w in read(world, views.work_order_list)] == ["Scheduled"]
    world.call(
        "sue",
        "AssignWorkOrder",
        work_order=wid,
        expected_version=world.version(wid),
        assigned_to="user:uma",
    )
    assert len(read(world, views.work_order_list, assigned_to="user:uma")) == 1
    assert read(world, views.work_order_list, state="Closed") == []


def test_every_read_takes_viewer_and_defaults_to_the_lowest(world: World) -> None:
    seed(world)
    for function in (views.requisition_list, views.work_order_list):
        assert len(read(world, function, viewer=CLEARED)) == len(read(world, function))
    with pytest.raises(TypeError):
        read(world, views.requisition_list, CLEARED)  # viewer is keyword-only
