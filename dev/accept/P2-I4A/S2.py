"""Acceptance for P2-I4A-S2: requisitions engine commands. Exit 0, one ``PASS <check>`` line per
check, final ``S2 ok``. Expectations are written from the S2 piece spec. SQLite only.
Run: ``uv run python dev/accept/P2-I4A/S2.py``."""

from __future__ import annotations

import sys
import tempfile
import threading
import tomllib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/requisitions/tests"))
from req_world import IWP, LABOR, World  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import as_target, create_schema, open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.constraints.commands import ClearConstraint  # noqa: E402
from tl_core.intent import Intent, IntentInvalid  # noqa: E402
from tl_core.services.errors import ServiceError  # noqa: E402
from tl_core.util import new_ulid  # noqa: E402
from tl_mod_requisitions import api  # noqa: E402
from tl_mod_requisitions.errors import RequisitionStateError, StaleVersionError  # noqa: E402
from tl_mod_requisitions.module import PROPOSABLE, REQUISITIONS_COMMANDS  # noqa: E402

CLEARED = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
SCOPE = "project:P123"


def fresh() -> World:
    db = as_target(str(Path(tempfile.mkdtemp()) / "s2.db"))
    create_schema(db)
    world = World(db)
    world.people()
    world.editions()
    return world


def refused(error: type[BaseException], call: Callable[[], Any]) -> str:
    try:
        call()
    except error as exc:
        return str(exc)
    raise AssertionError(f"expected {error.__name__}")


def passed(name: str) -> None:
    print(f"PASS {name}")


def read(world: World, function: Callable[..., Any], *args: Any, **kw: Any) -> Any:
    with open_uow(world.db, readonly=True) as uow:
        return function(uow.conn(), *args, **kw)


