"""Setting changes against a real ledger, on every adapter (P0-I8-A; brief 30.2, 30.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from settings_world import ALICE, P1, SRC, World, future
from tl_adapters.db import open_uow
from tl_core import settings as S
from tl_core.services.errors import (
    InvalidSettingValueError,
    ReasonRequiredError,
    RiskNotAcceptedError,
    SecretSettingUnavailableError,
    SettingChangeNotFoundError,
    SettingLockedError,
    SettingNotLockableError,
    SettingOutOfBoundsError,
    SettingScopeError,
    UnknownSettingError,
)
from tl_core.settings.types import SETTING_CHANGED, SETTING_LOCKED

# --- setting a value ----------------------------------------------------------------------------


def test_a_company_value_is_recorded_on_the_keys_stream_and_resolves(world: World) -> None:
    got = world.set("t.limit", "company", 20)
    assert (got.value, got.origin, got.modified_here) == (20, "company", True)
    (event,) = world.events()
    assert (event.event_type, event.stream_id, event.stream_type) == (
        SETTING_CHANGED,
        "setting:company:t.limit",
        "core.Setting",
    )
    assert (event.scope, event.actor, event.source) == ("company", ALICE, SRC)
    assert event.payload == {
        "key": "t.limit",
        "layer": "company",
        "old_value": None,
        "old_set": False,
        "new_value": 20,
        "reset": False,
        "reason": None,
        "applies_at": None,
        "accept_risk": False,
    }
    assert world.value("t.limit") == 20


def test_a_project_value_has_the_project_scope_and_inherits_the_company(world: World) -> None:
    world.set("t.limit", "company", 20)
    got = world.set("t.limit", P1, 30)
    assert (got.value, got.origin, got.modified_here) == (30, "project", True)
    event = world.events()[-1]
    assert (event.scope, event.stream_id) == (P1, "setting:project:P1:t.limit")
    assert (event.payload["old_set"], event.payload["old_value"]) == (False, None)
    assert world.value("t.limit", project="P2") == 20
    assert world.get("t.limit", project="P2").modified_here is False


def test_a_second_change_records_what_it_replaced(world: World) -> None:
    world.set("t.limit", P1, 30)
    world.set("t.limit", P1, 40)
    event = world.events()[-1]
    assert (event.payload["old_set"], event.payload["old_value"], event.payload["new_value"]) == (
        True,
        30,
        40,
    )
    assert event.stream_version == 2


def test_setting_the_value_a_layer_already_holds_writes_nothing(world: World) -> None:
    world.set("t.limit", P1, 30)
    head = world.head()
    got = world.set("t.limit", P1, 30)
    assert got.value == 30 and world.head() == head
    world.set("t.limit", "company", 30)  # the company holds nothing yet: this is a change
    assert world.head() == head + 1


def test_a_user_value_belongs_to_the_company_scope_and_only_for_ui_keys(world: World) -> None:
    got = world.set("ui.t.pref", "user:alice", "b")
    assert (got.value, got.origin) == ("b", "user")
    assert world.events()[-1].scope == "company"
    assert world.value("ui.t.pref", user="bob") == "a"
    with pytest.raises(SettingScopeError, match="not a UI key"):
        world.set("t.plain", "user:alice", "y")
    with pytest.raises(SettingScopeError, match="cannot be set at the project layer"):
        world.set("ui.t.pref", P1, "b")


def test_the_layer_must_be_one_the_key_allows(world: World) -> None:
    with pytest.raises(SettingScopeError, match="company"):
        world.set("t.restart", P1, 3)  # a company key
    for bad in ("default", "team:x", "project:", "project:a b", "user:", "", "company:x"):
        with pytest.raises(SettingScopeError, match="not a layer"):
            world.set("t.limit", bad, 1)
    assert world.head() == 0


def test_the_value_must_fit_the_definition(world: World) -> None:
    for value in ("5", 5.5, True, 101, -1, None):
        with pytest.raises(InvalidSettingValueError):
            world.set("t.limit", "company", value)
    with pytest.raises(InvalidSettingValueError, match="below the minimum"):
        world.set("t.every", "company", "9s")
    with pytest.raises(UnknownSettingError, match="no.such"):
        world.set("no.such", "company", 1)
    assert world.head() == 0


def test_a_secret_setting_is_refused_because_there_is_no_vault(world: World) -> None:
    with pytest.raises(SecretSettingUnavailableError, match="vault"):
        world.set("t.secret", "company", "s3cret")
    with pytest.raises(SecretSettingUnavailableError):
        world.reset("t.secret", "company")
    assert world.head() == 0


# --- reason and risk ----------------------------------------------------------------------------


def test_an_advanced_key_needs_a_reason(world: World) -> None:
    for reason in (None, "", "   "):
        with pytest.raises(ReasonRequiredError, match="advanced"):
            world.set("t.advanced", "company", "b", reason=reason)
    got = world.set("t.advanced", "company", "b", reason="  field pilot  ")
    assert got.value == "b"
    assert world.events()[-1].payload["reason"] == "field pilot"
    with pytest.raises(InvalidSettingValueError, match="longer"):
        world.set("t.advanced", "company", "c", reason="x" * 1001)


def test_a_dangerous_key_also_needs_the_risk_accepted(world: World) -> None:
    with pytest.raises(ReasonRequiredError):
        world.set("t.danger", "company", ["a"], accept_risk=True)
    with pytest.raises(RiskNotAcceptedError, match="accept the risk"):
        world.set("t.danger", "company", ["a"], reason="because")
    assert world.head() == 0
    world.set("t.danger", "company", ["a"], reason="because", accept_risk=True)
    assert world.events()[-1].payload["accept_risk"] is True


def test_a_normal_key_ignores_a_reason_it_does_not_need(world: World) -> None:
    world.set("t.limit", "company", 3, reason="why not", accept_risk=True)
    assert world.events()[-1].payload["reason"] == "why not"


def test_resetting_a_dangerous_key_follows_the_same_rules(world: World) -> None:
    world.set("t.danger", "company", ["a"], reason="r", accept_risk=True)
    with pytest.raises(ReasonRequiredError):
        world.reset("t.danger", "company")
    with pytest.raises(RiskNotAcceptedError):
        world.reset("t.danger", "company", reason="r")
    world.reset("t.danger", "company", reason="r", accept_risk=True)
    assert world.value("t.danger") == []


# --- reset --------------------------------------------------------------------------------------


def test_a_reset_gives_the_layer_back_to_what_is_above_it(world: World) -> None:
    world.set("t.limit", "company", 20)
    world.set("t.limit", P1, 30)
    got = world.reset("t.limit", P1)
    assert (got.value, got.origin, got.modified_here) == (20, "company", False)
    event = world.events()[-1]
    assert event.payload["reset"] is True and event.payload["new_value"] is None
    assert (event.payload["old_set"], event.payload["old_value"]) == (True, 30)
    assert world.value("t.limit", project="P1") == 20


def test_resetting_a_layer_that_holds_nothing_writes_nothing(world: World) -> None:
    head = world.head()
    got = world.reset("t.limit", P1)
    assert got.origin == "default" and world.head() == head
    world.set("t.limit", P1, 30)
    world.reset("t.limit", P1)
    head = world.head()
    world.reset("t.limit", P1)
    assert world.head() == head


def test_a_value_can_be_set_again_after_a_reset(world: World) -> None:
    world.set("t.limit", P1, 30)
    world.reset("t.limit", P1)
    world.set("t.limit", P1, 30)
    assert world.value("t.limit", project="P1") == 30
    assert [h.reset for h in world.history("t.limit")] == [False, True, False]


# --- locks and bounds ---------------------------------------------------------------------------


def test_a_locked_key_cannot_be_overridden_by_a_project(world: World) -> None:
    world.set("t.limit", "company", 20)
    got = world.lock("t.limit")
    assert got.locked is True
    with pytest.raises(SettingLockedError, match="locked by the company"):
        world.set("t.limit", P1, 30)
    assert world.set("t.limit", "company", 25).value == 25  # the company may still change it
    event = [e for e in world.events() if e.event_type == SETTING_LOCKED][0]
    assert (event.stream_id, event.scope, event.payload["layer"]) == (
        "setting:company:t.limit",
        "company",
        "company",
    )
    assert event.payload == {
        "key": "t.limit",
        "layer": "company",
        "locked": True,
        "bounds": None,
        "reason": "policy",
    }


def test_a_lock_set_after_a_project_value_takes_effect_at_once(world: World) -> None:
    world.set("t.limit", "company", 20)
    world.set("t.limit", P1, 30)
    world.lock("t.limit")
    got = world.get("t.limit", project="P1")
    assert (got.value, got.origin, got.locked) == (20, "company", True)
    assert world.reset("t.limit", P1).origin == "company"  # a project may still clean up
    world.lock("t.limit", locked=False)
    world.set("t.limit", P1, 31)
    assert world.value("t.limit", project="P1") == 31


def test_bounds_limit_what_projects_may_set(world: World) -> None:
    world.lock("t.limit", locked=False, bounds={"maximum": 50, "minimum": 5})
    assert world.set("t.limit", P1, 50).value == 50
    with pytest.raises(SettingOutOfBoundsError, match="above the company maximum"):
        world.set("t.limit", P1, 51)
    with pytest.raises(SettingOutOfBoundsError, match="below the company minimum"):
        world.set("t.limit", P1, 4)
    assert world.set("t.limit", "company", 90).value == 90  # bounds are for projects
    got = world.get("t.limit", project="P1")
    assert got.bounds == {"maximum": 50, "minimum": 5} and got.locked is False


def test_tightening_bounds_over_an_existing_project_value_ignores_it(world: World) -> None:
    world.set("t.limit", "company", 20)
    world.set("t.limit", P1, 60)
    world.lock("t.limit", locked=False, bounds={"maximum": 40})
    got = world.get("t.limit", project="P1")
    assert (got.value, got.origin, got.modified_here) == (20, "company", False)


def test_choices_bound_an_enum_for_projects(world: World) -> None:
    world.lock("project.mode", locked=False, bounds={"choices": ["live", "sandbox"]})
    with pytest.raises(SettingOutOfBoundsError, match="choices"):
        world.set("project.mode", P1, "simulated", reason="r")
    assert world.set("project.mode", P1, "sandbox", reason="r").value == "sandbox"


def test_only_a_lockable_key_can_be_locked_and_a_reason_is_required(world: World) -> None:
    with pytest.raises(SettingNotLockableError):
        world.lock("t.fixed")
    with pytest.raises(ReasonRequiredError):
        world.lock("t.limit", reason="  ")
    with pytest.raises(InvalidSettingValueError, match="must be a number"):
        world.lock("t.limit", bounds={"minimum": "5"})
    with pytest.raises(UnknownSettingError):
        world.lock("no.such")
    assert world.head() == 0


def test_locking_twice_the_same_way_writes_nothing(world: World) -> None:
    world.lock("t.limit")
    head = world.head()
    world.lock("t.limit")
    assert world.head() == head
    world.lock("t.limit", bounds={"maximum": 7})
    assert world.head() == head + 1
    assert world.get("t.limit").bounds == {"maximum": 7}
    world.lock("t.limit", locked=False, bounds=None)
    assert world.get("t.limit").locked is False and world.get("t.limit").bounds is None


def test_lock_and_change_events_share_the_company_stream_version(world: World) -> None:
    world.set("t.limit", "company", 20)
    world.lock("t.limit")
    world.set("t.limit", "company", 21)
    assert [e.stream_version for e in world.events()] == [1, 2, 3]


# --- scheduled changes --------------------------------------------------------------------------


def test_a_scheduled_change_is_recorded_now_and_applies_later(world: World) -> None:
    world.set("t.limit", "company", 20)
    when = future(2)
    got = world.set("t.limit", "company", 30, applies_at=when)
    assert got.value == 20 and [(s.new_value) for s in got.scheduled] == [30]
    event = world.events()[-1]
    assert event.payload["applies_at"] == when.astimezone(UTC).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    assert world.value("t.limit", at=when - timedelta(seconds=1)) == 20
    assert world.value("t.limit", at=when) == 30
    assert world.value("t.limit", at=when + timedelta(days=9)) == 30
    (first, second) = world.history("t.limit")
    assert first.applies_at is None and second.applies_at == event.payload["applies_at"]


def test_a_scheduled_value_must_still_pass_the_checks_now(world: World) -> None:
    with pytest.raises(InvalidSettingValueError):
        world.set("t.limit", "company", 999, applies_at=future())
    world.lock("t.limit")
    with pytest.raises(SettingLockedError):
        world.set("t.limit", P1, 5, applies_at=future())


def test_the_time_must_be_in_the_future_and_have_a_zone(world: World) -> None:
    with pytest.raises(InvalidSettingValueError, match="not in the future"):
        world.set("t.limit", "company", 5, applies_at=datetime.now(UTC) - timedelta(seconds=5))
    with pytest.raises(InvalidSettingValueError, match="timezone"):
        world.set("t.limit", "company", 5, applies_at=datetime.now() + timedelta(hours=1))  # noqa: DTZ005


def test_a_scheduled_reset_and_a_scheduled_value_with_the_same_value_are_recorded(
    world: World,
) -> None:
    world.set("t.limit", "company", 20)
    when = future()
    world.set("t.limit", "company", 20, applies_at=when)  # same value, but scheduled: recorded
    world.reset("t.limit", "company", applies_at=when + timedelta(hours=1))
    got = world.get("t.limit")
    assert got.value == 20 and len(got.scheduled) == 2
    assert world.value("t.limit", at=when + timedelta(hours=2)) == 10  # back to the default
    assert [e.event_type for e in world.events()] == [SETTING_CHANGED] * 3


def test_an_immediate_change_does_not_cancel_a_scheduled_one(world: World) -> None:
    when = future()
    world.set("t.limit", "company", 30, applies_at=when)
    world.set("t.limit", "company", 40)
    assert world.value("t.limit") == 40
    assert world.value("t.limit", at=when + timedelta(seconds=1)) == 30


# --- history and revert -------------------------------------------------------------------------


def test_history_lists_every_change_of_a_key_oldest_first(world: World) -> None:
    world.set("t.limit", "company", 20, reason="first")
    world.set("t.limit", P1, 30)
    world.reset("t.limit", P1)
    rows = world.history("t.limit")
    assert [(h.seq, h.layer, h.new_value, h.reset) for h in rows] == [
        (1, "company", 20, False),
        (2, "project:P1", 30, False),
        (3, "project:P1", None, True),
    ]
    assert rows[0].actor == ALICE and rows[0].reason == "first"
    assert rows[1].old_value is None and rows[2].old_value == 30
    assert rows[0].recorded_at.endswith("Z")
    assert [h.seq for h in world.history("t.limit", layer=P1)] == [2, 3]
    assert world.history("t.every") == []
    with pytest.raises(UnknownSettingError):
        world.history("no.such")
    with pytest.raises(SettingScopeError):
        world.history("t.limit", layer="nonsense")


def test_reverting_a_change_restores_what_it_replaced(world: World) -> None:
    world.set("t.limit", P1, 30)
    world.set("t.limit", P1, 40)
    got = world.revert("t.limit", P1, 2)
    assert got.value == 30
    assert [h.new_value for h in world.history("t.limit")] == [30, 40, 30]


def test_reverting_the_first_change_makes_the_layer_inherit_again(world: World) -> None:
    world.set("t.limit", "company", 20)
    world.set("t.limit", P1, 30)
    got = world.revert("t.limit", P1, 2)
    assert (got.value, got.origin) == (20, "company")
    assert world.history("t.limit")[-1].reset is True


def test_reverting_follows_the_risk_rules_and_needs_a_real_change(world: World) -> None:
    world.set("t.advanced", "company", "b", reason="r")
    world.set("t.advanced", "company", "c", reason="r")
    with pytest.raises(ReasonRequiredError):
        world.revert("t.advanced", "company", 2)
    assert world.revert("t.advanced", "company", 2, reason="oops").value == "b"
    with pytest.raises(SettingChangeNotFoundError):
        world.revert("t.limit", P1, 999)
    with pytest.raises(SettingChangeNotFoundError):  # a change of another layer
        world.revert("t.advanced", P1, 1)


def test_reverting_a_scheduled_change_cancels_it(world: World) -> None:
    world.set("t.limit", "company", 20)
    when = future()
    world.set("t.limit", "company", 30, applies_at=when)
    assert world.value("t.limit", at=when + timedelta(seconds=1)) == 30
    got = world.revert("t.limit", "company", 2)
    assert got.value == 20
    assert world.value("t.limit", at=when + timedelta(seconds=1)) == 20  # the later record wins
    assert world.value("t.limit", at=when + timedelta(days=30)) == 20


# --- diff ---------------------------------------------------------------------------------------


def test_diff_lists_the_keys_whose_value_differs(world: World) -> None:
    world.set("t.limit", "company", 20)
    world.set("t.limit", P1, 30)
    world.set("t.plain", "company", "same")
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        by_default = {d.key: d for d in S.diff(conn, left="default", right="company")}
        by_project = {d.key: d for d in S.diff(conn, left="company", right=P1)}
    assert set(by_default) == {"t.limit", "t.plain"}
    assert (by_default["t.limit"].left.value, by_default["t.limit"].right.value) == (10, 20)
    assert set(by_project) == {"t.limit"}
    assert by_project["t.limit"].right.origin == "project"


def test_diff_against_a_layer_that_is_not_one_is_refused(world: World) -> None:
    with (
        open_uow(world.db, readonly=True) as uow,
        pytest.raises(SettingScopeError, match="default"),
    ):
        S.diff(uow.conn(), left="company", right="elsewhere")


def test_resolve_all_lists_every_key_with_an_optional_prefix(world: World) -> None:
    world.set("t.limit", P1, 30)
    with open_uow(world.db, readonly=True) as uow:
        everything = S.resolve_all(uow.conn(), project="P1")
        only = S.resolve_all(uow.conn(), project="P1", prefix="t.l")
    keys = [e.key for e in everything]
    assert keys == sorted(keys) and "feed.reactions.enabled" in keys and "t.limit" in keys
    assert [e.key for e in only] == ["t.limit"] and only[0].modified_here is True


# --- pending effects ----------------------------------------------------------------------------


def test_a_key_that_needs_a_restart_shows_it_until_the_server_starts(world: World) -> None:
    from tl_core.settings.effects import mark_applied

    world.set("t.restart", "company", 3)
    assert world.get("t.restart").pending_effect == "restart"
    with open_uow(world.db) as uow:
        mark_applied(uow.conn(), ["restart"], applied_by="server")
    assert world.get("t.restart").pending_effect is None
    world.set("t.restart", "company", 4)
    assert world.get("t.restart").pending_effect == "restart"


def test_applied_effects_survive_a_projection_rebuild(world: World) -> None:
    from tl_adapters.db import rebuild_projections
    from tl_core.settings.effects import mark_applied

    world.set("t.restart", "company", 3)
    with open_uow(world.db) as uow:
        mark_applied(uow.conn(), ["restart"], applied_by="server")
    rebuild_projections(world.db)
    assert world.get("t.restart").pending_effect is None
    assert world.value("t.restart") == 3


def test_an_unknown_effect_name_is_refused(world: World) -> None:
    from tl_core.settings.effects import mark_applied

    with open_uow(world.db) as uow, pytest.raises(ValueError, match="unknown effects"):
        mark_applied(uow.conn(), ["reboot"], applied_by="x")


# --- the unit of work ---------------------------------------------------------------------------


def test_nothing_is_kept_when_the_block_that_changed_a_setting_fails(world: World) -> None:
    class Boom(Exception): ...

    with pytest.raises(Boom), open_uow(world.db) as uow:
        S.set_setting(uow, key="t.limit", layer="company", value=5, actor=ALICE, source=SRC)
        raise Boom
    assert world.head() == 0 and world.rows("cur_setting") == []


def test_several_changes_in_one_unit_of_work_chain_the_stream_version(world: World) -> None:
    with open_uow(world.db) as uow:
        for value in (1, 2, 3):
            S.set_setting(uow, key="t.limit", layer=P1, value=value, actor=ALICE, source=SRC)
    assert [e.stream_version for e in world.events()] == [1, 2, 3]
    assert world.value("t.limit", project="P1") == 3


def test_the_correlation_of_a_change_can_be_chosen(world: World) -> None:
    world.set("t.limit", "company", 5, correlation_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6P5")
    assert world.events()[0].correlation_id == "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    world.set("t.limit", "company", 6)
    assert world.events()[1].correlation_id != world.events()[0].correlation_id


def test_the_projection_rows_carry_the_event(world: World) -> None:
    world.set("t.limit", P1, 30, reason="pilot")
    (row,) = world.rows("cur_setting")
    event = world.events()[0]
    assert row["change_id"] == event.event_id and row["seq"] == event.seq
    assert (row["key"], row["layer"], row["scope"]) == ("t.limit", P1, P1)
    assert (row["actor"], row["source"], row["reason"]) == (ALICE, SRC, "pilot")
    assert row["version"] == 1 and bool(row["reset"]) is False and bool(row["old_set"]) is False
    assert row["applies_at"] is None
    assert row["effective_us"] > 0


# --- review fixes (S1 to S5) --------------------------------------------------------------------


def test_only_the_latest_change_at_a_layer_can_be_reverted(world: World) -> None:
    from tl_core.services.errors import SettingRevertNotLatestError

    world.set("t.limit", P1, 30)
    world.set("t.limit", P1, 40)
    world.set("t.limit", "company", 20)  # another layer: does not matter
    with pytest.raises(SettingRevertNotLatestError, match="not the latest"):
        world.revert("t.limit", P1, 1)
    assert world.value("t.limit", project="P1") == 40
    assert world.revert("t.limit", P1, 2).value == 30
    with pytest.raises(SettingRevertNotLatestError):  # the first is older than the revert now
        world.revert("t.limit", P1, 1)
    with pytest.raises(SettingChangeNotFoundError):  # not found is told apart from not latest
        world.revert("t.limit", P1, 77)


def test_true_is_not_one_for_a_no_op_or_a_choice(world: World) -> None:
    world.set("t.flag", "company", True)
    head = world.head()
    world.set("t.flag", "company", True)
    assert world.head() == head  # really the same value
    world.set("t.num", "company", 1)
    with pytest.raises(InvalidSettingValueError):
        world.set("t.num", "company", True)
    # 1 and true are different choices
    with pytest.raises(InvalidSettingValueError, match="not one of"):
        world.set("t.pick", "company", [True])
    assert world.set("t.pick", "company", [1, "a"]).value == [1, "a"]
    world.lock("t.pick", locked=False, bounds={"choices": ["a"]})
    from tl_core.services.errors import SettingOutOfBoundsError

    with pytest.raises(SettingOutOfBoundsError):
        world.set("t.pick", P1, [1])


def test_a_json_value_equal_only_by_python_rules_is_a_change(world: World) -> None:
    world.set("t.blob", "company", {"a": 1})
    head = world.head()
    world.set("t.blob", "company", {"a": True})  # {"a": 1} == {"a": True} in Python
    assert world.head() == head + 1


def test_a_changed_value_never_leaks_into_the_defaults_or_the_next_answer(world: World) -> None:
    got = world.get("feed.signal_tags")
    got.value.append("mutated")
    assert world.value("feed.signal_tags") == ["safety", "hold", "decision", "urgent", "fyi"]
    world.set("t.blob", "company", {"k": [1]})
    seen = world.get("t.blob")
    seen.value["k"].append(2)
    assert world.value("t.blob") == {"k": [1]}
    world.lock("project.mode", locked=False, bounds={"choices": ["live"]})
    bounds = world.get("project.mode").bounds
    assert bounds is not None
    bounds["choices"].append("hack")
    assert world.get("project.mode").bounds == {"choices": ["live"]}


def test_a_pending_effect_belongs_to_the_view_that_changed(world: World) -> None:
    world.set("t.rebuild", P1, 5)
    assert world.get("t.rebuild", project="P1").pending_effect == "rebuild"
    assert world.get("t.rebuild", project="P2").pending_effect is None
    assert world.get("t.rebuild").pending_effect is None
    world.set("t.rebuild", "company", 7)
    assert world.get("t.rebuild", project="P2").pending_effect == "rebuild"  # the company's change


def test_everything_that_does_not_depend_on_the_risk_is_checked_first(world: World) -> None:
    with pytest.raises(InvalidSettingValueError, match="not in the future"):
        world.set(
            "t.danger", "company", ["a"], reason="r", applies_at=datetime.now(UTC) - timedelta(1)
        )
    with pytest.raises(InvalidSettingValueError, match="not in the future"):
        world.set("t.danger", "company", ["a"], applies_at=datetime.now(UTC) - timedelta(1))
