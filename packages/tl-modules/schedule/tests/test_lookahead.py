"""The look-ahead of a snapshot: what is under way and what starts inside the window (T08)."""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_mod_schedule import registry
from tl_mod_schedule.lookahead import (
    MAX_WEEKS,
    LookAhead,
    build_look_ahead,
    look_ahead,
)
from tl_mod_schedule.registry import SnapshotRow
from tl_mod_schedule.testing import ScheduleWorld
from tl_mod_schedule.testing import make_activity as act

DATA_DATE = "2026-10-05T08:00"


def snapshot(data_date: str | None = DATA_DATE) -> SnapshotRow:
    return SnapshotRow(
        id="s", scope="project:P123", key="MAIN#1", state="Valid", schedule_id="x",
        schedule_code="MAIN", number=1, p6_project_option=None, source_file_id=None,
        source_name=None, source_sha256=None, source_size=None, requested_by=None, attempts=1,
        last_error=None, data_date=data_date, p6_version="20.12", p6_project="P", activity_count=0,
        relationship_count=0, wbs_count=0, calendar_count=0, code_count=0, udf_count=0,
        error_count=0, warning_count=0, report_file_id=None, raw_file_id=None, typed_sha256=None,
        raw_sha256=None, built_at=None, published_at=None,
    )  # fmt: skip


def listed(result: LookAhead) -> list[str]:
    return [r.activity_id for r in result.rows]


def test_the_window_runs_from_the_data_date_for_the_weeks_asked() -> None:
    result = build_look_ahead(snapshot(), [], {}, weeks=3)
    assert (result.window_start, result.window_end, result.weeks) == ("2026-10-05", "2026-10-26", 3)
    assert (result.snapshot_key, result.snapshot_number, result.data_date) == (
        "MAIN#1",
        1,
        DATA_DATE,
    )
    assert result.rows == () and dict(result.counts) == {
        "in_progress": 0, "late_start": 0, "starting": 0, "critical": 0, "total": 0,
    }  # fmt: skip


def test_the_default_window_is_four_weeks() -> None:
    assert build_look_ahead(snapshot(), [], {}).window_end == "2026-11-02"


def test_an_activity_is_listed_when_it_starts_on_or_before_the_last_day_of_the_window() -> None:
    inside = act("IN", early_start="2026-10-26T08:00")  # the last day of a three week window
    outside = act("OUT", early_start="2026-10-27T08:00")
    result = build_look_ahead(snapshot(), [outside, inside], {}, weeks=3)
    assert listed(result) == ["IN"]


def test_the_phase_says_why_an_activity_is_listed() -> None:
    running = act(
        "RUN", status="in_progress", early_start="2026-09-24T08:00", percent_complete=40.0
    )
    late = act("LATE", early_start="2026-10-01T08:00")
    soon = act("SOON", early_start="2026-10-12T08:00")
    on_day = act("DAY", early_start="2026-10-05T16:00")  # the data date's own day is not late
    result = build_look_ahead(snapshot(), [soon, late, running, on_day], {})
    assert {r.activity_id: r.phase for r in result.rows} == {
        "RUN": "in_progress", "LATE": "late_start", "SOON": "starting", "DAY": "starting",
    }  # fmt: skip
    assert dict(result.counts) == {
        "in_progress": 1, "late_start": 1, "starting": 2, "critical": 0, "total": 4,
    }  # fmt: skip


def test_completed_summary_and_dateless_activities_are_not_listed() -> None:
    rows = [
        act("DONE", status="completed", early_start="2026-09-01T08:00"),
        act("LOE", task_type="level_of_effort"),
        act("WBS", task_type="wbs_summary"),
        act("NODATE", early_start=None),
        act("TASK"),
        act("MILE", task_type="finish_milestone"),
        act("RES", task_type="resource_dependent"),
    ]
    assert sorted(listed(build_look_ahead(snapshot(), rows, {}))) == ["MILE", "RES", "TASK"]


def test_rows_are_ordered_by_early_start_then_critical_first_then_activity_id() -> None:
    rows = [
        act("C", early_start="2026-10-12T08:00"),
        act("B", early_start="2026-10-06T08:00"),
        act("A2", early_start="2026-10-12T08:00", critical=True),
        act("A1", early_start="2026-10-12T08:00"),
        act("Z", early_start="2026-10-05T08:00"),
    ]
    assert listed(build_look_ahead(snapshot(), rows, {})) == ["Z", "B", "A2", "A1", "C"]


