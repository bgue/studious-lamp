"""The six inspection commands: plan, schedule, record, verify, reinspect, cancel."""

from __future__ import annotations

from typing import Any

import pytest
from insp_world import IWP, QUESTIONS, InspWorld, answers
from pydantic import ValidationError
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality.commands import PlanInspection, RecordInspectionResult
from tl_mod_quality.errors import InspectionRuleError, InspectionStateError, StaleVersionError
from tl_mod_quality.guards import MSG_CANCELLED
from tl_mod_quality.handlers import inspection as handlers
from tl_mod_quality.handlers.inspection import (
    MSG_ANSWERS,
    MSG_CHAIN,
    MSG_NOT_REINSPECTABLE,
    MSG_SELF_VERIFY,
)

SCOPE = "project:P123"


def raises(error: type[BaseException], world: InspWorld, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


# --- plan --------------------------------------------------------------------------------------


def test_plan_makes_a_planned_inspection_numbered_per_project(insp: InspWorld) -> None:
    iwp = insp.record(IWP, "IWP-1")
    made = insp.call(
        "uma",
        "PlanInspection",
        title="Flange make-up",
        subject_id=iwp,
        point="hold",
        area="A1",
        planned_on="2026-12-01",
    )
    item = str(made.stream_id)
    assert made.key == "P123-INS-0001"
    assert insp.state_of(item, "Planned") == "Planned"
    row = insp.inspection_row(item)
    assert (row["subject_id"], row["for_iwp_id"], row["point"]) == (iwp, iwp, "hold")
    assert (row["area"], row["planned_on"], row["punch_count"]) == ("A1", "2026-12-01", 0)
    assert row["checklist_id"] is None and row["result"] is None
    actor = insp.scalar("SELECT actor FROM events WHERE stream_id = :i AND seq = (SELECT min(seq) "
                        "FROM events WHERE stream_id = :i)", i=item)  # fmt: skip
    assert actor == "user:uma"


def test_for_iwp_defaults_to_the_subject_and_may_name_another_record(insp: InspWorld) -> None:
    tag, iwp = insp.record("engineering.Tag", "TAG-1"), insp.record(IWP, "IWP-2")
    item = insp.plan(tag, for_iwp_id=iwp)
    assert (insp.inspection_row(item)["subject_id"], insp.inspection_row(item)["for_iwp_id"]) == (
        tag,
        iwp,
    )
    assert insp.inspection_row(insp.plan(tag))["for_iwp_id"] == tag


def test_planned_by_and_the_result_are_never_inputs() -> None:
    base: dict[str, Any] = {"actor": "user:uma", "source": "t", "scope": SCOPE}
    for extra in ({"planned_by": "user:x"}, {"result": "accept"}, {"state": "Done"}):
        with pytest.raises(ValidationError):
            PlanInspection(**base, title="x", subject_id="s", point="hold", **extra)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PlanInspection(**base, title="x", subject_id="s", point="spot")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        RecordInspectionResult(**base, inspection="i", answers=[], result="accept")  # type: ignore[call-arg]


def test_plan_refuses_a_hidden_a_missing_and_a_foreign_subject_with_one_text(
    insp: InspWorld,
) -> None:
    secret = insp.hidden_record()
    other = insp.record(IWP, "IWP-X", scope="project:P999")
    before = insp.count()
    texts = {
        raises(
            RecordNotFoundError,
            insp,
            "uma",
            "PlanInspection",
            title="t",
            point="hold",
            subject_id=s,
        )
        for s in (secret, "no-such-id", other)
    }
    assert texts == {"no record with that id"}
    assert raises(
        RecordNotFoundError, insp, "uma", "PlanInspection", title="t", point="hold",
        subject_id=insp.record(IWP, "IWP-3"), for_iwp_id=secret,
    ) == "no record with that id"  # fmt: skip
    assert insp.count() == before + 1  # only the IWP-3 record itself
    assert insp.rows("SELECT id FROM cur_quality_inspection") == []


def test_a_cleared_person_plans_against_a_restricted_subject(insp: InspWorld) -> None:
    secret = insp.hidden_record()
    item = insp.plan(secret, who="dora")
    assert insp.inspection_row(item)["subject_id"] == secret
    with pytest.raises(RecordNotFoundError, match="no record with that id"):
        insp.call(
            "uma", "ScheduleInspection", inspection=item, checklist=insp.checklist(),
            scheduled_for="2026-12-01", inspector="x",
        )  # fmt: skip


def test_a_subject_that_names_a_subject_is_planned_only_when_that_subject_names_none(
    insp: InspWorld,
) -> None:
    """Two hops from the inspection: subject, then the subject's subject; no third."""
    iwp = insp.record(IWP, "IWP-1")
    scaffold = insp.plan(iwp)  # an inspection names its subject
    # an inspection is a subject that names a subject (the IWP) that names none: allowed
    assert insp.inspection_row(insp.plan(scaffold))["subject_id"] == scaffold
    # an inspection of that inspection names a chain of three: refused
    second = insp.plan(scaffold)
    before = insp.count()
    assert (
        raises(
            InspectionRuleError,
            insp,
            "uma",
            "PlanInspection",
            title="t",
            point="hold",
            subject_id=second,
        )
        == MSG_CHAIN
    )
    assert insp.count() == before


# --- schedule ----------------------------------------------------------------------------------


def test_schedule_pins_the_version_of_a_published_checklist(insp: InspWorld) -> None:
    first = insp.checklist()
    item = insp.plan()
    insp.call("uma", "ScheduleInspection", inspection=item, checklist=first,
              scheduled_for="2026-12-01", inspector="M. Okafor")  # fmt: skip
    row = insp.inspection_row(item)
    assert (row["checklist_id"], row["checklist_version"]) == (first, 1)
    assert (row["scheduled_for"], row["inspector"]) == ("2026-12-01", "M. Okafor")
    assert insp.state_of(item, "Planned") == "Scheduled"
    # version 2 is published (version 1 retires); a reschedule from Scheduled re-pins to it
    second = str(insp.call("sue", "ReviseChecklist", checklist=first).stream_id)
    insp.call("sue", "PublishChecklist", checklist=second)
    insp.call("uma", "ScheduleInspection", inspection=item, checklist=second,
              scheduled_for="2026-12-05", inspector="J. Ng")  # fmt: skip
    row = insp.inspection_row(item)
    assert (row["checklist_id"], row["checklist_version"], row["inspector"]) == (second, 2, "J. Ng")


def test_schedule_needs_a_published_checklist_a_date_and_an_inspector(insp: InspWorld) -> None:
    item = insp.plan()
    draft = insp.checklist(publish=False)
    fields: dict[str, Any] = {"scheduled_for": "2026-12-01", "inspector": "M. Okafor"}
    message = raises(
        InspectionStateError,
        insp,
        "uma",
        "ScheduleInspection",
        inspection=item,
        checklist=draft,
        **fields,
    )
    assert message == "a checklist that is Draft cannot be scheduled; it needs Published"
    retired = insp.checklist()
    insp.call("sue", "RetireChecklist", checklist=retired)
    assert "Retired" in raises(
        InspectionStateError,
        insp,
        "uma",
        "ScheduleInspection",
        inspection=item,
        checklist=retired,
        **fields,
    )
    with pytest.raises(RecordNotFoundError):
        insp.call("uma", "ScheduleInspection", inspection=item, checklist=item, **fields)
    good = insp.checklist()
    for bad in ({"scheduled_for": "tomorrow"}, {"inspector": " "}, {"scheduled_for": "2026-13-40"}):
        with pytest.raises(ValidationError):
            insp.call(
                "uma", "ScheduleInspection", inspection=item, checklist=good, **{**fields, **bad}
            )
    assert insp.state_of(item, "Planned") == "Planned"


def test_only_planned_or_scheduled_can_be_scheduled(insp: InspWorld) -> None:
    item = insp.scheduled()
    insp.recorded(item, answers=answers())
    assert raises(
        InspectionStateError, insp, "uma", "ScheduleInspection", inspection=item,
        checklist=insp.checklist(), scheduled_for="2026-12-01", inspector="x",
    ) == (
        "an inspection that is Done does not take ScheduleInspection; "
        "it needs Planned or Scheduled"
    )  # fmt: skip


# --- record ------------------------------------------------------------------------------------


def test_record_needs_a_scheduled_inspection(insp: InspWorld) -> None:
    item = insp.plan()
    message = raises(
        InspectionStateError,
        insp,
        "rob",
        "RecordInspectionResult",
        inspection=item,
        answers=answers(),
    )
    assert (
        message
        == "an inspection that is Planned does not take RecordInspectionResult; it needs Scheduled"
    )
    assert insp.state_of(item, "Planned") == "Planned"


def test_an_accepted_result_raises_no_punch_item(insp: InspWorld) -> None:
    item = insp.scheduled()
    made = insp.recorded(item, answers=answers(), note="All good")
    row = insp.inspection_row(item)
    assert (row["result"], row["punch_count"], row["recorded_by"]) == ("accept", 0, "user:rob")
    assert (row["note"], insp.state_of(item, "Planned")) == ("All good", "Done")
    assert row["done_at"] is not None and made.key.startswith("P123-INS-")
    assert insp.punch_total() == 0


def test_a_rejected_result_raises_one_punch_item_per_failed_question_in_the_same_step(
    insp: InspWorld,
) -> None:
    iwp = insp.record(IWP, "IWP-1")
    item = insp.scheduled(iwp, point="hold", area="A1")
    before = insp.count()
    insp.recorded(item, answers=answers(q1="no", q2="no", q3=50, note="Gauge missing"))
    row = insp.inspection_row(item)
    assert (row["result"], row["punch_count"], insp.state_of(item, "Planned")) == (
        "reject",
        3,
        "Done",
    )
    items = insp.raised_by(item)
    assert [p["key"] for p in items] == ["P123-PUN-0001", "P123-PUN-0002", "P123-PUN-0003"]
    # category A for the failed required question on a hold point, else B
    assert [p["category"] for p in items] == ["A", "B", "B"]
    assert {p["source_id"] for p in items} == {iwp}
    assert {p["raised_by"] for p in items} == {"user:rob"} and {p["area"] for p in items} == {"A1"}
    assert items[0]["title"].startswith(
        f"{insp.rows('SELECT key FROM cur_core_record WHERE id=:i', i=item)[0]['key']} q1:"
    )
    description = insp.rows(
        "SELECT description FROM cur_core_record WHERE id = :i", i=items[0]["id"]
    )
    assert description == [{"description": "Gauge missing"}]
    assert insp.state_of(items[0]["id"], "Open") == "Open"
    assert insp.count() > before


def test_a_conditional_result_raises_category_b_and_a_non_hold_point_never_a(
    insp: InspWorld,
) -> None:
    held = insp.scheduled(point="hold")
    insp.recorded(held, answers=answers(q2="no"))
    assert insp.inspection_row(held)["result"] == "conditional"
    assert [p["category"] for p in insp.raised_by(held)] == ["B"]
    witnessed = insp.scheduled(point="witness")
    insp.recorded(witnessed, answers=answers(q1="no"))
    assert insp.inspection_row(witnessed)["result"] == "reject"
    assert [p["category"] for p in insp.raised_by(witnessed)] == ["B"]


def test_the_result_is_computed_from_the_answers_and_never_typed(insp: InspWorld) -> None:
    item = insp.scheduled()
    with pytest.raises(ValidationError):
        insp.call(
            "rob", "RecordInspectionResult", inspection=item, answers=answers(), result="accept"
        )
    insp.recorded(item, answers=answers(q1="no"))
    assert insp.inspection_row(item)["result"] == "reject"


def test_bad_answers_are_refused_with_the_problems_and_nothing_is_raised(insp: InspWorld) -> None:
    item = insp.scheduled()
    before = insp.count()
    for bad in (
        [],
        answers(q1="maybe"),
        [*answers(), {"q": "q9", "value": "yes"}],
        answers()[:1] * 2,
    ):
        message = raises(
            InspectionRuleError, insp, "rob", "RecordInspectionResult", inspection=item, answers=bad
        )
        assert message.startswith(MSG_ANSWERS)
    assert insp.count() == before and insp.punch_total() == 0
    assert insp.state_of(item, "Planned") == "Scheduled"


def test_a_failed_record_leaves_no_punch_item_behind(
    insp: InspWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = insp.scheduled()
    before = insp.count()

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(handlers, "move", fail)
    with pytest.raises(RuntimeError):
        insp.recorded(item, answers=answers(q1="no", q2="no"))
    assert insp.punch_total() == 0 and insp.count() == before
    assert insp.inspection_row(item)["result"] is None


def test_record_stale_version_and_valid_time(insp: InspWorld) -> None:
    item = insp.scheduled()
    stale = raises(StaleVersionError, insp, "rob", "RecordInspectionResult", inspection=item,
                   answers=answers(), expected_version=1)  # fmt: skip
    assert stale == "the record changed since it was read"
    with pytest.raises(ValidationError):
        RecordInspectionResult(actor="user:rob", source="t", scope=SCOPE, inspection=item,
                               answers=[], at="2026-12-01T09:00:00")  # type: ignore[arg-type]  # fmt: skip
    from datetime import UTC, datetime, timedelta

    future = datetime.now(UTC) + timedelta(days=2)
    assert raises(InspectionRuleError, insp, "rob", "RecordInspectionResult", inspection=item,
                  answers=answers(), at=future) == "the time is in the future"  # fmt: skip
    assert insp.state_of(item, "Planned") == "Scheduled"


def test_answers_are_bounded(insp: InspWorld) -> None:
    base: dict[str, Any] = {"actor": "user:rob", "source": "t", "scope": SCOPE, "inspection": "i"}
    with pytest.raises(ValidationError):
        RecordInspectionResult(**base, answers=[{"q": "q1", "value": "yes"}] * 61)
    with pytest.raises(ValidationError):
        RecordInspectionResult(**base, answers=[{"q": "q" * 17, "value": "yes"}])
    with pytest.raises(ValidationError):
        RecordInspectionResult(**base, answers=[{"q": "q1", "value": "x" * 5000}])
    with pytest.raises(ValidationError):
        RecordInspectionResult(**base, answers=[{"q": "q1", "value": "y", "note": "n\x00"}])
    ok = RecordInspectionResult(**base, answers=[{"q": "q1", "value": "yes"}])
    assert ok.answers == [{"note": None, "q": "q1", "value": "yes"}]


# --- verify ------------------------------------------------------------------------------------


def test_verify_takes_a_done_inspection_and_never_the_person_who_recorded_it(
    insp: InspWorld,
) -> None:
    item = insp.scheduled()
    assert "does not take VerifyInspection; it needs Done" in raises(
        InspectionStateError, insp, "sue", "VerifyInspection", inspection=item
    )
    insp.recorded(item, who="rob", answers=answers())
    assert (
        raises(ForbiddenError, insp, "rob", "VerifyInspection", inspection=item) == MSG_SELF_VERIFY
    )
    assert insp.state_of(item, "Planned") == "Done"
    with pytest.raises(ForbiddenError):
        insp.call("uma", "VerifyInspection", inspection=item)  # no controller word
    insp.call("sue", "VerifyInspection", inspection=item)
    row = insp.inspection_row(item)
    assert (row["verified_by"], insp.state_of(item, "Planned")) == ("user:sue", "Verified")
    assert row["verified_on"] is not None
    assert MSG_SELF_VERIFY == "the person who recorded an inspection may not verify it"


# --- reinspect ---------------------------------------------------------------------------------


def test_reinspect_plans_a_new_inspection_and_leaves_the_old_one_alone(insp: InspWorld) -> None:
    iwp = insp.record(IWP, "IWP-1")
    old = insp.scheduled(iwp, point="hold", area="A1")
    insp.recorded(old, answers=answers(q1="no"))
    before, version = insp.inspection_row(old), insp.version(old)
    made = insp.call("uma", "ReinspectInspection", inspection=old, planned_on="2026-12-08")
    new = str(made.stream_id)
    row = insp.inspection_row(new)
    assert (row["reinspection_of_id"], row["subject_id"], row["for_iwp_id"]) == (old, iwp, iwp)
    assert (row["point"], row["area"], row["planned_on"]) == ("hold", "A1", "2026-12-08")
    assert insp.state_of(new, "Planned") == "Planned" and row["checklist_id"] is None
    assert insp.inspection_row(old) == before and insp.version(old) == version
    assert insp.state_of(old, "Planned") == "Done"
    assert insp.rows("SELECT title FROM cur_core_record WHERE id = :i", i=new) == insp.rows(
        "SELECT title FROM cur_core_record WHERE id = :i", i=old
    )


def test_reinspect_takes_a_verified_conditional_one_and_refuses_an_accepted_one(
    insp: InspWorld,
) -> None:
    cond = insp.scheduled()
    insp.recorded(cond, answers=answers(q2="no"))
    insp.call("sue", "VerifyInspection", inspection=cond)
    assert (
        insp.inspection_row(
            str(insp.call("uma", "ReinspectInspection", inspection=cond).stream_id)
        )["reinspection_of_id"]
        == cond
    )
    accepted = insp.scheduled()
    insp.recorded(accepted, answers=answers())
    assert (
        raises(InspectionStateError, insp, "uma", "ReinspectInspection", inspection=accepted)
        == MSG_NOT_REINSPECTABLE
    )
    scheduled = insp.scheduled()
    assert "does not take ReinspectInspection; it needs Done or Verified" in raises(
        InspectionStateError, insp, "uma", "ReinspectInspection", inspection=scheduled
    )


# --- cancel ------------------------------------------------------------------------------------


def test_cancel_takes_planned_or_scheduled_with_a_reason_and_cancelled_accepts_nothing(
    insp: InspWorld,
) -> None:
    planned, scheduled = insp.plan(), insp.scheduled()
    for item in (planned, scheduled):
        insp.call("sue", "CancelInspection", inspection=item, reason="Work moved")
        assert insp.state_of(item, "Planned") == "Cancelled"
        assert insp.inspection_row(item)["cancel_reason"] == "Work moved"
        for who, name, extra in (
            ("sue", "CancelInspection", {"reason": "x"}),
            (
                "uma",
                "ScheduleInspection",
                {"checklist": insp.checklist(), "scheduled_for": "2026-12-01", "inspector": "x"},
            ),
            ("rob", "RecordInspectionResult", {"answers": answers()}),
            ("sue", "VerifyInspection", {}),
            ("uma", "ReinspectInspection", {}),
        ):
            assert (
                raises(InspectionStateError, insp, who, name, inspection=item, **extra)
                == MSG_CANCELLED
            )
    with pytest.raises(ForbiddenError):
        insp.call("uma", "CancelInspection", inspection=insp.plan(), reason="x")
    with pytest.raises(ValidationError):
        insp.call("sue", "CancelInspection", inspection=insp.plan(), reason="x" * 301)
    done = insp.scheduled()
    insp.recorded(done, answers=answers())
    assert "needs Planned or Scheduled" in raises(
        InspectionStateError, insp, "sue", "CancelInspection", inspection=done, reason="late"
    )


def test_every_questions_fixture_is_valid_for_the_world() -> None:
    assert len(QUESTIONS) == 3
