"""The pure permit rules (P2-PTW T00): shift end, effective state, gas result, issue blockers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from tl_mod_permits import rules as r


def at(h: int, m: int = 0, day: int = 10) -> datetime:
    return datetime(2026, 12, day, h, m, tzinfo=UTC)


# ---- shift_end -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "end"),
    [
        (at(6), at(18)),  # a shift start belongs to the new shift
        (at(9, 30), at(18)),
        (at(17, 59), at(18)),
        (at(18), at(6, day=11)),  # an end belongs to the next shift
        (at(23), at(6, day=11)),
        (at(0), at(6)),  # after midnight: the night shift that began the day before
        (at(5, 59), at(6)),
    ],
)
def test_twelve_hour_shifts_from_six(now: datetime, end: datetime) -> None:
    assert r.shift_end(now, "06:00", 12) == end


def test_eight_hour_shifts() -> None:
    assert r.shift_end(at(7), "06:00", 8) == at(14)
    assert r.shift_end(at(14), "06:00", 8) == at(22)
    assert r.shift_end(at(23), "06:00", 8) == at(6, day=11)
    assert r.shift_end(at(3), "06:00", 8) == at(6)


def test_last_shift_of_the_day_is_short_when_hours_do_not_divide_24() -> None:
    assert r.shift_end(at(7), "06:00", 10) == at(16)
    assert r.shift_end(at(17), "06:00", 10) == at(2, day=11)
    assert r.shift_end(at(3, day=11), "06:00", 10) == at(6, day=11)


def test_other_shift_start() -> None:
    assert r.shift_end(at(8), "07:30", 12) == at(19, 30)
    assert r.shift_end(at(7), "07:30", 12) == at(7, 30)


def test_shift_end_keeps_the_timezone_of_its_input() -> None:
    from datetime import timezone

    plus2 = timezone(timedelta(hours=2))
    now = datetime(2026, 12, 10, 9, 0, tzinfo=plus2)
    assert r.shift_end(now, "06:00", 12) == datetime(2026, 12, 10, 18, 0, tzinfo=plus2)


def test_shift_end_refuses_a_naive_time() -> None:
    with pytest.raises(ValueError):
        r.shift_end(datetime(2026, 12, 10, 9, 0), "06:00", 12)


@pytest.mark.parametrize(("start", "hours"), [("6:00", 12), ("24:00", 12), ("06:60", 12), ("06:00", 3), ("06:00", 25)])
def test_shift_end_refuses_bad_settings(start: str, hours: int) -> None:
    with pytest.raises(ValueError):
        r.shift_end(at(9), start, hours)


# ---- effective_state -------------------------------------------------------------------------


def test_active_before_valid_until_stays_active() -> None:
    assert r.effective_state("Active", at(18), at(17, 59)) == "Active"


def test_active_at_or_after_valid_until_is_lapsed() -> None:
    assert r.effective_state("Active", at(18), at(18)) == "Lapsed"
    assert r.effective_state("Active", at(18), at(23)) == "Lapsed"


def test_active_without_valid_until_fails_closed_as_lapsed() -> None:
    assert r.effective_state("Active", None, at(9)) == "Lapsed"


@pytest.mark.parametrize(
    "state", ["Requested", "Approved", "Rejected", "Suspended", "Handed back", "Closed", "Cancelled"]
)
def test_other_states_never_lapse(state: str) -> None:
    assert r.effective_state(state, at(1), at(23)) == state


def test_effective_state_refuses_naive_times() -> None:
    with pytest.raises(ValueError):
        r.effective_state("Active", datetime(2026, 12, 10, 18), at(9))


# ---- gas_result ------------------------------------------------------------------------------

LIMITS = r.GasLimits(
    o2_min_pct=D("19.5"), o2_max_pct=D("23.5"), lel_max_pct=D("5"), h2s_max_ppm=D("5"), co_max_ppm=D("25")
)


def test_all_in_limits_passes() -> None:
    assert r.gas_result(LIMITS, o2=D("20.9"), lel=D("0"), h2s=D("0"), co=D("2")) == "pass"


def test_limits_are_inclusive() -> None:
    assert r.gas_result(LIMITS, o2=D("19.5"), lel=D("5"), h2s=D("5"), co=D("25")) == "pass"
    assert r.gas_result(LIMITS, o2=D("23.5")) == "pass"


@pytest.mark.parametrize(
    "readings",
    [
        {"o2": D("19.4")},
        {"o2": D("23.6")},
        {"lel": D("5.1")},
        {"h2s": D("5.1")},
        {"co": D("25.1")},
        {"o2": D("20.9"), "lel": D("0"), "h2s": D("0"), "co": D("26")},
    ],
)
def test_any_reading_out_of_limits_fails(readings: dict[str, D]) -> None:
    assert r.gas_result(LIMITS, **readings) == "fail"


def test_unmeasured_readings_are_not_tested() -> None:
    assert r.gas_result(LIMITS, lel=D("1")) == "pass"
    assert r.gas_result(LIMITS, o2=None, lel=D("1"), h2s=None, co=None) == "pass"


def test_no_readings_at_all_is_an_error() -> None:
    with pytest.raises(ValueError):
        r.gas_result(LIMITS)


def test_negative_reading_is_an_error() -> None:
    with pytest.raises(ValueError):
        r.gas_result(LIMITS, lel=D("-1"))


def test_limits_come_from_the_caller_not_from_the_module() -> None:
    tight = r.GasLimits(
        o2_min_pct=D("20"), o2_max_pct=D("21"), lel_max_pct=D("1"), h2s_max_ppm=D("1"), co_max_ppm=D("1")
    )
    assert r.gas_result(tight, o2=D("19.9")) == "fail"
    assert r.gas_result(LIMITS, o2=D("19.9")) == "pass"


# ---- issue_blockers --------------------------------------------------------------------------

NOW = at(10)


def blockers(**kw: object) -> list[str]:
    args: dict[str, object] = {
        "needs_gas_test": False,
        "needs_isolation": False,
        "required_precautions": ["p1", "p2"],
        "ticked_precautions": ["p1", "p2"],
        "gas_tests": [],
        "isolation_states": [],
        "gas_valid_minutes": 240,
        "now": NOW,
    }
    args.update(kw)
    return r.issue_blockers(**args)  # type: ignore[arg-type]


def test_nothing_needed_and_all_ticked_has_no_blockers() -> None:
    assert blockers() == []


def test_unticked_precautions_are_named_in_the_type_order() -> None:
    assert blockers(ticked_precautions=["p2"]) == ["precaution_unticked:p1"]
    assert blockers(ticked_precautions=[]) == ["precaution_unticked:p1", "precaution_unticked:p2"]


def test_unknown_ticked_ids_are_ignored() -> None:
    assert blockers(ticked_precautions=["p1", "p2", "zz"]) == []


def test_gas_test_missing() -> None:
    assert blockers(needs_gas_test=True) == ["gas_test_missing"]


def test_gas_test_fresh_pass_is_enough() -> None:
    tests = [(NOW - timedelta(minutes=240), "pass")]
    assert blockers(needs_gas_test=True, gas_tests=tests) == []


def test_gas_test_older_than_the_setting_is_stale() -> None:
    tests = [(NOW - timedelta(minutes=241), "pass")]
    assert blockers(needs_gas_test=True, gas_tests=tests) == ["gas_test_stale"]


def test_newest_test_decides_a_later_fail_blocks_an_earlier_pass() -> None:
    tests = [(NOW - timedelta(minutes=60), "pass"), (NOW - timedelta(minutes=5), "fail")]
    assert blockers(needs_gas_test=True, gas_tests=tests) == ["gas_test_failed"]


def test_a_later_pass_clears_an_earlier_fail_whatever_the_list_order() -> None:
    tests = [(NOW - timedelta(minutes=5), "pass"), (NOW - timedelta(minutes=60), "fail")]
    assert blockers(needs_gas_test=True, gas_tests=tests) == []


def test_gas_tests_are_ignored_when_the_type_needs_none() -> None:
    assert blockers(gas_tests=[(NOW - timedelta(days=9), "fail")]) == []


def test_isolation_missing_when_none_linked_or_all_removed() -> None:
    assert blockers(needs_isolation=True) == ["isolation_missing"]
    assert blockers(needs_isolation=True, isolation_states=["Removed"]) == ["isolation_missing"]


def test_isolation_unverified_when_any_live_one_is_not_verified() -> None:
    assert blockers(needs_isolation=True, isolation_states=["Verified", "Applied"]) == ["isolation_unverified"]
    assert blockers(needs_isolation=True, isolation_states=["Applied"]) == ["isolation_unverified"]


def test_isolation_ok_when_every_live_one_is_verified_removed_ones_ignored() -> None:
    assert blockers(needs_isolation=True, isolation_states=["Verified", "Removed"]) == []


def test_blockers_order_is_gas_then_isolation_then_precautions() -> None:
    got = blockers(needs_gas_test=True, needs_isolation=True, ticked_precautions=["p2"])
    assert got == ["gas_test_missing", "isolation_missing", "precaution_unticked:p1"]
