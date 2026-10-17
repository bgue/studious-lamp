"""Comparing two snapshots: date shifts, float erosion, logic, progress, critical path (T06)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from tl_adapters.db import open_uow
from tl_mod_schedule import compare, registry
from tl_mod_schedule.compare import SnapshotData
from tl_mod_schedule.compare import compare as compare_snapshots
from tl_mod_schedule.registry import ActivityRow, RelationshipRow
from tl_mod_schedule.testing import ScheduleWorld


def act(activity_id: str, **more: object) -> ActivityRow:
    base = ActivityRow(
        snapshot_id="s",
        activity_id=activity_id,
        task_id=activity_id,
        name=f"Activity {activity_id}",
        wbs_id="1",
        wbs_path="P > W",
        task_type="task",
        status="not_started",
        calendar_id="1",
        original_duration_hr=80.0,
        remaining_duration_hr=80.0,
        early_start="2026-10-05T08:00",
        early_finish="2026-10-16T16:00",
        late_start="2026-10-12T08:00",
        late_finish="2026-10-23T16:00",
        actual_start=None,
        actual_finish=None,
        target_start="2026-10-05T08:00",
        target_finish="2026-10-16T16:00",
        total_float_hr=40.0,
        free_float_hr=40.0,
        percent_complete=0.0,
        percent_type="CP_Drtn",
        constraint_type=None,
        constraint_date=None,
        critical=False,
        longest_path=False,
        seq=1,
    )
    return replace(base, **more)  # type: ignore[arg-type]


def rel(pred: str, succ: str, kind: str = "FS", lag: float = 0.0) -> RelationshipRow:
    return RelationshipRow("s", pred, succ, kind, lag, 1)


def snap(
    key: str,
    number: int,
    data_date: str,
    activities: list[ActivityRow],
    rels: list[RelationshipRow] | None = None,
    day_hours: dict[str, float] | None = None,
) -> SnapshotData:
    return SnapshotData(
        key,
        number,
        data_date,
        {a.activity_id: a for a in activities},
        rels or [],
        day_hours or {"1": 8.0},
    )


OLD = "2026-10-05T08:00"
NEW = "2026-10-12T08:00"


def test_nothing_changed_is_an_empty_comparison() -> None:
    a = snap("M#1", 1, OLD, [act("A1")], [rel("A1", "A2")])
    result = compare_snapshots(a, snap("M#2", 2, NEW, [act("A1")], [rel("A1", "A2")]))
    assert result.data_date_shift_days == 7
    assert all(result.totals[name] == 0 for name in compare.LIST_FIELDS)
    assert result.old.key == "M#1" and result.new.key == "M#2"


def test_added_and_removed_activities_are_the_ones_only_one_snapshot_has() -> None:
    old = snap("M#1", 1, OLD, [act("A1"), act("A2", critical=True, total_float_hr=0.0)])
    new = snap("M#2", 2, NEW, [act("A1"), act("A3", total_float_hr=16.0)])
    result = compare_snapshots(old, new)
    assert [a.activity_id for a in result.added] == ["A3"]
    assert [a.activity_id for a in result.removed] == ["A2"]
    assert result.added[0].total_float_days == 2.0 and result.removed[0].critical is True
    # a removed critical activity left the critical set; nothing else changed
    assert [(c.activity_id, c.direction) for c in result.critical_changes] == [("A2", "left")]


def test_a_date_shift_is_in_calendar_days_and_positive_is_later() -> None:
    old = snap("M#1", 1, OLD, [act("A1"), act("A2")])
    new = snap(
        "M#2",
        2,
        NEW,
        [
            act("A1", early_finish="2026-10-23T16:00", late_finish="2026-10-21T16:00"),
            act("A2"),
        ],
    )
    [shift] = compare_snapshots(old, new).date_shifts
    assert shift.activity_id == "A1"
    assert {s.field: s.shift_days for s in shift.shifts} == {"early_finish": 7, "late_finish": -2}
    assert (shift.largest_days, shift.finish_shift_days, shift.start_shift_days) == (7, 7, None)


def test_the_time_of_day_does_not_make_a_shift() -> None:
    old = snap("M#1", 1, OLD, [act("A1", early_start="2026-10-05T08:00")])
    new = snap("M#2", 2, NEW, [act("A1", early_start="2026-10-06T07:00")])
    [shift] = compare_snapshots(old, new).date_shifts
    assert shift.shifts[0].shift_days == 1


def test_a_date_that_appears_has_no_shift_but_is_listed() -> None:
    old = snap("M#1", 1, OLD, [act("A1")])
    new = snap("M#2", 2, NEW, [act("A1", actual_start="2026-10-06T08:00", status="in_progress")])
    [shift] = compare_snapshots(old, new).date_shifts
    [moved] = shift.shifts
    assert (moved.field, moved.old, moved.new, moved.shift_days) == (
        "actual_start", None, "2026-10-06T08:00", None,
    )  # fmt: skip
    assert shift.largest_days == 0


def test_date_shifts_are_ordered_by_size_then_activity_id() -> None:
    old = snap("M#1", 1, OLD, [act("A1"), act("A2"), act("A3")])
    new = snap(
        "M#2",
        2,
        NEW,
        [
            act("A1", early_finish="2026-10-17T16:00"),
            act("A2", early_finish="2026-10-26T16:00"),
            act("A3", early_finish="2026-10-17T16:00"),
        ],
    )
    assert [s.activity_id for s in compare_snapshots(old, new).date_shifts] == ["A2", "A1", "A3"]


def test_float_erosion_is_in_days_of_the_activitys_own_calendar() -> None:
    old = snap(
        "M#1",
        1,
        OLD,
        [act("A1", total_float_hr=72.0), act("A2", total_float_hr=80.0)],
        day_hours={"1": 8.0},
    )
    new = snap(
        "M#2",
        2,
        NEW,
        [act("A1", total_float_hr=32.0), act("A2", total_float_hr=100.0)],
        day_hours={"1": 10.0},
    )
    changes = {c.activity_id: c for c in compare_snapshots(old, new).float_changes}
    assert (changes["A1"].old_days, changes["A1"].new_days, changes["A1"].delta_days) == (
        9.0,
        3.2,
        -5.8,
    )
    assert changes["A1"].eroded is True
    assert (changes["A2"].old_days, changes["A2"].new_days, changes["A2"].delta_days) == (
        10.0,
        10.0,
        0.0,
    )
    assert (
        changes["A2"].eroded is False
    )  # the hours differ, the days do not (different day lengths)


def test_floats_are_ordered_most_eroded_first_and_unknowns_last() -> None:
    old = snap(
        "M#1",
        1,
        OLD,
        [
            act("A1", total_float_hr=80.0),
            act("A2", total_float_hr=80.0),
            act("A3", total_float_hr=None),
        ],
    )
    new = snap(
        "M#2",
        2,
        NEW,
        [
            act("A1", total_float_hr=72.0),
            act("A2", total_float_hr=16.0),
            act("A3", total_float_hr=8.0),
        ],
    )
    result = compare_snapshots(old, new)
    assert [c.activity_id for c in result.float_changes] == ["A2", "A1", "A3"]
    assert result.float_changes[-1].old_days is None and result.float_changes[-1].delta_days is None
    assert result.totals["eroded"] == 2


def test_a_float_difference_below_the_rounding_of_p6_is_not_a_change() -> None:
    old = snap("M#1", 1, OLD, [act("A1", total_float_hr=72.0)])
    new = snap("M#2", 2, NEW, [act("A1", total_float_hr=72.004)])
    assert compare_snapshots(old, new).float_changes == ()


def test_logic_changes_are_added_removed_and_changed_relationships() -> None:
    old = snap(
        "M#1", 1, OLD, [act("A1")], [rel("A1", "A2"), rel("A2", "A3"), rel("A3", "A4", "FS", 0.0)]
    )
    new = snap(
        "M#2", 2, NEW, [act("A1")], [rel("A1", "A2"), rel("A1", "A3"), rel("A3", "A4", "SS", 16.0)]
    )
    kinds = [
        (c.kind, c.pred_activity_id, c.succ_activity_id)
        for c in compare_snapshots(old, new).logic_changes
    ]
    assert kinds == [("removed", "A2", "A3"), ("added", "A1", "A3"), ("changed", "A3", "A4")]
    changed = compare_snapshots(old, new).logic_changes[2]
    assert (changed.old_type, changed.new_type, changed.old_lag_hr, changed.new_lag_hr) == (
        "FS",
        "SS",
        0.0,
        16.0,
    )


def test_progress_is_percent_status_and_remaining_duration() -> None:
    old = snap(
        "M#1",
        1,
        OLD,
        [
            act("A1", percent_complete=40.0, status="in_progress", remaining_duration_hr=48.0),
            act("A2"),
        ],
    )
    new = snap(
        "M#2", 2, NEW,
        [
            act("A1", percent_complete=100.0, status="completed", remaining_duration_hr=0.0),
            act("A2", remaining_duration_hr=40.0),
        ],
    )  # fmt: skip
    changes = {c.activity_id: c for c in compare_snapshots(old, new).progress_changes}
    assert (changes["A1"].delta_percent, changes["A1"].old_status, changes["A1"].new_status) == (
        60.0,
        "in_progress",
        "completed",
    )
    assert (changes["A1"].old_remaining_days, changes["A1"].new_remaining_days) == (6.0, 0.0)
    assert changes["A2"].delta_percent == 0.0 and changes["A2"].new_remaining_days == 5.0


def test_a_change_of_original_duration_is_reported_in_days() -> None:
    old = snap("M#1", 1, OLD, [act("A1", original_duration_hr=80.0)])
    new = snap("M#2", 2, NEW, [act("A1", original_duration_hr=96.0)])
    [change] = compare_snapshots(old, new).duration_changes
    assert (change.old_days, change.new_days) == (10.0, 12.0)


def test_the_critical_set_entered_and_left() -> None:
    old = snap(
        "M#1",
        1,
        OLD,
        [act("A1", critical=True, total_float_hr=0.0), act("A2", total_float_hr=32.0)],
    )
    new = snap(
        "M#2",
        2,
        NEW,
        [act("A1", total_float_hr=16.0), act("A2", critical=True, total_float_hr=-8.0)],
    )
    changes = [
        (c.activity_id, c.direction, c.old_float_days, c.new_float_days)
        for c in compare_snapshots(old, new).critical_changes
    ]
    assert changes == [("A2", "entered", 4.0, -1.0), ("A1", "left", 0.0, 2.0)]


def test_a_new_critical_activity_entered_the_critical_set() -> None:
    old = snap("M#1", 1, OLD, [act("A1")])
    new = snap("M#2", 2, NEW, [act("A1"), act("A9", critical=True, total_float_hr=-16.0)])
    [change] = compare_snapshots(old, new).critical_changes
    assert (change.activity_id, change.direction, change.old_float_days, change.new_float_days) == (
        "A9", "entered", None, -2.0,
    )  # fmt: skip


def test_the_latest_finish_is_a_stand_in_for_the_project_finish() -> None:
    old = snap(
        "M#1", 1, OLD, [act("A1", early_finish="2026-12-03T16:00"), act("A2", early_finish=None)]
    )
    new = snap("M#2", 2, NEW, [act("A1", early_finish="2026-12-07T16:00")])
    result = compare_snapshots(old, new)
    assert (result.latest_finish_old, result.latest_finish_new, result.finish_shift_days) == (
        "2026-12-03T16:00", "2026-12-07T16:00", 4,
    )  # fmt: skip
    empty = compare_snapshots(
        snap("a", 1, OLD, [act("A", early_finish=None)]), snap("b", 2, NEW, [])
    )
    assert empty.finish_shift_days is None


def test_the_comparison_does_not_depend_on_the_order_of_the_input() -> None:
    a1, a2, a3 = (
        act("A1", total_float_hr=8.0),
        act("A2", total_float_hr=16.0),
        act("A3", total_float_hr=24.0),
    )
    b1, b2, b3 = (
        replace(a, total_float_hr=0.0, early_finish="2026-10-20T16:00") for a in (a1, a2, a3)
    )
    one = compare_snapshots(snap("a", 1, OLD, [a1, a2, a3]), snap("b", 2, NEW, [b1, b2, b3]))
    two = compare_snapshots(snap("a", 1, OLD, [a3, a1, a2]), snap("b", 2, NEW, [b2, b3, b1]))
    assert one == two


def test_limited_cuts_every_list_and_keeps_the_totals() -> None:
    old = snap("M#1", 1, OLD, [act(f"A{i}") for i in range(10)])
    new = snap("M#2", 2, NEW, [act(f"A{i}", early_finish="2026-10-30T16:00") for i in range(10)])
    full = compare_snapshots(old, new)
    cut = full.limited(3)
    assert len(cut.date_shifts) == 3 and cut.cut is True
    assert cut.totals == full.totals and cut.totals["date_shifts"] == 10
    assert full.limited(10).cut is False and len(full.limited(10).date_shifts) == 10


# --- the demo's two files, through the database ---------------------------------------------------


def loaded(world: ScheduleWorld, a: str, b: str) -> compare.Comparison:
    with open_uow(world.db, readonly=True) as uow:
        rows = [registry.get_snapshot(uow.conn(), i) for i in (a, b)]
        old, new = (compare.load(uow.conn(), r) for r in rows if r is not None)
    return compare_snapshots(old, new)


def test_the_demo_week_shows_slips_float_erosion_and_a_new_critical_path(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    result = loaded(world, one, two)
    assert result.data_date_shift_days == 7
    assert [a.activity_id for a in result.added] == ["A2500"]
    assert [a.activity_id for a in result.removed] == ["A1990"]
    floats = {c.activity_id: c for c in result.float_changes}
    assert (floats["A1230"].old_days, floats["A1230"].new_days, floats["A1230"].delta_days) == (
        9.0,
        4.0,
        -5.0,
    )
    assert floats["A1230"].eroded is True
    assert result.float_changes[0].activity_id in {
        "A1110",
        "A1120",
        "A1250",
        "A1260",
        "A1270",
        "A1290",
        "A1300",
    }
    shifts = {s.activity_id: s for s in result.date_shifts}
    assert shifts["A1230"].finish_shift_days == 7
    fields = {s.field: s.shift_days for s in shifts["A1230"].shifts}
    assert (
        fields["early_finish"] == 7 and "late_finish" not in fields
    )  # the late date is the deadline's
    progress = {p.activity_id: p for p in result.progress_changes}
    assert (progress["A1140"].old_percent, progress["A1140"].new_percent) == (60.0, 80.0)
    logic = {(c.kind, c.pred_activity_id, c.succ_activity_id) for c in result.logic_changes}
    assert ("added", "A1120", "A1290") in logic and ("added", "A1230", "A2500") in logic
    assert ("removed", "A1200", "A1990") in logic
    entered = {c.activity_id for c in result.critical_changes if c.direction == "entered"}
    assert {"A1110", "A1120"} <= entered
    assert result.finish_shift_days is not None and result.finish_shift_days > 0


def test_a_snapshot_compared_with_itself_has_nothing_to_report(world: ScheduleWorld) -> None:
    world.define()
    one, _ = world.two_weeks()
    result = loaded(world, one, one)
    assert result.data_date_shift_days == 0
    assert all(result.totals[name] == 0 for name in compare.LIST_FIELDS)


@pytest.mark.parametrize("hours", [0.0, 4.0])
def test_zero_calendar_hours_do_not_divide_by_zero(hours: float) -> None:
    old = snap("M#1", 1, OLD, [act("A1", total_float_hr=80.0)], day_hours={"1": hours})
    new = snap("M#2", 2, NEW, [act("A1", total_float_hr=40.0)], day_hours={"1": hours})
    [change] = compare_snapshots(old, new).float_changes
    assert change.old_days is not None
