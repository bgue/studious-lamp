"""The ten requisition commands: raise, edit, approve, reject, cancel and the work order moves."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from req_world import CWP, IWP, LABOR, SCOPE, World
from tl_core.auth.errors import ForbiddenError
from tl_core.constraints.commands import ClearConstraint
from tl_core.intent import Intent, IntentInvalid, IntentToward
from tl_core.services.errors import RecordNotFoundError, ServiceError
from tl_core.util import new_ulid
from tl_mod_requisitions.errors import (
    RequisitionRuleError,
    RequisitionStateError,
    StaleVersionError,
)
from tl_mod_requisitions.guards import MSG_FINAL


def refuses(error: type[BaseException], world: World, who: str, name: str, **fields: object) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


# --- raise ---------------------------------------------------------------------------------------


def test_a_labour_requisition_is_raised_numbered_and_linked(world: World) -> None:
    iwp = world.record(IWP, "IWP-1")
    code = world.record("cost.CostCode", "CC-1", scope="company")
    made = world.call(
        "uma", "RaiseRequisition", requisition=LABOR, for_record_id=iwp, cost_code_id=code
    )
    assert made.key == "P123-REQ-LAB-0001"
    row = world.requisition(made.stream_id)
    assert row["requester"] == "user:uma" and row["for_record_id"] == iwp
    assert row["headcount"] == 6 and row["priority"] == "normal"
    links = world.rows("SELECT from_id, to_id, relation, source FROM cur_links ORDER BY relation")
    assert (iwp, made.stream_id, "requires", "rule") in {
        (r["from_id"], r["to_id"], r["relation"], r["source"]) for r in links
    }
    assert (made.stream_id, code, "references", "rule") in {
        (r["from_id"], r["to_id"], r["relation"], r["source"]) for r in links
    }


def test_the_requester_is_never_an_input(world: World) -> None:
    for fields in (
        {"requisition": {**LABOR, "requester": "user:sue"}},
        {"requisition": LABOR, "requester": "user:sue"},
    ):
        with pytest.raises(ValidationError):
            world.call("uma", "RaiseRequisition", **fields)


def test_each_kind_has_its_own_numbering_and_row(world: World) -> None:
    item = world.record("materials.ProjectItem", "ITEM-1")
    where = world.record("materials.InventoryLocation", "LOC-1")
    bodies = [
        {
            "kind": "material",
            "subject": "Pipe",
            "from_location_id": where,
            "lines": [{"item_id": item, "qty": "4", "uom": "EA"}],
        },
        {"kind": "general", "subject": "Lift the vessel", "general_type": "crane_lift"},
        {
            "kind": "scaffold",
            "subject": "Scaffold",
            "purpose": "Access\nto valve",
            "duration_days": 5,
        },
    ]
    keys = [world.call("uma", "RaiseRequisition", requisition=b).key for b in bodies]
    assert keys == ["P123-REQ-MAT-0001", "P123-REQ-GEN-0001", "P123-REQ-SCF-0001"]
    lines = world.rows("SELECT lines_json FROM cur_requisitions_material_requisition")[0]
    assert '"fulfilled_qty":"0"' in lines["lines_json"]


@pytest.mark.parametrize(
    "body",
    [
        {**LABOR, "end_date": "2026-11-01"},
        {**LABOR, "start_date": "2026-01-01", "end_date": "2027-01-03"},
        {**LABOR, "end_date": "2026-02-30"},
        {"kind": "general", "subject": "x", "general_type": "no_such_type"},
        {
            "kind": "material",
            "subject": "x",
            "lines": [{"item_id": "nope", "qty": "1", "uom": "EA"}],
        },
    ],
)
def test_a_body_that_breaks_a_rule_is_refused(world: World, body: dict[str, object]) -> None:
    with pytest.raises(RequisitionRuleError):
        world.call("uma", "RaiseRequisition", requisition=body)


def test_a_366_day_period_is_the_longest(world: World) -> None:
    body = {**LABOR, "start_date": "2026-01-01", "end_date": "2027-01-02"}
    assert world.call("uma", "RaiseRequisition", requisition=body).key


def test_a_hidden_subject_answers_as_an_unknown_one(world: World) -> None:
    hidden, absent = world.hidden_record(), new_ulid()
    texts = {
        refuses(
            RequisitionRuleError,
            world,
            "uma",
            "RaiseRequisition",
            requisition=LABOR,
            for_record_id=i,
        )
        for i in (hidden, absent, world.record("cost.CostCode", "CC-2", scope="company"))
    }
    assert len(texts) == 1
    assert world.record(CWP, "CWP-1")  # a work package is a subject too
    cwp = world.record(CWP, "CWP-2")
    assert world.call("uma", "RaiseRequisition", requisition=LABOR, for_record_id=cwp).key


# --- edit ----------------------------------------------------------------------------------------


def test_the_requester_or_an_approver_edits_while_requested(world: World) -> None:
    rid = world.raise_labor()
    world.call(
        "uma", "EditRequisition", requisition=rid, expected_version=world.version(rid), headcount=8
    )
    world.call(
        "sue",
        "EditRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        need_by="2026-11-09",
    )
    row = world.requisition(rid)
    assert (row["headcount"], row["need_by"]) == (8, "2026-11-09")
    text = refuses(
        ForbiddenError,
        world,
        "rob",
        "EditRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        headcount=9,
    )
    assert "requester or an approver" in text


def test_an_edit_needs_the_current_version_and_a_change(world: World) -> None:
    rid = world.raise_labor()
    v = world.version(rid)
    refuses(
        StaleVersionError,
        world,
        "uma",
        "EditRequisition",
        requisition=rid,
        expected_version=v + 1,
        headcount=2,
    )
    refuses(
        RequisitionRuleError,
        world,
        "uma",
        "EditRequisition",
        requisition=rid,
        expected_version=v,
        headcount=6,
    )
    refuses(
        RequisitionRuleError,
        world,
        "uma",
        "EditRequisition",
        requisition=rid,
        expected_version=v,
        craft=None,
    )
    refuses(
        RequisitionRuleError,
        world,
        "uma",
        "EditRequisition",
        requisition=rid,
        expected_version=v,
        purpose="x",
    )
    refuses(
        RequisitionRuleError,
        world,
        "uma",
        "EditRequisition",
        requisition=rid,
        expected_version=v,
        end_date="2026-10-01",
    )
    assert world.version(rid) == v


def test_an_edit_after_the_decision_is_refused(world: World) -> None:
    rid, _ = world.approved()
    text = refuses(
        RequisitionStateError,
        world,
        "uma",
        "EditRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        headcount=2,
    )
    assert "Approved" in text


# --- approve and reject --------------------------------------------------------------------------


def test_approval_opens_the_work_order_in_one_unit(world: World) -> None:
    rid = world.raise_labor()
    made = world.call(
        "sue", "ApproveRequisition", requisition=rid, expected_version=world.version(rid)
    )
    wid = world.work_order_of(rid)
    row = world.requisition(rid)
    assert world.state(rid) == "Approved" and row["approved_by"] == "user:sue"
    wo = world.row("requisitions.WorkOrder", wid)
    assert wo["requisition_id"] == rid and wo["work_kind"] == "labour"
    assert (
        world.rows("SELECT status, key FROM cur_core_record WHERE id = :i", i=wid)[0]["key"]
        == "P123-WO-0001"
    )
    assert {e.event_type for e in made.events} >= {"WorkOrder.Opened", "Requisition.Approved"}


def test_the_requester_may_not_approve_their_own_request(world: World) -> None:
    rid = world.raise_labor("sue")  # sue holds the word, and still may not
    text = refuses(
        ForbiddenError,
        world,
        "sue",
        "ApproveRequisition",
        requisition=rid,
        expected_version=world.version(rid),
    )
    assert "own" in text
    assert world.version(rid) == 2 and world.requisition(rid)["work_order_id"] is None


def test_a_plain_user_may_not_approve(world: World) -> None:
    rid = world.raise_labor()
    refuses(
        ForbiddenError,
        world,
        "rob",
        "ApproveRequisition",
        requisition=rid,
        expected_version=world.version(rid),
    )
    assert world.requisition(rid)["approved_by"] is None


def test_a_stale_version_refuses_the_approval(world: World) -> None:
    rid = world.raise_labor()
    refuses(
        StaleVersionError, world, "sue", "ApproveRequisition", requisition=rid, expected_version=5
    )


def test_reject_needs_a_reason_and_ends_the_request(world: World) -> None:
    rid = world.raise_labor()
    with pytest.raises(ValidationError):
        world.call("sue", "RejectRequisition", requisition=rid, expected_version=world.version(rid))
    with pytest.raises(ValidationError):
        world.call(
            "sue",
            "RejectRequisition",
            requisition=rid,
            expected_version=world.version(rid),
            reason="x" * 301,
        )
    world.call(
        "sue",
        "RejectRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        reason="Not needed",
    )
    assert (
        world.state(rid) == "Rejected" and world.requisition(rid)["reject_reason"] == "Not needed"
    )


def test_a_rejected_or_cancelled_record_takes_no_command(world: World) -> None:
    rid = world.raise_labor()
    world.call(
        "sue",
        "RejectRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        reason="No",
    )
    v = world.version(rid)
    texts = {
        refuses(
            RequisitionStateError, world, who, name, requisition=rid, expected_version=v, **extra
        )
        for who, name, extra in (
            ("uma", "EditRequisition", {"headcount": 2}),
            ("sue", "ApproveRequisition", {}),
            ("sue", "RejectRequisition", {"reason": "again"}),
            ("uma", "CancelRequisition", {"reason": "again"}),
        )
    }
    assert texts == {MSG_FINAL}
    other = world.raise_labor()
    world.call(
        "uma",
        "CancelRequisition",
        requisition=other,
        expected_version=world.version(other),
        reason="Plans changed",
    )
    assert (
        refuses(
            RequisitionStateError,
            world,
            "sue",
            "ApproveRequisition",
            requisition=other,
            expected_version=world.version(other),
        )
        == MSG_FINAL
    )


def test_a_hidden_id_answers_as_a_missing_one(world: World) -> None:
    hidden, absent = world.hidden_record(), new_ulid()
    texts = {
        refuses(
            RecordNotFoundError,
            world,
            "sue",
            "ApproveRequisition",
            requisition=i,
            expected_version=1,
        ).replace(i, "ID")
        for i in (hidden, absent)
    }
    assert len(texts) == 1


# --- cancel --------------------------------------------------------------------------------------


def test_cancel_is_for_the_requester_or_an_approver_and_takes_the_open_work_order(
    world: World,
) -> None:
    rid, wid = world.approved()
    refuses(
        ForbiddenError,
        world,
        "rob",
        "CancelRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        reason="no",
    )
    world.call(
        "uma",
        "CancelRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        reason="Plans changed",
    )
    assert (world.state(rid), world.state(wid)) == ("Cancelled", "Cancelled")
    pending = world.raise_labor()
    world.call(
        "sue",
        "CancelRequisition",
        requisition=pending,
        expected_version=world.version(pending),
        reason="Duplicate",
    )
    assert world.state(pending) == "Cancelled"


def test_a_scheduled_requisition_is_no_longer_cancelled(world: World) -> None:
    rid, _ = world.scheduled()
    assert "Scheduled" in refuses(
        RequisitionStateError,
        world,
        "uma",
        "CancelRequisition",
        requisition=rid,
        expected_version=world.version(rid),
        reason="late",
    )


# --- the work order ------------------------------------------------------------------------------


def test_approved_cannot_be_closed_directly(world: World) -> None:
    _, wid = world.approved()
    text = refuses(
        RequisitionStateError,
        world,
        "sue",
        "CloseWorkOrder",
        work_order=wid,
        expected_version=world.version(wid),
    )
    assert "Open" in text
    assert refuses(
        RequisitionStateError,
        world,
        "sue",
        "StartWorkOrder",
        work_order=wid,
        expected_version=world.version(wid),
    )


def test_the_work_order_walks_both_records_to_closed(world: World) -> None:
    rid, wid = world.approved()

    def step(name: str, **f: str) -> object:
        return world.call("sue", name, work_order=wid, expected_version=world.version(wid), **f)

    step("AssignWorkOrder", assigned_to="user:uma")
    step(
        "ScheduleWorkOrder",
        planned_start="2026-11-02",
        planned_finish="2026-11-13",
        hours_planned="480.0",
    )
    assert (world.state(rid), world.state(wid)) == ("Scheduled", "Scheduled")
    step("AssignWorkOrder", assigned_to="Crew B")
    step("StartWorkOrder", at="2026-10-05T08:00:00+00:00")
    assert (world.state(rid), world.state(wid)) == ("In progress", "In progress")
    step("CompleteWorkOrder", at="2026-10-14T16:00:00+00:00", hours_actual="470.5")
    assert (world.state(rid), world.state(wid)) == ("Done", "Done")
    step("CloseWorkOrder")
    assert (world.state(rid), world.state(wid)) == ("Closed", "Closed")
    wo = world.row("requisitions.WorkOrder", wid)
    assert (wo["assigned_to"], wo["actual_start"], wo["actual_finish"]) == (
        "Crew B",
        "2026-10-05",
        "2026-10-14",
    )
    assert (wo["hours_planned"], wo["hours_actual"], wo["planned_finish"]) == (
        "480.0",
        "470.5",
        "2026-11-13",
    )
    assert (
        refuses(
            RequisitionStateError,
            world,
            "sue",
            "AssignWorkOrder",
            work_order=wid,
            expected_version=world.version(wid),
            assigned_to="x",
        )
        == MSG_FINAL
    )


def test_schedule_rules(world: World) -> None:
    _, wid = world.approved()
    v = world.version(wid)
    refuses(
        RequisitionRuleError,
        world,
        "sue",
        "ScheduleWorkOrder",
        work_order=wid,
        expected_version=v,
        planned_start="2026-11-05",
        planned_finish="2026-11-04",
    )
    refuses(
        StaleVersionError,
        world,
        "sue",
        "ScheduleWorkOrder",
        work_order=wid,
        expected_version=v + 1,
        planned_start="2026-11-05",
        planned_finish="2026-11-06",
    )
    refuses(
        ForbiddenError,
        world,
        "uma",
        "ScheduleWorkOrder",
        work_order=wid,
        expected_version=v,
        planned_start="2026-11-05",
        planned_finish="2026-11-06",
    )
    assert world.state(wid) == "Open"


def test_start_time_is_never_in_the_future_and_complete_is_not_before_start(world: World) -> None:
    _, wid = world.scheduled()
    v = world.version(wid)
    refuses(
        RequisitionRuleError,
        world,
        "sue",
        "StartWorkOrder",
        work_order=wid,
        expected_version=v,
        at="2999-01-01T00:00:00+00:00",
    )
    with pytest.raises(ValidationError):
        world.call(
            "sue", "StartWorkOrder", work_order=wid, expected_version=v, at="2026-10-05T08:00:00"
        )
    world.call(
        "sue", "StartWorkOrder", work_order=wid, expected_version=v, at="2026-10-05T08:00:00+00:00"
    )
    refuses(
        RequisitionRuleError,
        world,
        "sue",
        "CompleteWorkOrder",
        work_order=wid,
        expected_version=world.version(wid),
        at="2026-10-04T08:00:00+00:00",
    )
    world.call(
        "sue", "CompleteWorkOrder", work_order=wid, expected_version=world.version(wid)
    )  # now
    assert world.row("requisitions.WorkOrder", wid)["actual_finish"] is not None


def test_a_blocking_constraint_refuses_the_start_until_cleared(world: World) -> None:
    rid, wid = world.scheduled()
    constraint = world.block(wid)
    text = refuses(
        ServiceError,
        world,
        "sue",
        "StartWorkOrder",
        work_order=wid,
        expected_version=world.version(wid),
    )
    assert "open blocking constraints" in text
    assert (world.state(wid), world.state(rid)) == ("Scheduled", "Scheduled")
    world.core_call(
        "sue",
        ClearConstraint(
            actor="user:sue", source="test", scope=SCOPE, constraint=constraint, reason="Delivered"
        ),
    )
    world.call("sue", "StartWorkOrder", work_order=wid, expected_version=world.version(wid))
    assert (world.state(wid), world.state(rid)) == ("In progress", "In progress")


def test_a_work_order_command_on_a_requisition_id_answers_as_missing(world: World) -> None:
    rid, _ = world.approved()
    with pytest.raises(RecordNotFoundError):
        world.call("sue", "StartWorkOrder", work_order=rid, expected_version=1)


# --- intent (ADR-0025) ---------------------------------------------------------------------------


def test_an_intent_sent_with_raise_and_approve_is_stored_and_a_bad_one_refuses(
    world: World,
) -> None:
    iwp = world.record(IWP, "IWP-9")
    why = Intent(
        why="Tie-ins start Monday", toward=IntentToward(target=iwp, condition="crew on site")
    )
    made = world.call("uma", "RaiseRequisition", requisition=LABOR, intent=why)
    stored = world.rows("SELECT intent FROM events WHERE event_type = 'Requisition.Raised'")
    assert "Tie-ins start Monday" in stored[0]["intent"] and iwp in stored[0]["intent"]
    world.call(
        "sue",
        "ApproveRequisition",
        requisition=made.stream_id,
        expected_version=world.version(made.stream_id),
        intent=Intent(why="Crew free"),
    )
    approved = world.rows("SELECT intent FROM events WHERE event_type = 'Requisition.Approved'")
    assert "Crew free" in approved[0]["intent"]
    before = world.rows("SELECT count(*) AS n FROM events")[0]["n"]
    with pytest.raises(IntentInvalid):
        world.call("uma", "RaiseRequisition", requisition=LABOR, intent=Intent(why="x" * 501))
    assert world.rows("SELECT count(*) AS n FROM events")[0]["n"] == before