def test_the_order_does_not_depend_on_the_order_of_the_input() -> None:
    rows = [act(f"A{i}", early_start=f"2026-10-{6 + i % 3:02d}T08:00") for i in range(9)]
    assert build_look_ahead(snapshot(), rows, {}) == build_look_ahead(snapshot(), rows[::-1], {})


def test_float_is_in_days_of_the_activitys_own_calendar_and_eight_hours_when_unknown() -> None:
    rows = [
        act("A", total_float_hr=80.0, calendar_id="5day"),
        act("B", total_float_hr=80.0, calendar_id="long"),
        act("C", total_float_hr=80.0, calendar_id="unknown"),
        act("D", total_float_hr=None),
        act("E", total_float_hr=-8.0, critical=True),
    ]
    result = build_look_ahead(snapshot(), rows, {"5day": 8.0, "long": 10.0})
    floats = {r.activity_id: r.total_float_days for r in result.rows}
    assert floats == {"A": 10.0, "B": 8.0, "C": 10.0, "D": None, "E": -1.0}
    assert result.counts["critical"] == 1


def test_a_calendar_with_no_hours_counts_as_eight() -> None:
    [row] = build_look_ahead(snapshot(), [act("A", total_float_hr=16.0)], {"1": 0.0}).rows
    assert row.total_float_days == 2.0


def test_the_row_carries_the_facts_of_the_activity() -> None:
    [row] = build_look_ahead(
        snapshot(),
        [
            act(
                "A1230",
                name="Install",
                wbs_path="P > CON",
                percent_complete=40.0,
                status="in_progress",
            )
        ],
        {},
    ).rows
    assert (row.activity_id, row.name, row.wbs_path, row.status) == (
        "A1230",
        "Install",
        "P > CON",
        "in_progress",
    )
    assert (row.early_start, row.early_finish, row.percent_complete) == (
        "2026-10-05T08:00", "2026-10-16T16:00", 40.0,
    )  # fmt: skip


@pytest.mark.parametrize("weeks", [0, -1, MAX_WEEKS + 1, 100])
def test_weeks_outside_one_to_twenty_six_are_refused(weeks: int) -> None:
    with pytest.raises(ValueError, match="weeks must be between 1 and 26"):
        build_look_ahead(snapshot(), [], {}, weeks=weeks)


def test_the_smallest_and_largest_windows_are_allowed() -> None:
    assert build_look_ahead(snapshot(), [], {}, weeks=1).window_end == "2026-10-12"
    assert build_look_ahead(snapshot(), [], {}, weeks=MAX_WEEKS).weeks == MAX_WEEKS


def test_true_is_not_a_number_of_weeks() -> None:
    with pytest.raises(ValueError):
        build_look_ahead(snapshot(), [], {}, weeks=True)


def test_a_snapshot_with_no_data_date_has_no_window() -> None:
    with pytest.raises(ValueError, match="no data date"):
        build_look_ahead(snapshot(None), [], {})


def test_only_the_date_of_the_data_date_matters_not_the_time() -> None:
    early = build_look_ahead(
        snapshot("2026-10-05T00:00"), [act("A", early_start="2026-10-05T01:00")], {}
    )
    late = build_look_ahead(
        snapshot("2026-10-05T23:59"), [act("A", early_start="2026-10-05T01:00")], {}
    )
    assert early.rows == late.rows and early.window_start == late.window_start


# --- through the database -----------------------------------------------------------------------


def test_the_look_ahead_of_the_demos_snapshots(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    with open_uow(world.db, readonly=True) as uow:
        first = registry.get_snapshot(uow.conn(), one)
        second = registry.get_snapshot(uow.conn(), two)
        assert first is not None and second is not None
        four = look_ahead(uow.conn(), first, scope="project:P123")
        short = look_ahead(uow.conn(), first, weeks=1, scope="project:P123")
        later = look_ahead(uow.conn(), second, weeks=2, scope="project:P123")
    by_id = {r.activity_id: r for r in four.rows}
    assert by_id["A1230"].phase == "in_progress" and by_id["A1230"].total_float_days == 9.0
    assert "A1000" not in by_id  # complete
    assert by_id["A1140"].phase == "in_progress" and by_id["A1140"].critical is True
    assert short.counts["total"] <= four.counts["total"]
    assert (later.window_start, later.window_end) == ("2026-10-12", "2026-10-26")
    assert "A2500" in {r.activity_id for r in later.rows}
