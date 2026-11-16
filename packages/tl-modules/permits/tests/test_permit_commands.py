"""The ten permit commands: effects, state table, actors, guards, versions, numbering."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from permit_world import SCOPE, World
from pydantic import ValidationError
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_permits.commands import RequestPermit
from tl_mod_permits.errors import (
    PermitBlockedError,
    PermitRuleError,
    PermitScopeError,
    PermitStateError,
    StaleVersionError,
)
from tl_mod_permits.handlers.permit import (
    MSG_MAX_DAYS,
    MSG_NOT_PARTY,
    MSG_SELF_APPROVE,
    MSG_SELF_ISSUE,
    MSG_UNKNOWN_PRECAUTION,
    MSG_WINDOW_OVER,
)


def raises(error: type[BaseException], world: World, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def iso(value: Any) -> str:
    return str(value)[:19].replace(" ", "T")


# --- request -----------------------------------------------------------------------------------


def test_request_makes_a_requested_permit_numbered_per_project(world: World) -> None:
    iwp = world.record("awp.IWP", "IWP-1")
    made = world.call(
        "rob",
        "RequestPermit",
        permit_type="hot_work",
        for_record_id=iwp,
        area="A1",
        location_text="Pump room",
        work_description="Weld repair, rack 12\nlevel 2",
        holder="Rob",
        needed_from="2026-12-01",
        needed_until="2026-12-02",
    )
    assert made.key == "P123-PTW-0001"
    assert world.state(made.stream_id) == "Requested"
    row = world.row(made.stream_id)
    assert (row["permit_type"], row["for_record_id"], row["requested_by"], row["holder"]) == (
        "hot_work",
        iwp,
        "user:rob",
        "Rob",
    )
    assert row["needed_until"] == "2026-12-02" and row["valid_until"] is None
    assert world.call("rob", "RequestPermit", **_fields()).key == "P123-PTW-0002"


def test_request_for_a_hidden_missing_or_foreign_record_answers_one_text(world: World) -> None:
    secret = world.hidden_record()
    other = world.record("awp.IWP", "IWP-9", scope="project:P999")
    texts = {
        raises(RecordNotFoundError, world, "uma", "RequestPermit", **_fields(for_record_id=ref))
        for ref in (secret, "01JXXXXXXXXXXXXXXXXXXXXXXX", other)
    }
    assert texts == {"no record with that id"}
    assert world.count("cur_permits_permit") == 0


def _fields(**more: Any) -> dict[str, Any]:
    return {
        "permit_type": "general",
        "area": "A1",
        "location_text": "Pump room",
        "work_description": "Weld repair",
        "holder": "Rob",
        "needed_from": "2026-12-01",
        "needed_until": "2026-12-03",
        **more,
    }


def test_request_models_are_strict() -> None:
    base: dict[str, Any] = {"actor": "user:rob", "source": "t", "scope": SCOPE, **_fields()}
    RequestPermit(**base)
    for bad in (
        {"requested_by": "user:x"},
        {"needed_until": "2026-11-30"},
        {"needed_from": "2026-13-01"},
        {"permit_type": "welding"},
        {"area": "  "},
    ):
        with pytest.raises(ValidationError):
            RequestPermit(**{**base, **bad})


def test_request_needs_a_project_scope(world: World) -> None:
    from tl_adapters.db import open_uow
    from tl_mod_permits.handlers.permit import handle_request_permit

    cmd = RequestPermit(actor="user:rob", source="t", scope="company", **_fields())
    with open_uow(world.db) as uow, pytest.raises(PermitScopeError):
        handle_request_permit(uow, cmd)


# --- approve and reject --------------------------------------------------------------------------


def test_approve_by_a_controller_who_is_not_the_requester(world: World) -> None:
    permit = world.request()
    assert raises(ForbiddenError, world, "sue", "ApprovePermit", permit=world.request("sue")) == (
        MSG_SELF_APPROVE
    )
    world.call("sue", "ApprovePermit", permit=permit)
    assert world.state(permit) == "Approved"
    assert world.row(permit)["approved_by"] == "user:sue"


def test_a_requester_cannot_reject_either_and_reject_needs_a_reason(world: World) -> None:
    mine = world.request("sue")
    assert raises(ForbiddenError, world, "sue", "RejectPermit", permit=mine, reason="x") == (
        MSG_SELF_APPROVE
    )
    permit = world.request()
    with pytest.raises(ValidationError):
        world.call("sue", "RejectPermit", permit=permit)
    world.call("sue", "RejectPermit", permit=permit, reason="Not this week")
    assert world.state(permit) == "Rejected"
    assert world.row(permit)["reject_reason"] == "Not this week"


def test_a_plain_user_cannot_approve(world: World) -> None:
    from tl_core.auth.errors import ForbiddenError as Denied

    with pytest.raises(Denied):
        world.call("uma", "ApprovePermit", permit=world.request())


# --- issue ---------------------------------------------------------------------------------------


def test_issue_stores_the_ticks_and_ends_the_validity_at_the_end_of_the_shift(
    world: World,
) -> None:
    permit = world.approved("general")
    made = world.issue(permit)
    assert world.state(permit) == "Active"
    row = world.row(permit)
    assert iso(row["valid_until"]) == "2026-12-01T18:00:00"
    assert iso(row["issued_at"]) == "2026-12-01T07:00:00"
    assert row["issued_by"] == "user:pam" and made.key == "P123-PTW-0001"
    assert '"jha_attached"' in str(row["precautions_json"])


def test_issue_is_capped_by_the_end_of_the_window_when_sooner(world: World) -> None:
    permit = world.approved("general", needed_from="2026-12-01", needed_until="2026-12-01")
    world.at = world.at.replace(hour=20)  # the 18:00 shift runs to 06:00 the next day
    world.issue(permit)
    assert iso(world.row(permit)["valid_until"]) == "2026-12-02T00:00:00"


def test_issue_from_any_other_state_is_refused_naming_the_state_it_needs(world: World) -> None:
    permit = world.request()
    message = raises(PermitStateError, world, "pam", "IssuePermit", permit=permit)
    assert message == "a permit that is Requested does not take IssuePermit; it needs Approved"


def test_issue_refuses_an_unknown_precaution_and_unticked_ones(world: World) -> None:
    permit = world.approved("general")
    assert raises(
        PermitRuleError, world, "pam", "IssuePermit", permit=permit, precautions=["nope"]
    ) == (MSG_UNKNOWN_PRECAUTION)
    message = raises(PermitBlockedError, world, "pam", "IssuePermit", permit=permit)
    assert message == "the permit cannot be made live: precaution_unticked:jha_attached"
    assert world.state(permit) == "Approved"


def test_issue_of_hot_work_is_refused_by_each_gas_blocker_and_passes_when_clean(
    world: World,
) -> None:
    permit = world.approved("hot_work")
    refused = "the permit cannot be made live: "
    assert raises(PermitBlockedError, world, "pam", "IssuePermit", permit=permit) == (
        refused + "gas_test_missing, precaution_unticked:fire_watch, "
        "precaution_unticked:extinguisher, precaution_unticked:combustibles_cleared, "
        "precaution_unticked:spark_containment"
    )
    world.gas_test(permit, result="fail")
    ticks = ["fire_watch", "extinguisher", "combustibles_cleared", "spark_containment"]
    assert raises(
        PermitBlockedError, world, "pam", "IssuePermit", permit=permit, precautions=ticks
    ) == (refused + "gas_test_failed")
    world.at += timedelta(minutes=1)
    world.gas_test(permit)
    world.at += timedelta(minutes=241)
    assert raises(
        PermitBlockedError, world, "pam", "IssuePermit", permit=permit, precautions=ticks
    ) == (refused + "gas_test_stale")
    world.gas_test(permit)
    world.issue(permit)
    assert world.state(permit) == "Active"


def test_issue_of_confined_space_needs_a_verified_isolation(world: World) -> None:
    permit = world.approved("confined_space")
    world.gas_test(permit)
    refused = "the permit cannot be made live: "
    assert raises(
        PermitBlockedError,
        world,
        "pam",
        "IssuePermit",
        permit=permit,
        precautions=["attendant", "rescue_plan", "ventilation", "entry_log"],
    ) == (refused + "isolation_missing")
    isolation = world.isolation(permit)
    assert "isolation_unverified" in raises(
        PermitBlockedError,
        world,
        "pam",
        "IssuePermit",
        permit=permit,
        precautions=["attendant", "rescue_plan", "ventilation", "entry_log"],
    )
    world.verify_isolation(isolation)
    world.issue(permit)
    assert world.state(permit) == "Active"


def test_an_unlinked_isolation_no_longer_counts(world: World) -> None:
    permit = world.approved("isolation")
    isolation = world.isolation(permit, verified=True)
    world.link(permit, isolation, unlink=True)
    assert "isolation_missing" in raises(
        PermitBlockedError,
        world,
        "pam",
        "IssuePermit",
        permit=permit,
        precautions=["points_listed", "locks_tags_applied", "zero_energy_proven"],
    )


def test_a_user_without_the_issue_word_cannot_issue(world: World) -> None:
    permit = world.approved("general")
    with pytest.raises(ForbiddenError):
        world.call("rob", "IssuePermit", permit=permit, precautions=["jha_attached"])


# --- revalidate ----------------------------------------------------------------------------------


def test_revalidate_moves_valid_until_one_shift_and_counts(world: World) -> None:
    permit = world.active()
    world.at = world.at.replace(hour=17)
    world.call("rob", "RevalidatePermit", permit=permit)
    row = world.row(permit)
    assert iso(row["valid_until"]) == "2026-12-02T06:00:00"
    assert row["revalidation_count"] == 1
    assert world.state(permit) == "Active"


def test_a_lapsed_permit_is_revalidated_and_shown_active_again(world: World) -> None:
    permit = world.active()
    world.at = world.at.replace(hour=19)
    world.call("sue", "RevalidatePermit", permit=permit)
    assert iso(world.row(permit)["valid_until"]) == "2026-12-02T06:00:00"


def test_revalidate_is_for_the_holder_or_a_controller_only(world: World) -> None:
    permit = world.active()
    assert raises(ForbiddenError, world, "uma", "RevalidatePermit", permit=permit) == MSG_NOT_PARTY
    world.call("rob", "RevalidatePermit", permit=permit)
    world.call("pam", "RevalidatePermit", permit=permit)
    assert world.row(permit)["revalidation_count"] == 2


def test_revalidate_is_never_past_the_longest_validity_from_issue(world: World) -> None:
    permit = world.active("work_at_height")
    # the permit was issued at 07:00 on day 1: seven days end at 07:00 on day 8
    world.at = world.at.replace(day=8, hour=6, minute=30)
    world.call("rob", "RevalidatePermit", permit=permit)
    assert iso(world.row(permit)["valid_until"]) == "2026-12-08T07:00:00"
    world.at = world.at.replace(hour=7, minute=0)
    assert raises(PermitRuleError, world, "rob", "RevalidatePermit", permit=permit) == MSG_MAX_DAYS


def test_revalidate_of_hot_work_needs_a_fresh_passing_test(world: World) -> None:
    permit = world.approved("hot_work")
    world.gas_test(permit)
    world.issue(permit)
    world.at = world.at.replace(hour=17)
    world.at += timedelta(hours=3)
    assert raises(PermitBlockedError, world, "rob", "RevalidatePermit", permit=permit) == (
        "the permit cannot be made live: gas_test_stale"
    )
    world.gas_test(permit)
    world.call("rob", "RevalidatePermit", permit=permit)
    assert world.row(permit)["revalidation_count"] == 1


# --- suspend, resume, hand back, close, cancel -------------------------------------------------


def test_anyone_with_the_word_suspends_and_only_the_authority_resumes(world: World) -> None:
    permit = world.active()
    world.call("uma", "SuspendPermit", permit=permit, reason="Gas alarm")
    assert world.state(permit) == "Suspended"
    assert world.row(permit)["suspend_reason"] == "Gas alarm"
    with pytest.raises(ForbiddenError):
        world.call("uma", "ResumePermit", permit=permit)
    world.at = world.at.replace(hour=9)
    world.call("pam", "ResumePermit", permit=permit)
    assert world.state(permit) == "Active"
    assert iso(world.row(permit)["valid_until"]) == "2026-12-01T18:00:00"


def test_suspend_needs_a_reason_of_one_to_three_hundred_characters(world: World) -> None:
    permit = world.active()
    for reason in ("", "x" * 301):
        with pytest.raises(ValidationError):
            world.call("uma", "SuspendPermit", permit=permit, reason=reason)


def test_a_lapsed_permit_can_be_suspended(world: World) -> None:
    permit = world.active()
    world.at = world.at.replace(hour=19)
    world.call("uma", "SuspendPermit", permit=permit, reason="Stop")
    assert world.state(permit) == "Suspended"


def test_resume_runs_the_issue_guards_again(world: World) -> None:
    permit = world.approved("hot_work")
    world.gas_test(permit)
    world.issue(permit)
    world.call("uma", "SuspendPermit", permit=permit, reason="Gas alarm")
    world.at += timedelta(minutes=250)  # the passing test is now stale
    world.at = world.at.replace(hour=11)
    message = raises(PermitBlockedError, world, "pam", "ResumePermit", permit=permit)
    assert message == "the permit cannot be made live: gas_test_stale"
    assert world.state(permit) == "Suspended"
    world.gas_test(permit)
    world.call("pam", "ResumePermit", permit=permit)
    assert world.state(permit) == "Active"


def test_hand_back_needs_the_note_and_the_holder_or_a_controller(world: World) -> None:
    permit = world.active()
    with pytest.raises(ValidationError):
        world.call("rob", "HandBackPermit", permit=permit)
    assert raises(
        ForbiddenError, world, "uma", "HandBackPermit", permit=permit, handback_note="Site clear"
    ) == (MSG_NOT_PARTY)
    world.call("rob", "HandBackPermit", permit=permit, handback_note="Site clear")
    assert world.state(permit) == "Handed back"
    assert world.row(permit)["handback_note"] == "Site clear"


def test_a_suspended_permit_can_be_handed_back_and_then_closed(world: World) -> None:
    permit = world.active()
    world.call("uma", "SuspendPermit", permit=permit, reason="Stop")
    world.call("sue", "HandBackPermit", permit=permit, handback_note="Site clear")
    with pytest.raises(ForbiddenError):
        world.call("rob", "ClosePermit", permit=permit)
    world.call("pam", "ClosePermit", permit=permit)
    assert world.state(permit) == "Closed"
    assert world.row(permit)["closed_by"] == "user:pam"


def test_cancel_from_requested_or_approved_with_a_reason(world: World) -> None:
    first, second = world.request(), world.approved()
    world.call("pam", "CancelPermit", permit=first, reason="Work moved")
    world.call("pam", "CancelPermit", permit=second, reason="Work moved")
    assert (world.state(first), world.state(second)) == ("Cancelled", "Cancelled")
    assert world.row(first)["cancel_reason"] == "Work moved"
    with pytest.raises(ValidationError):
        world.call("pam", "CancelPermit", permit=world.request())


COMMANDS_BY_NAME: dict[str, dict[str, Any]] = {
    "ApprovePermit": {},
    "RejectPermit": {"reason": "r"},
    "IssuePermit": {"precautions": ["jha_attached"]},
    "RevalidatePermit": {},
    "SuspendPermit": {"reason": "r"},
    "ResumePermit": {},
    "HandBackPermit": {"handback_note": "n"},
    "ClosePermit": {},
    "CancelPermit": {"reason": "r"},
}


@pytest.mark.parametrize("final", ["Closed", "Rejected", "Cancelled"])
def test_closed_rejected_and_cancelled_accept_nothing(world: World, final: str) -> None:
    permit = world.request()
    if final == "Rejected":
        world.call("sue", "RejectPermit", permit=permit, reason="r")
    elif final == "Cancelled":
        world.call("pam", "CancelPermit", permit=permit, reason="r")
    else:
        world.call("sue", "ApprovePermit", permit=permit)
        world.issue(permit)
        world.call("pam", "HandBackPermit", permit=permit, handback_note="n")
        world.call("pam", "ClosePermit", permit=permit)
    before = world.count()
    for name, fields in COMMANDS_BY_NAME.items():
        with pytest.raises(PermitStateError) as caught:
            world.call("pam", name, permit=permit, **fields)
        assert f"does not take {name}" in str(caught.value) and final in str(caught.value)
    assert world.count() == before and world.state(permit) == final


def test_a_wrong_state_names_the_states_the_command_needs(world: World) -> None:
    permit = world.request()
    assert raises(PermitStateError, world, "pam", "ClosePermit", permit=permit) == (
        "a permit that is Requested does not take ClosePermit; it needs Handed back"
    )
    assert raises(PermitStateError, world, "rob", "RevalidatePermit", permit=permit) == (
        "a permit that is Requested does not take RevalidatePermit; it needs Active or Lapsed"
    )


# --- versions and one unit of work ---------------------------------------------------------------


def test_a_stale_expected_version_is_refused_and_nothing_is_written(world: World) -> None:
    permit = world.request()
    before = world.count()
    with pytest.raises(StaleVersionError):
        world.call("sue", "ApprovePermit", permit=permit, expected_version=1)
    assert world.count() == before and world.state(permit) == "Requested"
    world.call("sue", "ApprovePermit", permit=permit, expected_version=world.version(permit))
    assert world.state(permit) == "Approved"


def test_each_move_appends_one_module_event_and_one_workflow_event(world: World) -> None:
    permit = world.request()
    made = world.call("sue", "ApprovePermit", permit=permit)
    assert [e.event_type for e in made.events][0] == "Permit.Approved"
    assert len(made.events) == 2


def test_an_id_that_is_not_a_permit_reads_as_missing(world: World) -> None:
    iwp = world.record("awp.IWP", "IWP-1")
    assert raises(RecordNotFoundError, world, "sue", "ApprovePermit", permit=iwp) == (
        "no record with that id"
    )


def test_a_namesake_with_another_account_is_not_the_holder(world: World) -> None:
    permit = world.active(holder="Uma")  # rob asked; the holder text names uma
    assert raises(ForbiddenError, world, "uma", "RevalidatePermit", permit=permit) == MSG_NOT_PARTY
    assert raises(
        ForbiddenError, world, "uma", "HandBackPermit", permit=permit, handback_note="Clear"
    ) == (MSG_NOT_PARTY)
    world.call("rob", "RevalidatePermit", permit=permit)  # the requester
    world.call("sue", "HandBackPermit", permit=permit, handback_note="Clear")  # a controller
    assert world.state(permit) == "Handed back"


def test_a_second_revalidate_in_one_shift_leaves_valid_until_and_the_next_shift_extends(
    world: World,
) -> None:
    permit = world.active()
    world.at = world.at.replace(hour=17)
    world.call("rob", "RevalidatePermit", permit=permit)
    first = iso(world.row(permit)["valid_until"])
    assert first == "2026-12-02T06:00:00"
    world.at = world.at.replace(hour=17, minute=30)
    world.call("rob", "RevalidatePermit", permit=permit)
    assert iso(world.row(permit)["valid_until"]) == first
    assert world.row(permit)["revalidation_count"] == 2
    world.at = world.at.replace(day=2, hour=6, minute=30)  # the next shift
    world.call("rob", "RevalidatePermit", permit=permit)
    assert iso(world.row(permit)["valid_until"]) == "2026-12-02T18:00:00"


def test_needed_until_caps_revalidate_and_resume_as_it_does_issue(world: World) -> None:
    permit = world.active(needed_until="2026-12-01")
    other = world.active(needed_until="2026-12-01")
    world.at = world.at.replace(hour=17)
    world.call("rob", "RevalidatePermit", permit=permit)
    assert iso(world.row(permit)["valid_until"]) == "2026-12-02T00:00:00"
    world.at = world.at.replace(day=2, hour=0, minute=30)
    assert raises(PermitRuleError, world, "rob", "RevalidatePermit", permit=permit) == (
        MSG_WINDOW_OVER
    )
    world.at = world.at.replace(day=1, hour=17)
    world.call("uma", "SuspendPermit", permit=other, reason="Stop")
    world.at = world.at.replace(day=1, hour=20)
    world.call("pam", "ResumePermit", permit=other)
    assert iso(world.row(other)["valid_until"]) == "2026-12-02T00:00:00"
    world.call("uma", "SuspendPermit", permit=other, reason="Stop")
    world.at = world.at.replace(day=2, hour=1)
    assert raises(PermitRuleError, world, "pam", "ResumePermit", permit=other) == MSG_WINDOW_OVER


def test_the_requesting_account_may_not_issue_but_the_approver_may(world: World) -> None:
    mine = world.request("sue")
    world.call("pam", "ApprovePermit", permit=mine)
    assert raises(
        ForbiddenError, world, "sue", "IssuePermit", permit=mine, precautions=["jha_attached"]
    ) == (MSG_SELF_ISSUE)
    assert world.state(mine) == "Approved"
    theirs = world.request("rob")
    world.call("sue", "ApprovePermit", permit=theirs)
    world.call("sue", "IssuePermit", permit=theirs, precautions=["jha_attached"])
    assert world.state(theirs) == "Active"
