"""The reads of the schedule module: schedules, snapshots, activities, comparison, links (P1-I4)."""

from __future__ import annotations

import pytest
from stubs import needs_t07, needs_t08
from tl_adapters.db import open_uow
from tl_mod_schedule import views
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    NoCurrentSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    SnapshotStateError,
)
from tl_mod_schedule.testing import BASE, ScheduleWorld

SCOPE = BASE["scope"]


def published_pair(world: ScheduleWorld) -> tuple[str, str]:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    world.publish(two)
    return one, two


def read(world: ScheduleWorld, function, *args, **kwargs):  # noqa: ANN001, ANN201
    with open_uow(world.db, readonly=True) as uow:
        return function(uow.conn(), SCOPE, *args, **kwargs)


# --- schedules and snapshots --------------------------------------------------------------------


def test_a_schedule_lists_its_snapshots_newest_first_with_the_one_before_each(
    world: ScheduleWorld,
) -> None:
    published_pair(world)
    [listed] = read(world, views.schedule_views)
    assert (listed.code, listed.current_snapshot_number, listed.snapshot_count) == ("MAIN", 2, 2)
    detail = read(world, views.schedule_detail, "MAIN")
    assert [(s.number, s.state, s.is_current, s.previous_number) for s in detail.snapshots] == [
        (2, "Published", True, 1),
        (1, "Superseded", False, None),
    ]
    assert detail.snapshots[0].data_date == "2026-10-12T08:00"
    assert detail.snapshots[0].activity_count and detail.snapshots[0].error_count == 0


def test_a_snapshot_is_read_by_number_or_as_the_current_one(world: ScheduleWorld) -> None:
    published_pair(world)
    assert read(world, views.snapshot_view, "MAIN", 1).state == "Superseded"
    assert read(world, views.snapshot_view, "MAIN", None).number == 2
    with pytest.raises(SnapshotNotFoundError):
        read(world, views.snapshot_view, "MAIN", 9)
    with pytest.raises(ScheduleNotFoundError):
        read(world, views.snapshot_view, "OTHER", 1)


def test_a_schedule_without_a_published_snapshot_has_no_current_one(world: ScheduleWorld) -> None:
    world.define()
    world.two_weeks()
    with pytest.raises(NoCurrentSnapshotError):
        read(world, views.snapshot_view, "MAIN", None)
    with pytest.raises(NoCurrentSnapshotError):
        read(world, views.activity_page, "MAIN")
    [listed] = read(world, views.schedule_views)
    assert (listed.current_snapshot_number, listed.snapshot_count) == (None, 2)


# --- activities -----------------------------------------------------------------------------------


def test_activities_are_paged_filtered_and_counted(world: ScheduleWorld) -> None:
    published_pair(world)
    everything = read(world, views.activity_page, "MAIN", None, limit=1000)
    assert everything.total == len(everything.rows) > 10
    assert (everything.snapshot_number, everything.offset) == (2, 0)
    first = read(world, views.activity_page, "MAIN", 2, limit=3)
    assert [a.activity_id for a in first.rows] == [a.activity_id for a in everything.rows[:3]]
    assert first.total == everything.total
    rest = read(world, views.activity_page, "MAIN", 2, limit=3, offset=3)
    assert [a.activity_id for a in rest.rows] == [a.activity_id for a in everything.rows[3:6]]
    critical = read(world, views.activity_page, "MAIN", 2, critical=True, limit=1000)
    assert critical.total and all(a.critical for a in critical.rows)
    assert {a.activity_id for a in critical.rows} >= {"A1110", "A1120"}
    done = read(world, views.activity_page, "MAIN", 2, status="completed", limit=1000)
    assert done.total and all(a.status == "completed" for a in done.rows)
    found = read(world, views.activity_page, "MAIN", 2, search="a1230")
    assert [a.activity_id for a in found.rows] == ["A1230"]
    by_name = read(world, views.activity_page, "MAIN", 2, search="PIPE RACK")
    assert "A1230" in {a.activity_id for a in by_name.rows}


