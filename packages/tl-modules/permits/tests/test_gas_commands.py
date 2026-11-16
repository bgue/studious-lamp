"""``RecordGasTest``: the computed result, the bounds, the clock and the safety suspend (S3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from permit_world import SCOPE, World
from pydantic import ValidationError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_permits.errors import GasTestRuleError, PermitBlockedError, PermitStateError
from tl_mod_permits.handlers.gas_test import MSG_FUTURE
from tl_mod_permits.iso_commands import RecordGasTest

ISO = {
    "point_text": "Pump P-101 breaker",
    "energy": "electrical",
    "method": "Lock and tag",
    "lock_number": "L-12",
    "tag_number": "T-12",
}


def raises(error: type[BaseException], world: World, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def record(world: World, permit: str, who: str = "uma", **more: Any) -> str:
    fields: dict[str, Any] = {"permit": permit, "instrument_text": "MX6", "o2_pct": "20.9"}
    return str(world.call(who, "RecordGasTest", **{**fields, **more}).stream_id)


def refused(error: type[BaseException], world: World, permit: str) -> str:
    return raises(
        error, world, "uma", "RecordGasTest", permit=permit, instrument_text="MX6", o2_pct="20.9"
    )


def result_of(world: World, gas: str) -> str:
    return str(world.scalar("SELECT result FROM cur_permits_gas_test WHERE id = :i", i=gas))


def live_hot(world: World) -> str:
    """A hot work permit made Active on a passing test."""
    permit = world.approved("hot_work")
    record(world, permit)
    world.at += timedelta(minutes=1)
    world.issue(permit)
    assert world.state(permit) == "Active"
    return permit


# --- the result is computed from the five limits ------------------------------------------------

AT_AND_AROUND = [
    ("o2_pct", "19.5", "pass"),
    ("o2_pct", "19.4", "fail"),
    ("o2_pct", "19.6", "pass"),
    ("o2_pct", "23.5", "pass"),
    ("o2_pct", "23.4", "pass"),
    ("o2_pct", "23.6", "fail"),
    ("lel_pct", "5", "pass"),
    ("lel_pct", "4.9", "pass"),
    ("lel_pct", "5.1", "fail"),
    ("h2s_ppm", "5", "pass"),
    ("h2s_ppm", "4.9", "pass"),
    ("h2s_ppm", "5.1", "fail"),
    ("co_ppm", "25", "pass"),
    ("co_ppm", "24.9", "pass"),
    ("co_ppm", "25.1", "fail"),
]


@pytest.mark.parametrize(("field", "value", "expected"), AT_AND_AROUND)
def test_a_reading_at_just_under_and_just_over_each_limit(
    world: World, field: str, value: str, expected: str
) -> None:
    permit = world.approved("hot_work")
    made = world.call(
        "uma", "RecordGasTest", permit=permit, instrument_text="MX6", **{field: value}
    )
    gas = str(made.stream_id)
    assert result_of(world, gas) == expected
    stored = world.rows("SELECT * FROM cur_permits_gas_test WHERE id = :i", i=gas)[0]
    assert float(stored[field]) == float(value)


def test_one_bad_reading_among_good_ones_fails_the_test(world: World) -> None:
    permit = world.approved("hot_work")
    good = record(world, permit, lel_pct="0", h2s_ppm="0", co_ppm="2")
    bad = record(world, permit, lel_pct="0", h2s_ppm="0", co_ppm="26")
    assert (result_of(world, good), result_of(world, bad)) == ("pass", "fail")


def test_a_gas_test_is_a_numbered_record_with_the_tester_and_the_time(world: World) -> None:
    permit = world.approved("hot_work")
    made = world.call(
        "rob",
        "RecordGasTest",
        permit=permit,
        instrument_text="MX6",
        o2_pct="20.9",
        co_ppm="2",
        note="Top of the tank",
    )
    assert made.key == "P123-GAS-0001"
    row = world.rows("SELECT * FROM cur_permits_gas_test WHERE id = :i", i=made.stream_id)[0]
    assert (row["permit_id"], row["tester"], row["instrument_text"]) == (permit, "user:rob", "MX6")
    assert row["note"] == "Top of the tank" and row["lel_pct"] is None
    assert str(row["taken_at"])[:19].replace(" ", "T") == "2026-12-01T07:00:00"
    second = world.call("uma", "RecordGasTest", permit=permit, instrument_text="MX6", co_ppm="1")
    assert second.key == "P123-GAS-0002"


def test_a_taken_at_in_the_past_is_kept(world: World) -> None:
    permit = world.approved("hot_work")
    gas = record(world, permit, taken_at=world.at - timedelta(minutes=30))
    row = world.rows("SELECT taken_at FROM cur_permits_gas_test WHERE id = :i", i=gas)[0]
    assert str(row["taken_at"])[:19].replace(" ", "T") == "2026-12-01T06:30:00"


# --- the fields -----------------------------------------------------------------------------------


def _model(**more: Any) -> RecordGasTest:
    base: dict[str, Any] = {
        "actor": "user:uma",
        "source": "t",
        "scope": SCOPE,
        "permit": "01JX",
        "instrument_text": "MX6",
        "o2_pct": "20.9",
    }
    return RecordGasTest(**{**base, **more})


def test_a_result_field_is_refused_as_an_unknown_field() -> None:
    _model()
    with pytest.raises(ValidationError) as caught:
        _model(result="pass")
    assert "result" in str(caught.value) and "extra" in str(caught.value).lower()


@pytest.mark.parametrize(
    "bad",
    [
        {"o2_pct": None},  # no reading at all
        {"o2_pct": "-0.1"},
        {"o2_pct": "100.1"},
        {"lel_pct": "100.1"},
        {"h2s_ppm": "100001"},
        {"co_ppm": "-1"},
        {"co_ppm": "1.2345"},
        {"co_ppm": "NaN"},
        {"co_ppm": "Infinity"},
        {"instrument_text": ""},
        {"instrument_text": "  "},
        {"instrument_text": "x" * 65},
        {"note": "x" * 301},
        {"taken_at": "2026-12-01T06:00:00"},  # no zone
        {"recorded_by": "user:x"},
        {"tester": "user:x"},
    ],
)
def test_the_readings_and_texts_are_bounded(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _model(**bad)


def test_the_bounds_themselves_are_allowed() -> None:
    model = _model(
        o2_pct="0", lel_pct="100", h2s_ppm="100000", co_ppm="0.001", instrument_text="x" * 64
    )
    assert model.lel_pct == "100" and model.co_ppm == "0.001"
    assert _model(o2_pct=None, co_ppm="3").o2_pct is None


# --- the clock ------------------------------------------------------------------------------------


def test_a_test_dated_in_the_future_is_refused(world: World) -> None:
    permit = world.approved("hot_work")
    message = raises(
        GasTestRuleError,
        world,
        "uma",
        "RecordGasTest",
        permit=permit,
        instrument_text="MX6",
        o2_pct="20.9",
        taken_at=world.at + timedelta(seconds=1),
    )
    assert message == MSG_FUTURE
    assert world.count("cur_permits_gas_test") == 0
    record(world, permit, taken_at=world.at)  # exactly now is not the future


def test_the_time_is_compared_in_utc_whatever_the_zone_sent(world: World) -> None:
    permit = world.approved("hot_work")
    east = timezone(timedelta(hours=1))
    raises(
        GasTestRuleError,
        world,
        "uma",
        "RecordGasTest",
        permit=permit,
        instrument_text="MX6",
        o2_pct="20.9",
        taken_at=datetime(2026, 12, 1, 8, 30, tzinfo=east),  # 07:30 UTC, after 07:00
    )
    record(world, permit, taken_at=datetime(2026, 12, 1, 7, 59, tzinfo=east))  # 06:59 UTC


# --- which permits take a test ---


def test_a_permit_that_is_not_yet_approved_or_is_over_takes_no_test(world: World) -> None:
    requested = world.request(permit_type="hot_work")
    message = refused(PermitStateError, world, requested)
    assert "needs Approved or Active or Lapsed or Suspended" in message
    cancelled = world.approved("hot_work")
    world.call("pam", "CancelPermit", permit=cancelled, reason="Moved")
    refused(PermitStateError, world, cancelled)
    ended = live_hot(world)
    world.call("rob", "HandBackPermit", permit=ended, handback_note="Site clear")
    refused(PermitStateError, world, ended)
    world.call("pam", "ClosePermit", permit=ended)
    refused(PermitStateError, world, ended)
    assert world.count("cur_permits_gas_test") == 1  # the one that made `ended` Active


@pytest.mark.parametrize("stage", ["Approved", "Active", "Lapsed", "Suspended"])
def test_a_permit_in_a_live_stage_takes_a_test(world: World, stage: str) -> None:
    permit = world.approved("hot_work") if stage == "Approved" else live_hot(world)
    if stage == "Lapsed":
        world.at = world.at.replace(hour=19)
    if stage == "Suspended":
        world.call("uma", "SuspendPermit", permit=permit, reason="Stop")
    assert result_of(world, record(world, permit)) == "pass"


def test_a_hidden_or_missing_permit_answers_one_text(world: World) -> None:
    secret = world.hidden_record()
    hidden = world.request("dora", "hot_work", for_record_id=secret)
    isolation = str(world.call("uma", "ApplyIsolation", **ISO).stream_id)
    texts = {
        refused(RecordNotFoundError, world, ref)
        for ref in (hidden, "01JXXXXXXXXXXXXXXXXXXXXXXX", isolation)
    }
    assert texts == {"no record with that id"}
    assert world.count("cur_permits_gas_test") == 0


# --- the safety rule ---


def suspensions(world: World, permit: str) -> list[dict[str, Any]]:
    return world.rows(
        "SELECT actor, payload FROM events "
        "WHERE stream_id = :s AND event_type = 'Permit.Suspended'",
        s=permit,
    )


def test_a_failing_test_suspends_an_active_permit_that_needs_gas_testing(world: World) -> None:
    permit = live_hot(world)
    gas = record(world, permit, "rob", co_ppm="40")
    assert result_of(world, gas) == "fail" and world.state(permit) == "Suspended"
    (event,) = suspensions(world, permit)
    raw = event["payload"]
    payload = json.loads(raw) if isinstance(raw, str) else raw
    assert payload["reason"] == "gas test failed" and payload["gas_test_id"] == gas
    assert event["actor"] == "user:rob"


def test_the_suspend_and_the_test_are_one_unit_of_work(world: World) -> None:
    permit = live_hot(world)
    made = world.call("uma", "RecordGasTest", permit=permit, instrument_text="MX6", lel_pct="50")
    kinds = [e.event_type for e in made.events]
    assert "GasTest.Recorded" in kinds and "Permit.Suspended" in kinds
    assert len({e.correlation_id for e in made.events}) == 1


def test_a_failing_test_suspends_a_lapsed_permit_too(world: World) -> None:
    permit = live_hot(world)
    world.at = world.at.replace(hour=19)
    record(world, permit, h2s_ppm="9")
    assert world.state(permit) == "Suspended"


def test_a_failing_test_of_a_type_that_needs_none_records_only(world: World) -> None:
    permit = world.active("general")
    gas = record(world, permit, lel_pct="50")
    assert result_of(world, gas) == "fail"
    assert world.state(permit) == "Active" and suspensions(world, permit) == []


def test_a_failing_test_of_an_approved_or_suspended_permit_records_only(world: World) -> None:
    approved = world.approved("hot_work")
    record(world, approved, co_ppm="99")
    assert world.state(approved) == "Approved" and suspensions(world, approved) == []
    active = live_hot(world)
    world.call("uma", "SuspendPermit", permit=active, reason="Stop")
    record(world, active, co_ppm="99")
    assert world.state(active) == "Suspended" and len(suspensions(world, active)) == 1


def test_a_passing_test_never_suspends(world: World) -> None:
    permit = live_hot(world)
    record(world, permit, lel_pct="0", co_ppm="1")
    assert world.state(permit) == "Active" and suspensions(world, permit) == []


def test_a_suspended_permit_fails_resume_until_a_fresh_pass(world: World) -> None:
    permit = live_hot(world)
    record(world, permit, co_ppm="40")
    assert "gas_test_failed" in raises(
        PermitBlockedError, world, "pam", "ResumePermit", permit=permit
    )
    world.at += timedelta(minutes=1)
    record(world, permit, co_ppm="2")
    world.call("pam", "ResumePermit", permit=permit)
    assert world.state(permit) == "Active"


def test_a_pass_dated_before_the_fail_does_not_clear_it(world: World) -> None:
    permit = live_hot(world)
    record(world, permit, co_ppm="40")
    world.at += timedelta(minutes=2)
    record(world, permit, co_ppm="2", taken_at=world.at - timedelta(minutes=10))  # older pass
    assert "gas_test_failed" in raises(
        PermitBlockedError, world, "pam", "ResumePermit", permit=permit
    )