def main() -> None:
    w = fresh()
    rid = w.raise_labor()
    w.call("sue", "ApproveRequisition", requisition=rid, expected_version=w.version(rid))
    wid = w.work_order_of(rid)
    assert w.state(rid) == "Approved" and w.state(wid) == "Open" and wid != "None"
    passed(
        "a labour requisition approved by an approver has a work order Open and work_order_id set"
    )

    own = w.raise_labor("sue")
    refused(
        ForbiddenError,
        lambda: w.call(
            "sue", "ApproveRequisition", requisition=own, expected_version=w.version(own)
        ),
    )
    assert w.requisition(own)["work_order_id"] is None
    passed("the requester approving their own request is refused")

    other = w.raise_labor()
    refused(
        ForbiddenError,
        lambda: w.call("rob", "ApproveRequisition", requisition=other, expected_version=2),
    )
    passed("a plain user approving is refused")

    refused(
        ValidationError,
        lambda: w.call("uma", "RaiseRequisition", requisition={**LABOR, "requester": "user:x"}),
    )
    passed("requester in the raise body is refused as an unknown field")

    refused(
        ValidationError,
        lambda: w.call("sue", "RejectRequisition", requisition=other, expected_version=2),
    )
    w.call("sue", "RejectRequisition", requisition=other, expected_version=2, reason="No need")
    assert w.state(other) == "Rejected"
    passed("reject needs a reason")

    refused(
        RequisitionStateError,
        lambda: w.call("sue", "CloseWorkOrder", work_order=wid, expected_version=w.version(wid)),
    )
    assert w.state(rid) == "Approved"
    passed("Approved -> Closed directly is refused")

    def step(name: str, **fields: Any) -> None:
        w.call("sue", name, work_order=wid, expected_version=w.version(wid), **fields)

    step("AssignWorkOrder", assigned_to="Crew A")
    step("ScheduleWorkOrder", planned_start="2026-10-01", planned_finish="2026-10-12")
    step("StartWorkOrder", at="2026-10-02T08:00:00+00:00")
    step("CompleteWorkOrder", at="2026-10-12T16:00:00+00:00", hours_actual="96.0")
    step("CloseWorkOrder")
    assert (w.state(rid), w.state(wid)) == ("Closed", "Closed")
    passed("schedule, assign, start, complete, close walk both records to Closed together")

    rid2, wid2 = w.scheduled()
    constraint = w.block(wid2)
    refused(
        ServiceError,
        lambda: w.call("sue", "StartWorkOrder", work_order=wid2, expected_version=w.version(wid2)),
    )
    w.core_call(
        "sue",
        ClearConstraint(
            actor="user:sue", source="test", scope=SCOPE, constraint=constraint, reason="Delivered"
        ),
    )
    w.call("sue", "StartWorkOrder", work_order=wid2, expected_version=w.version(wid2))
    assert w.state(rid2) == "In progress"
    passed("a blocking constraint refuses StartWorkOrder, clearing it allows it")

    fresh_req = w.raise_labor()
    refused(
        StaleVersionError,
        lambda: w.call(
            "uma",
            "EditRequisition",
            requisition=fresh_req,
            expected_version=w.version(fresh_req) - 1,
            headcount=2,
        ),
    )
    passed("a stale expected_version is refused")

    hidden, absent = w.hidden_record(), new_ulid()

    def raise_for(subject: str) -> Any:
        return lambda: w.call("uma", "RaiseRequisition", requisition=LABOR, for_record_id=subject)

    from tl_mod_requisitions.errors import RequisitionRuleError

    assert refused(RequisitionRuleError, raise_for(hidden)) == refused(
        RequisitionRuleError, raise_for(absent)
    )
    passed("a hidden record as for_record_id answers the same text as an unknown id")

    iwp = w.record(IWP, "IWP-1")
    mine = str(w.call("uma", "RaiseRequisition", requisition=LABOR, for_record_id=iwp).stream_id)
    w.call("sue", "ApproveRequisition", requisition=mine, expected_version=w.version(mine))
    subject = w.hidden_record()
    with open_uow(w.db) as uow:  # the subject becomes a record the lowest viewer cannot read
        uow.conn().execute(
            text("UPDATE cur_requisitions_labor_requisition SET for_record_id = :s WHERE id = :i"),
            {"s": subject, "i": mine},
        )
    assert read(w, api.open_requisitions_for, subject) == []
    assert read(w, api.work_order_for, mine) is None
    assert [r.id for r in read(w, api.open_requisitions_for, subject, viewer=CLEARED)] == [mine]
    assert read(w, api.work_order_for, mine, viewer=CLEARED) is not None
    passed(
        "a requisition of a hidden subject is absent for the default viewer, present when cleared"
    )

    made = w.call(
        "uma", "RaiseRequisition", requisition=LABOR, intent=Intent(why="Tie-ins start Monday")
    )
    w.call(
        "sue",
        "ApproveRequisition",
        requisition=made.stream_id,
        expected_version=w.version(made.stream_id),
        intent=Intent(why="Crew is free"),
    )
    stored = w.rows(
        "SELECT event_type, intent FROM events WHERE event_type IN "
        "('Requisition.Raised', 'Requisition.Approved') AND stream_id = :i",
        i=made.stream_id,
    )
    held = {r["event_type"]: r["intent"] for r in stored}
    assert "Tie-ins start Monday" in held["Requisition.Raised"]
    assert "Crew is free" in held["Requisition.Approved"]
    before = w.scalar("SELECT count(*) FROM events")
    refused(
        IntentInvalid,
        lambda: w.call("uma", "RaiseRequisition", requisition=LABOR, intent=Intent(why="x" * 501)),
    )
    assert w.scalar("SELECT count(*) FROM events") == before
    passed("an intent round-trips on raise and approve, and a bad intent refuses the command")

    threaded = fresh()
    gate = threading.Barrier(2)

    def raise_ten(who: str) -> list[str]:
        gate.wait()
        return [threaded.call(who, "RaiseRequisition", requisition=LABOR).key for _ in range(10)]

    with ThreadPoolExecutor(2) as pool:
        keys = [k for batch in pool.map(raise_ten, ["uma", "rob"]) for k in batch]
    assert sorted(keys) == [f"P123-REQ-LAB-{n:04d}" for n in range(1, 21)]
    passed("two threads raising 20 requisitions of one kind get -0001..-0020 with no gap or repeat")

    v = fresh()
    anchor = v.record(IWP, "IWP-9")
    ids = [
        str(v.call("uma", "RaiseRequisition", requisition=LABOR, for_record_id=anchor).stream_id)
        for _ in range(4)
    ]
    v.call(
        "sue",
        "RejectRequisition",
        requisition=ids[0],
        expected_version=v.version(ids[0]),
        reason="No",
    )
    v.call(
        "uma",
        "CancelRequisition",
        requisition=ids[1],
        expected_version=v.version(ids[1]),
        reason="No",
    )
    v.call("sue", "ApproveRequisition", requisition=ids[2], expected_version=v.version(ids[2]))
    assert {r.id for r in read(v, api.open_requisitions_for, anchor)} == {ids[2], ids[3]}
    passed("open_requisitions_for returns only non-terminal records")

    excluded = set(
        tomllib.loads((ROOT / "tests/tools/proposable_exclusions.toml").read_text())["commands"]
    )
    rows = {p.model.__name__ for p in PROPOSABLE}
    assert rows | excluded == {c.model.__name__ for c in REQUISITIONS_COMMANDS}
    passed("every command is a proposable row or an exclusion")
    print("S2 ok")


if __name__ == "__main__":
    main()