def test_a_search_treats_percent_and_underscore_as_text(world: ScheduleWorld) -> None:
    published_pair(world)
    for term in ("%", "_", "\\", "A1%0", "A12_0"):
        assert read(world, views.activity_page, "MAIN", 2, search=term).total == 0, term


def test_a_page_is_bounded(world: ScheduleWorld) -> None:
    published_pair(world)
    assert len(read(world, views.activity_page, "MAIN", 2, limit=10**9).rows) <= views.MAX_PAGE
    assert len(read(world, views.activity_page, "MAIN", 2, limit=0).rows) == 1
    assert read(world, views.activity_page, "MAIN", 2, offset=-5).offset == 0


def test_a_snapshot_that_is_not_built_has_no_activities_to_read(world: ScheduleWorld) -> None:
    world.define()
    opened = world.open_snapshot()
    assert opened.stream_id
    with pytest.raises(SnapshotStateError):
        read(world, views.activity_page, "MAIN", 1)
    with pytest.raises(SnapshotStateError):
        read(world, views.activity_detail, "MAIN", "A1230", 1)


def test_one_activity_comes_with_what_precedes_and_follows_it(world: ScheduleWorld) -> None:
    published_pair(world)
    detail = read(world, views.activity_detail, "MAIN", "A1230")
    assert detail.snapshot_number == 2 and detail.activity.name.startswith("Install pipe rack")
    assert [r.pred_activity_id for r in detail.predecessors] == ["A1220"]
    assert {r.succ_activity_id for r in detail.successors} >= {"A1240", "A2500"}
    assert all(r.succ_activity_id == "A1230" for r in detail.predecessors)
    assert all(r.pred_activity_id == "A1230" for r in detail.successors)
    with pytest.raises(ActivityNotFoundError):
        read(world, views.activity_detail, "MAIN", "NOPE")
    # A1990 is only in the first snapshot
    assert read(world, views.activity_detail, "MAIN", "A1990", 1).activity.activity_id == "A1990"
    with pytest.raises(ActivityNotFoundError):
        read(world, views.activity_detail, "MAIN", "A1990", 2)


def test_the_float_trend_of_an_activity_is_one_point_per_published_snapshot(
    world: ScheduleWorld,
) -> None:
    published_pair(world)
    trend = read(world, views.float_trend, "MAIN", "A1230")
    assert [(p.snapshot_number, p.total_float_days) for p in trend] == [(1, 9.0), (2, 4.0)]
    assert [p.data_date for p in trend] == ["2026-10-05T08:00", "2026-10-12T08:00"]
    gone = read(world, views.float_trend, "MAIN", "A1990")
    assert [p.snapshot_number for p in gone] == [1]
    with pytest.raises(ActivityNotFoundError):
        read(world, views.float_trend, "MAIN", "NOPE")


def test_a_snapshot_that_is_not_published_is_not_in_the_trend(world: ScheduleWorld) -> None:
    world.define()
    one, _ = world.two_weeks()
    world.publish(one)
    assert [p.snapshot_number for p in read(world, views.float_trend, "MAIN", "A1230")] == [1]


# --- comparison, look-ahead, resolution -----------------------------------------------------


def test_the_default_comparison_is_the_current_snapshot_against_the_one_before(
    world: ScheduleWorld,
) -> None:
    published_pair(world)
    result = read(world, views.comparison, "MAIN")
    assert (result.old.number, result.new.number) == (1, 2)
    assert result.data_date_shift_days == 7
    erosion = {c.activity_id: (c.old_days, c.new_days) for c in result.float_changes}
    assert erosion["A1230"] == (9.0, 4.0)
    assert [b.activity_id for b in result.added] == ["A2500"]
    assert [b.activity_id for b in result.removed] == ["A1990"]


def test_a_valid_snapshot_can_be_compared_before_it_is_published(world: ScheduleWorld) -> None:
    world.define()
    one, _ = world.two_weeks()
    world.publish(one)
    result = read(world, views.comparison, "MAIN", 2)
    assert (result.old.number, result.new.number) == (1, 2)


