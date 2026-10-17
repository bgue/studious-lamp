"""Linking a record to an activity by its stable id, and the references behind it (P1-I4-T07)."""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_core.services.errors import ServiceError
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    NoCurrentSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
)
from tl_mod_schedule.handlers.activity import LinkActivity, handle_link_activity
from tl_mod_schedule.testing import BASE, ScheduleWorld
from xer_files import first_xer


def test_a_link_points_at_the_reference_of_the_activity_not_at_a_snapshot(
    world: ScheduleWorld,
) -> None:
    world.define()
    snapshot_id = world.upload(first_xer())
    world.publish(snapshot_id)
    record = world.record()
    made = world.link(record, "A1230")
    ref = world.ref("MAIN", "A1230")
    assert ref is not None and ref.key == "MAIN/A1230" and ref.present
    assert (ref.first_snapshot_id, ref.first_snapshot_number) == (snapshot_id, 1)
    link = world.link_row(made.stream_id)
    assert (link["from_id"], link["to_id"], link["relation"]) == (record, ref.id, "references")
    assert link["status"] == "active" and link["pin"] is None
    title = world.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=ref.id)
    assert title == "A1230 Install pipe rack supports"


def test_the_reference_is_made_once_and_shared_by_every_link(world: ScheduleWorld) -> None:
    world.define()
    world.publish(world.upload(first_xer()))
    first, second = world.record("R-1"), world.record("R-2")
    one = world.link(first, "A1230")
    two = world.link(second, "A1230")
    assert world.link_row(one.stream_id)["to_id"] == world.link_row(two.stream_id)["to_id"]
    assert world.scalar("SELECT COUNT(*) FROM cur_schedule_activity_ref") == 1
    assert [e.event_type for e in two.events] == ["Link.Added"]  # no second reference


def test_a_link_may_pin_a_published_snapshot(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    world.publish(two)
    made = world.link(world.record(), "A1990", pin=1)  # A1990 is only in snapshot 1
    assert world.link_row(made.stream_id)["pin"] == "1"


@pytest.mark.parametrize("pin", [3, 99])
def test_a_pin_must_name_a_published_snapshot(world: ScheduleWorld, pin: int) -> None:
    world.define()
    one, _ = world.two_weeks()
    world.publish(one)
    with pytest.raises(SnapshotNotFoundError):
        world.link(world.record(), "A1230", pin=pin)
    with pytest.raises(SnapshotNotFoundError):  # snapshot 2 is built but not published
        world.link(world.record(), "A1230", pin=2)


def test_an_unknown_activity_is_refused_and_leaves_no_reference(world: ScheduleWorld) -> None:
    world.define()
    world.publish(world.upload(first_xer()))
    with pytest.raises(ActivityNotFoundError):
        world.link(world.record(), "A9999")
    assert world.scalar("SELECT COUNT(*) FROM cur_schedule_activity_ref") == 0


def test_an_activity_missing_from_the_current_snapshot_cannot_be_linked_any_more(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    world.publish(two)
    with pytest.raises(ActivityNotFoundError):
        world.link(world.record(), "A1990")


def test_a_schedule_with_no_published_snapshot_has_nothing_to_link_to(world: ScheduleWorld) -> None:
    world.define()
    world.upload(first_xer())  # built, not published
    with pytest.raises(NoCurrentSnapshotError):
        world.link(world.record(), "A1230")


def test_the_schedule_must_exist_in_the_scope(world: ScheduleWorld) -> None:
    world.define()
    world.publish(world.upload(first_xer()))
    schedule = world.schedule()
    record = world.record()
    with open_uow(world.db) as uow, pytest.raises(ScheduleNotFoundError):
        handle_link_activity(
            uow,
            LinkActivity(
                **{**BASE, "scope": "project:OTHER"},
                from_id=record,
                schedule_id=schedule.id,
                activity_id="A1230",
            ),
        )


def test_a_record_type_that_takes_no_links_cannot_start_one(world: ScheduleWorld) -> None:
    world.define()
    world.publish(world.upload(first_xer()))
    first = world.link(world.record(), "A1230")
    ref = world.ref("MAIN", "A1230")
    assert ref is not None
    del first
    with open_uow(world.db) as uow, pytest.raises(ServiceError):
        handle_link_activity(
            uow,
            LinkActivity(
                **BASE, from_id=ref.id, schedule_id=world.schedule().id, activity_id="A1240"
            ),
        )


def test_the_activity_id_and_note_are_bounded() -> None:
    from pydantic import ValidationError

    base = {**BASE, "from_id": "x", "schedule_id": "y"}
    with pytest.raises(ValidationError):
        LinkActivity(**base, activity_id="")
    with pytest.raises(ValidationError):
        LinkActivity(**base, activity_id="A" * 61)
    with pytest.raises(ValidationError):
        LinkActivity(**base, activity_id="A\x07")
    with pytest.raises(ValidationError):
        LinkActivity(**base, activity_id="A1", pin=0)
    with pytest.raises(ValidationError):
        LinkActivity(**base, activity_id="A1", note="n" * 501)
    with pytest.raises(ValidationError):
        LinkActivity(**{**base, "surprise": 1}, activity_id="A1")
