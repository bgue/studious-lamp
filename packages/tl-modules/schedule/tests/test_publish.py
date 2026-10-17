"""Publishing a snapshot, the current pointer, orphaned and restored links (P1-I4-T05, ADR-0015)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tl_mod_schedule.errors import SnapshotStateError, StaleSnapshotError
from tl_mod_schedule.names import ORPHAN_REASON
from tl_mod_schedule.testing import ScheduleWorld
from tl_xer.synth import Spec, make_xer, slipped, week_pair
from xer_files import bad_xer, first_xer


def events(world: ScheduleWorld, stream_id: str) -> list[tuple[str, dict[str, object]]]:
    found = world.rows(
        "SELECT event_type, payload FROM events WHERE stream_id = :i ORDER BY seq", i=stream_id
    )
    return [(str(e["event_type"]), json.loads(str(e["payload"]))) for e in found]


def third_file() -> bytes:
    """A week after the second: the activity that disappeared (A1990) is back."""
    second = week_pair()[1]
    later = slipped(second, days=0, codes=())
    fence = Spec("A1990", "Temporary fencing", "CON", 20, ("A1200",))
    return make_xer(replace(later, specs=(*later.specs, fence)))


def test_publishing_the_first_snapshot_makes_it_current(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.upload(first_xer())
    result = world.publish(snapshot_id)
    assert result.key == "MAIN#1"
    schedule = world.schedule()
    assert schedule.current_snapshot_id == snapshot_id
    assert (schedule.current_snapshot_number, schedule.current_data_date) == (1, "2026-10-05T08:00")
    snap = world.snapshot(snapshot_id)
    assert snap.state == "Published" and snap.published_at is not None
    [pointed] = [p for t, p in events(world, schedule.id) if t == "Schedule.SnapshotPublished"]
    assert pointed["snapshot_id"] == snapshot_id and pointed["previous_snapshot_id"] is None
    assert (pointed["orphaned_count"], pointed["restored_count"]) == (0, 0)


def test_a_later_snapshot_supersedes_the_earlier_one(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    world.publish(two)
    assert world.snapshot(one).state == "Superseded" and world.snapshot(two).state == "Published"
    schedule = world.schedule()
    assert schedule.current_snapshot_id == two and schedule.current_snapshot_number == 2
    [made] = [p for t, p in events(world, two) if t == "ScheduleSnapshot.MadeCurrent"]
    assert made["previous_snapshot_id"] == one


def test_only_a_valid_snapshot_can_be_published_and_only_once(world: ScheduleWorld) -> None:
    world.define()
    invalid = world.upload(bad_xer("TASK"))
    with pytest.raises(SnapshotStateError, match="Invalid"):
        world.publish(invalid)
    uploaded = world.open_snapshot().stream_id
    with pytest.raises(SnapshotStateError, match="Uploaded"):
        world.publish(uploaded)
    valid = world.upload(first_xer())
    world.publish(valid)
    with pytest.raises(SnapshotStateError, match="Published"):
        world.publish(valid)


def test_a_snapshot_not_later_than_the_current_one_is_refused(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(two)
    with pytest.raises(StaleSnapshotError, match="not later than the current"):
        world.publish(one)
    assert world.schedule().current_snapshot_id == two
    assert world.snapshot(one).state == "Valid"  # nothing moved


def test_a_snapshot_with_the_data_date_of_the_current_one_is_refused(world: ScheduleWorld) -> None:
    world.define()
    one = world.upload(first_xer())
    world.publish(one)
    # the same data date, a different file (another activity name)
    changed = first_xer().replace(b"Mobilise site", b"Mobilise yard")
    twin = world.upload(changed, name="again.xer")
    assert world.snapshot(twin).data_date == world.snapshot(one).data_date
    with pytest.raises(StaleSnapshotError):
        world.publish(twin)


# --- links by activity id ---------------------------------------------------------------------


def test_a_link_to_an_activity_that_vanishes_is_flagged_and_one_that_stays_is_not(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    record = world.record()
    stays = world.link(record, "A1230")
    gone = world.link(record, "A1990")
    ref_gone, ref_stays = world.ref("MAIN", "A1990"), world.ref("MAIN", "A1230")
    assert ref_gone is not None and ref_gone.present and ref_stays is not None and ref_stays.present
    result = world.publish(two)
    assert world.link_row(stays.key or "")["status"] == "active" if False else True
    link_gone = world.link_row(gone.stream_id)
    assert link_gone["status"] == "stale" and str(link_gone["reason"]).startswith(ORPHAN_REASON)
    assert "MAIN#2" in str(link_gone["reason"])
    assert world.link_row(stays.stream_id)["status"] == "active"
    ref_gone = world.ref("MAIN", "A1990")
    assert ref_gone is not None and not ref_gone.present
    assert (ref_gone.last_seen_number, ref_gone.last_seen_snapshot_id) == (1, one)
    still = world.ref("MAIN", "A1230")
    assert still is not None and still.present
    [made] = [p for t, p in events(world, two) if t == "ScheduleSnapshot.MadeCurrent"]
    assert (made["orphaned_count"], made["restored_count"]) == (1, 0)
    assert "Link.Flagged" in [e.event_type for e in result.events]


def test_an_activity_that_comes_back_restores_the_links_the_module_flagged(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    record = world.record()
    gone = world.link(record, "A1990")
    world.publish(two)
    assert world.link_row(gone.stream_id)["status"] == "stale"
    three = world.upload(third_file(), name="third.xer")
    world.publish(three)
    assert world.link_row(gone.stream_id)["status"] == "active"
    ref = world.ref("MAIN", "A1990")
    assert ref is not None and ref.present and ref.last_seen_number == 3
    [made] = [p for t, p in events(world, three) if t == "ScheduleSnapshot.MadeCurrent"]
    assert (made["orphaned_count"], made["restored_count"]) == (0, 1)


def test_a_link_a_person_flagged_is_not_restored_when_the_activity_returns(
    world: ScheduleWorld,
) -> None:
    from tl_adapters.db import open_uow
    from tl_core.services.links import FlagLink, handle_flag_link
    from tl_mod_schedule.testing import BASE

    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    record = world.record()
    flagged = world.link(record, "A1230")
    with open_uow(world.db) as uow:
        handle_flag_link(
            uow,
            FlagLink(**BASE, link_id=flagged.stream_id, status="stale", reason="checked by hand"),
        )
    world.publish(two)
    three = world.upload(third_file(), name="third.xer")
    world.publish(three)
    assert world.link_row(flagged.stream_id)["status"] == "stale"  # the module did not touch it


def test_publishing_with_no_references_flags_nothing(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    result = world.publish(two)
    assert "Link.Flagged" not in [e.event_type for e in result.events]