def test_a_comparison_names_both_snapshots_or_refuses(world: ScheduleWorld) -> None:
    published_pair(world)
    backwards = read(world, views.comparison, "MAIN", 1, 2)
    assert (backwards.old.number, backwards.new.number) == (2, 1)
    assert backwards.data_date_shift_days == -7
    with pytest.raises(SnapshotNotFoundError):
        read(world, views.comparison, "MAIN", 1)  # nothing before the first
    with pytest.raises(SnapshotNotFoundError):
        read(world, views.comparison, "MAIN", 2, 7)
    with pytest.raises(NoCurrentSnapshotError):
        world.define("OTHER")
        read(world, views.comparison, "OTHER")


def test_a_comparison_is_cut_to_the_limit_and_says_so(world: ScheduleWorld) -> None:
    published_pair(world)
    whole = read(world, views.comparison, "MAIN")
    assert not whole.cut
    cut = read(world, views.comparison, "MAIN", limit=1)
    assert cut.cut and len(cut.float_changes) == 1
    assert cut.totals == whole.totals
    assert len(read(world, views.comparison, "MAIN", limit=0).float_changes) == 1


@needs_t08
def test_the_look_ahead_starts_at_the_data_date_of_the_snapshot(world: ScheduleWorld) -> None:
    published_pair(world)
    ahead = read(world, views.look_ahead_view, "MAIN")
    assert (ahead.snapshot_number, ahead.window_start, ahead.weeks) == (2, "2026-10-12", 4)
    assert ahead.counts["total"] == len(ahead.rows)
    assert "A1230" in {r.activity_id for r in ahead.rows}
    first = read(world, views.look_ahead_view, "MAIN", 1, 6)
    assert (first.snapshot_number, first.weeks, first.window_end) == (1, 6, "2026-11-16")
    with pytest.raises(ValueError, match="weeks"):
        read(world, views.look_ahead_view, "MAIN", None, 0)


@needs_t07
def test_an_activity_resolves_now_and_as_of_a_number_or_a_date(world: ScheduleWorld) -> None:
    published_pair(world)
    now = read(world, views.resolution, "MAIN", "A1230")
    assert (now.state, now.snapshot_number) == ("current", 2)
    then = read(world, views.resolution, "MAIN", "A1230", 1)
    assert (then.state, then.snapshot_number) == ("as_of", 1)
    dated = read(world, views.resolution, "MAIN", "A1230", "2026-10-08")
    assert (dated.state, dated.snapshot_number) == ("as_of", 1)
    assert read(world, views.resolution, "MAIN", "A1230", "2026-10-01").state == "no_snapshot"


@needs_t07
def test_the_activity_links_of_a_record_and_the_orphans_of_a_schedule(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    record = world.record()
    world.link(record, "A1230")
    world.link(record, "A1990")
    world.publish(two)
    with open_uow(world.db, readonly=True) as uow:
        links = views.activity_links(uow.conn(), record)
    assert [(link.ref_key, link.status) for link in links] == [
        ("MAIN/A1230", "active"),
        ("MAIN/A1990", "stale"),
    ]
    assert links[0].resolution.state == "current"
    assert links[1].resolution.state == "orphaned"
    [orphan] = read(world, views.orphans, "MAIN")
    assert (orphan.activity_id, orphan.from_id, orphan.last_seen_number) == ("A1990", record, 1)


def test_as_of_written_as_text() -> None:
    assert views.as_of_of(None) is None
    assert views.as_of_of("") is None
    assert views.as_of_of("current") is None
    assert views.as_of_of("3") == 3
    assert views.as_of_of("007") == 7
    assert views.as_of_of("2026-10-08") == "2026-10-08"
    assert views.as_of_of("٣") == "٣"  # not an ASCII digit: left for the resolver
    assert views.as_of_of("9" * 10) == "9" * 10
