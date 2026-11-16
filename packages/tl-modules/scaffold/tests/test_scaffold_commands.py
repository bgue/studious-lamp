"""The nine scaffold commands: allowed, refused in the wrong state, refused for the wrong word."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from scaffold_world import SCOPE, World
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_scaffold.errors import (
    DismantleRefused,
    ScaffoldRuleError,
    ScaffoldStateError,
    StaleVersionError,
)
from tl_mod_scaffold.guards import MSG_REMOVED
from tl_mod_scaffold.handlers.scaffold import (
    MSG_HIDDEN_IWP,
    MSG_NOT_GREEN,
    MSG_ONE_PER_REQUEST,
    MSG_REQUEST_STATE,
)


def refuses(error: type[BaseException], world: World, who: str, name: str, **fields: object) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


# --- register ---


def test_register_numbers_copies_and_links(world: World) -> None:
    iwp = world.iwp("IWP-1")
    request = world.request(for_record_id=iwp)
    made = world.call(
        "uma", "RegisterScaffold", request_id=request, title="Scaffold A", location_text="North"
    )
    assert made.key == "P123-SCF-0001"
    row = world.row(made.stream_id)
    assert row["request_id"] == request and row["for_record_id"] == iwp
    assert (row["location_text"], row["elevation"], row["gridline"], row["load_class"]) == (
        "North",
        "+12.0",
        "C-4",
        "Light",
    )
    assert row["tag"] is None and row["inspection_count"] == 0
    assert world.state(made.stream_id) == "Requested"
    links = world.rows(
        "SELECT relation, to_id, source FROM cur_links WHERE from_id = :i", i=made.stream_id
    )
    assert {(r["relation"], r["to_id"], r["source"]) for r in links} == {
        ("belongs_to", request, "rule")
    }


def test_register_needs_an_approved_request_and_one_scaffold_per_request(world: World) -> None:
    waiting = world.request(approve=False)
    assert (
        refuses(ScaffoldRuleError, world, "uma", "RegisterScaffold", request_id=waiting, title="A")
        == MSG_REQUEST_STATE
    )
    rejected = world.request(approve=False)
    world.call(
        "sue",
        "RejectRequisition",
        requisition=rejected,
        expected_version=world.version(rejected),
        reason="No",
    )
    assert (
        refuses(ScaffoldRuleError, world, "uma", "RegisterScaffold", request_id=rejected, title="A")
        == MSG_REQUEST_STATE
    )
    cancelled = world.request()
    world.call(
        "uma",
        "CancelRequisition",
        requisition=cancelled,
        expected_version=world.version(cancelled),
        reason="No",
    )
    assert (
        refuses(
            ScaffoldRuleError, world, "uma", "RegisterScaffold", request_id=cancelled, title="A"
        )
        == MSG_REQUEST_STATE
    )
    ok = world.request()
    world.register(ok)
    assert (
        refuses(ScaffoldRuleError, world, "uma", "RegisterScaffold", request_id=ok, title="B")
        == MSG_ONE_PER_REQUEST
    )
    assert world.count("cur_scaffold_scaffold") == 1


def test_register_refuses_what_is_not_a_scaffold_request(world: World) -> None:
    labour = str(
        world.call(
            "uma",
            "RaiseRequisition",
            requisition={
                "kind": "labor",
                "subject": "Six",
                "craft": "Fitter",
                "headcount": 2,
                "start_date": "2026-11-02",
                "end_date": "2026-11-13",
            },
        ).stream_id
    )
    other = world.iwp("IWP-9")
    for request in (labour, other, "01J9Z6Q4W3X2Y1V0T9S8R7Q6PZ"):
        assert "no record" in refuses(
            RecordNotFoundError, world, "uma", "RegisterScaffold", request_id=request, title="A"
        )


def test_register_is_a_user_word_and_a_viewer_is_refused(world: World) -> None:
    request = world.request()
    refuses(ForbiddenError, world, "vera", "RegisterScaffold", request_id=request, title="A")
    world.call("rob", "RegisterScaffold", request_id=request, title="A")


def test_the_inspector_and_other_actor_fields_are_never_inputs(world: World) -> None:
    request = world.request()
    with pytest.raises(ValidationError):
        world.call("uma", "RegisterScaffold", request_id=request, title="A", inspector="user:sue")


# --- the life ---


def test_the_whole_life_from_request_to_removed(world: World) -> None:
    sid = world.register()
    assert world.state(sid) == "Requested"
    world.call("uma", "DesignScaffold", scaffold=sid, note="SD-12")
    assert world.state(sid) == "Designed"
    world.call("uma", "ErectScaffold", scaffold=sid)
    assert world.state(sid) == "Erecting"
    assert world.row(sid)["next_due_on"] is not None
    green = world.call("sue", "TagScaffoldGreen", scaffold=sid, note="Good")
    assert world.state(sid) == "Inspected"
    row = world.row(sid)
    assert row["tag"] == "green" and row["inspection_count"] == 1
    assert row["last_inspected_on"] == row["tagged_on"] == datetime.now(UTC).date().isoformat()
    inspection = world.rows("SELECT * FROM cur_scaffold_scaffold_inspection")[0]
    assert (inspection["scaffold_id"], inspection["result"], inspection["tag"]) == (
        sid,
        "pass",
        "green",
    )
    assert inspection["inspector"] == "user:sue" and inspection["note"] == "Good"
    key = world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=inspection["id"])
    assert key == "P123-SCI-0001" and green.key == "P123-SCF-0001"
    world.call("uma", "ReleaseScaffold", scaffold=sid)
    assert world.state(sid) == "In Use"
    world.call("uma", "ModifyScaffold", scaffold=sid, reason="Add a lift")
    assert world.state(sid) == "Modify" and world.row(sid)["tag"] == "green"
    assert world.row(sid)["modify_reason"] == "Add a lift"
    world.call("sue", "TagScaffoldGreen", scaffold=sid)
    assert world.state(sid) == "Inspected" and world.row(sid)["inspection_count"] == 2
    world.call("uma", "DismantleScaffold", scaffold=sid, reason="Work done")
    assert world.state(sid) == "Dismantle" and world.row(sid)["dismantle_reason"] == "Work done"
    world.call("uma", "RemoveScaffold", scaffold=sid)
    assert world.state(sid) == "Removed"
    assert world.event_types(sid)[:3] == [
        "Record.Created",
        "Scaffold.Registered",
        "Scaffold.Designed",
    ]
    assert world.event_types(sid)[-1] == "Workflow.Transitioned"


@pytest.mark.parametrize("stage", ["Requested", "Designed"])
def test_a_request_that_never_stood_is_withdrawn(world: World, stage: str) -> None:
    sid = world.register()
    if stage == "Designed":
        world.advance(sid, "Designed")
    world.call("uma", "RemoveScaffold", scaffold=sid, reason="Not needed")
    assert world.state(sid) == "Removed"


def test_a_removed_scaffold_takes_nothing(world: World) -> None:
    sid = world.register()
    world.call("uma", "RemoveScaffold", scaffold=sid)
    for name, extra in (
        ("DesignScaffold", {}),
        ("ErectScaffold", {}),
        ("InspectScaffold", {"result": "fail"}),
        ("TagScaffoldGreen", {}),
        ("ReleaseScaffold", {}),
        ("ModifyScaffold", {"reason": "x"}),
        ("DismantleScaffold", {"reason": "x"}),
        ("RemoveScaffold", {}),
    ):
        who = "sue" if name == "TagScaffoldGreen" else "uma"
        assert refuses(ScaffoldStateError, world, who, name, scaffold=sid, **extra) == MSG_REMOVED


# --- wrong state ---


@pytest.mark.parametrize(
    ("at", "name", "extra"),
    [
        ("Requested", "ErectScaffold", {}),
        ("Requested", "InspectScaffold", {"result": "fail"}),
        ("Requested", "TagScaffoldGreen", {}),
        ("Requested", "ReleaseScaffold", {}),
        ("Requested", "ModifyScaffold", {"reason": "x"}),
        ("Requested", "DismantleScaffold", {"reason": "x"}),
        ("Designed", "DesignScaffold", {}),
        ("Designed", "TagScaffoldGreen", {}),
        ("Erecting", "ReleaseScaffold", {}),
        ("Erecting", "DismantleScaffold", {"reason": "x"}),
        ("Erecting", "RemoveScaffold", {}),
        ("Inspected", "RemoveScaffold", {}),
        ("In Use", "ReleaseScaffold", {}),
        ("In Use", "RemoveScaffold", {}),
    ],
)
def test_a_command_refused_in_the_wrong_state(
    world: World, at: str, name: str, extra: dict
) -> None:  # type: ignore[type-arg]
    sid = world.register()
    if at != "Requested":
        world.advance(sid, at)
    who = "sue" if name == "TagScaffoldGreen" else "uma"
    before = world.count()
    message = refuses(ScaffoldStateError, world, who, name, scaffold=sid, **extra)
    assert at in message and name in message
    assert world.count() == before and world.state(sid) == at


# --- inspect and the green tag ---


def test_inspect_takes_only_conditional_or_fail(world: World) -> None:
    sid = world.advance(world.register(), "Erecting")
    with pytest.raises(ValidationError):
        world.call("uma", "InspectScaffold", scaffold=sid, result="pass")
    with pytest.raises(ValidationError):
        world.call("uma", "InspectScaffold", scaffold=sid, result="green")


def test_a_conditional_inspection_tags_yellow_and_changes_no_state(world: World) -> None:
    sid = world.advance(world.register(), "Erecting")
    world.call("uma", "InspectScaffold", scaffold=sid, result="conditional", note="Toe boards")
    assert world.state(sid) == "Erecting" and world.row(sid)["tag"] == "yellow"
    world.call("sue", "TagScaffoldGreen", scaffold=sid)
    world.call("uma", "InspectScaffold", scaffold=sid, result="conditional")
    assert world.state(sid) == "Inspected" and world.row(sid)["tag"] == "yellow"
    assert (
        refuses(ScaffoldRuleError, world, "uma", "ReleaseScaffold", scaffold=sid) == MSG_NOT_GREEN
    )


def test_a_failed_inspection_of_a_standing_scaffold_moves_it_to_modify(world: World) -> None:
    sid = world.advance(world.register(), "In Use")
    world.call("uma", "InspectScaffold", scaffold=sid, result="fail", note="Loose ledger")
    assert world.state(sid) == "Modify"
    row = world.row(sid)
    assert row["tag"] == "red" and row["modify_reason"] == "failed inspection"
    assert refuses(ScaffoldStateError, world, "uma", "ReleaseScaffold", scaffold=sid)
    world.call("sue", "TagScaffoldGreen", scaffold=sid)
    assert world.state(sid) == "Inspected" and world.row(sid)["tag"] == "green"
    world.call("uma", "ReleaseScaffold", scaffold=sid)
    assert world.state(sid) == "In Use"


def test_a_failed_inspection_while_erecting_or_modifying_keeps_the_state(world: World) -> None:
    sid = world.advance(world.register(), "Erecting")
    world.call("uma", "InspectScaffold", scaffold=sid, result="fail")
    assert world.state(sid) == "Erecting" and world.row(sid)["tag"] == "red"


def test_release_needs_a_green_tag(world: World) -> None:
    sid = world.advance(world.register(), "Inspected")
    world.call("uma", "InspectScaffold", scaffold=sid, result="conditional")
    assert (
        refuses(ScaffoldRuleError, world, "uma", "ReleaseScaffold", scaffold=sid) == MSG_NOT_GREEN
    )
    assert world.state(sid) == "Inspected"


def test_the_green_tag_is_a_controller_word(world: World) -> None:
    sid = world.advance(world.register(), "Erecting")
    for who in ("uma", "rob", "vera"):
        refuses(ForbiddenError, world, who, "TagScaffoldGreen", scaffold=sid)
    assert world.row(sid)["tag"] is None
    world.call("sue", "TagScaffoldGreen", scaffold=sid)
    assert world.row(sid)["tag"] == "green"
    # a user may still inspect (yellow, red)
    world.call("uma", "InspectScaffold", scaffold=sid, result="conditional")


def test_the_inspection_time_is_not_in_the_future_nor_before_registration(world: World) -> None:
    sid = world.advance(world.register(), "Erecting")
    soon = datetime.now(UTC) + timedelta(days=1)
    refuses(ScaffoldRuleError, world, "sue", "TagScaffoldGreen", scaffold=sid, at=soon)
    long_ago = datetime(2020, 1, 1, tzinfo=UTC)
    refuses(ScaffoldRuleError, world, "sue", "TagScaffoldGreen", scaffold=sid, at=long_ago)
    with pytest.raises(ValidationError):
        world.call("sue", "TagScaffoldGreen", scaffold=sid, at=datetime(2026, 1, 1))
    earlier = datetime.now(UTC) - timedelta(hours=1)
    world.call("sue", "TagScaffoldGreen", scaffold=sid, at=earlier)
    assert world.rows("SELECT count(*) AS n FROM cur_scaffold_scaffold_inspection")[0]["n"] == 1


def test_the_next_due_day_follows_the_interval_setting(world: World) -> None:
    sid = world.advance(world.register(), "Inspected")
    row = world.row(sid)
    assert (
        row["next_due_on"]
        == (datetime.fromisoformat(row["last_inspected_on"]) + timedelta(days=7)).date().isoformat()
    )


# --- modify, dismantle ---


def test_modify_keeps_the_tag(world: World) -> None:
    sid = world.advance(world.register(), "Inspected")
    world.call("uma", "ModifyScaffold", scaffold=sid, reason="Extend")
    assert world.state(sid) == "Modify" and world.row(sid)["tag"] == "green"
    refuses(ScaffoldStateError, world, "uma", "ModifyScaffold", scaffold=sid, reason="Again")


def test_dismantle_is_refused_while_a_work_package_in_use_requires_it(world: World) -> None:
    sid = world.advance(world.register(), "In Use")
    issued = world.iwp("IWP-77", "Issued")
    world.require(issued, sid)
    message = refuses(
        DismantleRefused, world, "uma", "DismantleScaffold", scaffold=sid, reason="Done"
    )
    assert "IWP-77" in message and "Issued" in message
    assert world.state(sid) == "In Use"


@pytest.mark.parametrize("state", ["Issued", "In progress", "On hold"])
def test_each_holding_state_blocks(world: World, state: str) -> None:
    sid = world.advance(world.register(), "Inspected")
    world.require(world.iwp("IWP-5", state), sid)
    assert state in refuses(
        DismantleRefused, world, "uma", "DismantleScaffold", scaffold=sid, reason="x"
    )


@pytest.mark.parametrize("state", ["Draft", "Ready", "Field complete", "Closed"])
def test_a_quiet_or_finished_work_package_does_not_block(world: World, state: str) -> None:
    sid = world.advance(world.register(), "Inspected")
    world.require(world.iwp("IWP-5", state), sid)
    world.call("uma", "DismantleScaffold", scaffold=sid, reason="Done")
    assert world.state(sid) == "Dismantle"


def test_a_retracted_link_does_not_block(world: World) -> None:
    sid = world.advance(world.register(), "Inspected")
    iwp = world.iwp("IWP-5", "Issued")
    world.require(iwp, sid)
    link = world.scalar("SELECT link_id FROM cur_links WHERE from_id = :i", i=iwp)
    from tl_adapters.db import open_uow
    from tl_core.services.links import RetractLink, handle_retract_link

    with open_uow(world.db) as uow:
        handle_retract_link(
            uow,
            RetractLink(
                actor="user:uma", source="test", scope=SCOPE, link_id=link, reason="Not needed"
            ),
        )
    world.call("uma", "DismantleScaffold", scaffold=sid, reason="Done")
    assert world.state(sid) == "Dismantle"


def test_another_open_scaffold_request_of_the_package_blocks_but_its_own_does_not(
    world: World,
) -> None:
    iwp = world.iwp("IWP-8", "Closed")
    own = world.request(for_record_id=iwp)
    sid = world.advance(world.register(own), "Inspected")
    world.require(iwp, sid)
    # the own request stays open until Closed: it does not hold
    world.call("uma", "DismantleScaffold", scaffold=sid, reason="Done")
    sid2 = world.advance(world.register(world.request(for_record_id=iwp)), "Inspected")
    world.require(iwp, sid2)
    other = world.request(for_record_id=iwp, approve=False)
    key = world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=other)
    message = refuses(
        DismantleRefused, world, "uma", "DismantleScaffold", scaffold=sid2, reason="x"
    )
    assert key in message


def test_a_hidden_work_package_blocks_and_is_not_named(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = world.advance(world.register(), "In Use")
    secret = world.iwp("IWP-SECRET", "In progress")
    world.require(secret, sid)
    monkeypatch.setattr("tl_mod_scaffold.handlers.scaffold._hidden", lambda conn, ids: set(ids))
    message = refuses(DismantleRefused, world, "uma", "DismantleScaffold", scaffold=sid, reason="x")
    assert MSG_HIDDEN_IWP in message and "IWP-SECRET" not in message
    assert "In progress" not in message and "progress" not in message


def test_two_hidden_work_packages_one_holding_still_refuse_and_say_no_state(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = world.advance(world.register(), "In Use")
    world.require(world.iwp("IWP-A-HOLD", "In progress"), sid)
    world.require(world.iwp("IWP-B-IDLE", "Draft"), sid)
    world.require(world.iwp("IWP-C-HOLD", "In progress"), sid)
    monkeypatch.setattr("tl_mod_scaffold.handlers.scaffold._hidden", lambda conn, ids: set(ids))
    message = refuses(DismantleRefused, world, "uma", "DismantleScaffold", scaffold=sid, reason="x")
    assert "2 work packages you cannot see" in message
    assert "IWP-" not in message and "progress" not in message and "Draft" not in message


# --- generic commands and versions ---


def test_expected_version_is_checked(world: World) -> None:
    sid = world.register()
    refuses(StaleVersionError, world, "uma", "DesignScaffold", scaffold=sid, expected_version=99)
    world.call("uma", "DesignScaffold", scaffold=sid, expected_version=world.version(sid))
    assert world.state(sid) == "Designed"


def test_an_unknown_or_foreign_id_answers_alike(world: World) -> None:
    refuses(
        RecordNotFoundError, world, "uma", "DesignScaffold", scaffold="01J9Z6Q4W3X2Y1V0T9S8R7Q6PZ"
    )
    iwp = world.iwp("IWP-2")
    refuses(RecordNotFoundError, world, "uma", "DesignScaffold", scaffold=iwp)
