"""The reads other modules use, and the rule that a requisition inherits its subject's class."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from req_world import IWP, LABOR, SCOPE, World
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_mod_requisitions import api
from tl_mod_requisitions.names import LABOR_TABLE

CLEARED = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")


def read(world: World, function, *args, **kw):  # type: ignore[no-untyped-def]
    with open_uow(world.db, readonly=True) as uow:
        return function(uow.conn(), *args, **kw)


def hide(world: World, requisition: str) -> str:
    """Point the requisition at a restricted record (a projection write: an IWP is not confidential
    today, and the rule is generic in the subject); returns the subject's id."""
    subject = world.hidden_record()
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text(f"UPDATE {LABOR_TABLE} SET for_record_id = :s WHERE id = :i"),
            {"s": subject, "i": requisition},
        )
    return subject


def test_open_requisitions_are_the_non_final_ones_of_the_record(world: World) -> None:
    iwp = world.record(IWP, "IWP-1")
    other = world.record(IWP, "IWP-2")
    ids = [
        str(world.call("uma", "RaiseRequisition", requisition=LABOR, for_record_id=iwp).stream_id)
        for _ in range(3)
    ]
    world.call("uma", "RaiseRequisition", requisition=LABOR, for_record_id=other)
    world.call(
        "uma",
        "RaiseRequisition",
        requisition={"kind": "general", "subject": "Lift", "general_type": "other"},
        for_record_id=iwp,
    )
    world.call(
        "sue",
        "RejectRequisition",
        requisition=ids[0],
        expected_version=world.version(ids[0]),
        reason="No",
    )
    world.call(
        "uma",
        "CancelRequisition",
        requisition=ids[1],
        expected_version=world.version(ids[1]),
        reason="No",
    )
    found = read(world, api.open_requisitions_for, iwp)
    assert [r.kind for r in found] == ["general", "labor"] and found[1].id == ids[2]
    assert found[1].state == "Requested" and found[1].requester == "user:uma"
    assert [r.kind for r in read(world, api.open_requisitions_for, iwp, kinds=["general"])] == [
        "general"
    ]
    with pytest.raises(ValueError):
        read(world, api.open_requisitions_for, iwp, kinds=["nope"])
    world.call(
        "sue", "ApproveRequisition", requisition=ids[2], expected_version=world.version(ids[2])
    )
    assert read(world, api.open_requisitions_for, iwp)[1].state == "Approved"  # still open


def test_the_answer_is_bounded(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    iwp = world.record(IWP, "IWP-1")
    monkeypatch.setattr(api, "MAX_ROWS", 2)
    for _ in range(3):
        world.call("uma", "RaiseRequisition", requisition=LABOR, for_record_id=iwp)
    with pytest.raises(ValueError, match="more than 500"):
        read(world, api.open_requisitions_for, iwp)


def test_the_work_order_of_a_requisition(world: World) -> None:
    rid = world.raise_labor()
    assert read(world, api.work_order_for, rid) is None
    world.call("sue", "ApproveRequisition", requisition=rid, expected_version=world.version(rid))
    found = read(world, api.work_order_for, rid)
    assert found is not None and found.state == "Open" and found.requisition_id == rid
    assert found.key == "P123-WO-0001" and found.assigned_to is None


def test_a_requisition_of_a_hidden_subject_is_hidden_whole(world: World) -> None:
    rid, wid = world.approved()
    subject = hide(world, rid)
    assert read(world, api.open_requisitions_for, subject) == []
    assert read(world, api.work_order_for, rid) is None
    cleared = read(world, api.open_requisitions_for, subject, viewer=CLEARED)
    assert [r.id for r in cleared] == [rid]
    wo = read(world, api.work_order_for, rid, viewer=CLEARED)
    assert wo is not None and wo.id == wid
    with open_uow(world.db, readonly=True) as uow:
        assert cf.is_hidden(uow.conn(), rid, cf.LOWEST) and cf.is_hidden(uow.conn(), wid, cf.LOWEST)
        assert not cf.is_hidden(uow.conn(), rid, CLEARED) and not cf.is_hidden(
            uow.conn(), wid, CLEARED
        )


def test_a_command_on_a_hidden_requisition_answers_as_a_missing_one(world: World) -> None:
    rid, wid = world.approved()
    hide(world, rid)
    for name, fields in (
        ("CancelRequisition", {"requisition": rid, "reason": "x"}),
        ("StartWorkOrder", {"work_order": wid}),
    ):
        with pytest.raises(RecordNotFoundError):
            world.call("sue", name, expected_version=1, **fields)


def test_a_null_subject_takes_the_record_own_class(world: World) -> None:
    rid = world.raise_labor()
    assert read(world, api.open_requisitions_for, "x") == []
    with open_uow(world.db, readonly=True) as uow:
        assert not cf.is_hidden(uow.conn(), rid, cf.LOWEST)


def test_twenty_requisitions_from_two_threads_are_numbered_without_a_gap(db: DbTarget) -> None:
    from req_world import World as W

    w = W(db)
    w.people()
    w.editions()
    start = threading.Barrier(2)

    def raise_ten(who: str) -> list[str]:
        start.wait()
        return [w.call(who, "RaiseRequisition", requisition=LABOR).key for _ in range(10)]

    with ThreadPoolExecutor(2) as pool:
        keys = [k for batch in pool.map(raise_ten, ["uma", "rob"]) for k in batch]
    assert sorted(keys) == [f"P123-REQ-LAB-{n:04d}" for n in range(1, 21)]
    assert SCOPE
