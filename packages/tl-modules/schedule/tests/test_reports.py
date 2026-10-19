"""The report of records with no schedule activity (P1-I4)."""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_core.services.commands import CreateRecord, VoidRecord
from tl_core.services.links import FlagLink, RetractLink, handle_flag_link, handle_retract_link
from tl_core.services.records import handle_create_record, handle_void_record
from tl_mod_schedule import reports
from tl_mod_schedule.errors import ScheduleNotFoundError
from tl_mod_schedule.testing import BASE, ScheduleWorld


def unscheduled(
    world: ScheduleWorld, kind: str = "core.Record", **more: object
) -> list[reports.UnscheduledRecord]:
    scope = str(more.pop("scope", BASE["scope"]))
    with open_uow(world.db, readonly=True) as uow:
        return reports.unscheduled_records(uow.conn(), scope, kind, **more)  # pyright: ignore[reportArgumentType]


def keys(found: list[reports.UnscheduledRecord]) -> list[str | None]:
    return [r.key for r in found]


@pytest.fixture
def scheduled(world: ScheduleWorld) -> ScheduleWorld:
    """Both demo files published; REC-A linked to A1230 (stays), REC-C to A1990 (leaves, and the
    worker has flagged it), REC-B and REC-D linked to nothing."""
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    ids = {key: world.record(key) for key in ("REC-D", "REC-B", "REC-C", "REC-A")}
    world.link(ids["REC-A"], "A1230")
    world.link(ids["REC-C"], "A1990")
    world.publish(two)
    return world


def test_records_with_no_activity_are_listed_by_key(scheduled: ScheduleWorld) -> None:
    found = unscheduled(scheduled)
    assert keys(found) == ["REC-B", "REC-C", "REC-D"]
    assert (found[0].record_type, found[0].title) == ("core.Record", "REC-B")
    assert len(found[0].id) == 26


def test_a_link_to_an_activity_that_left_does_not_count(scheduled: ScheduleWorld) -> None:
    assert "REC-C" in keys(unscheduled(scheduled))
    # before the worker has flagged it, the link is still active and the record counts as scheduled
    assert scheduled.scalar("SELECT COUNT(*) FROM cur_links WHERE status = 'stale'") == 1


def test_only_the_asked_type_and_only_live_records_are_listed(scheduled: ScheduleWorld) -> None:
    with open_uow(scheduled.db) as uow:
        handle_create_record(
            uow, CreateRecord(**BASE, record_type="core.Record", title="OLD", key="REC-OLD")
        )
    [old] = [r for r in unscheduled(scheduled) if r.key == "REC-OLD"]
    with open_uow(scheduled.db) as uow:
        handle_void_record(
            uow, VoidRecord(**BASE, stream_id=old.id, expected_version=1, reason="duplicate")
        )
    assert "REC-OLD" not in keys(unscheduled(scheduled))
    assert unscheduled(scheduled, "core.Other") == []


def test_with_a_schedule_only_links_to_that_schedule_count(scheduled: ScheduleWorld) -> None:
    scheduled.define("OTHER")
    assert keys(unscheduled(scheduled, schedule_code="MAIN")) == ["REC-B", "REC-C", "REC-D"]
    # nothing is linked to OTHER, so even REC-A is unscheduled there
    assert keys(unscheduled(scheduled, schedule_code="OTHER")) == [
        "REC-A",
        "REC-B",
        "REC-C",
        "REC-D",
    ]
    with pytest.raises(ScheduleNotFoundError, match="no schedule 'NOPE'"):
        unscheduled(scheduled, schedule_code="NOPE")


def test_the_report_is_cut_at_the_limit(scheduled: ScheduleWorld) -> None:
    assert keys(unscheduled(scheduled, limit=2)) == ["REC-B", "REC-C"]
    assert keys(unscheduled(scheduled, limit=0)) == ["REC-B"]  # at least one


def test_another_project_sees_nothing_of_this_ones_records_or_schedules(
    scheduled: ScheduleWorld,
) -> None:
    other = {**BASE, "scope": "project:OTHER"}
    with open_uow(scheduled.db) as uow:
        handle_create_record(
            uow, CreateRecord(**other, record_type="core.Record", title="X", key="REC-X")
        )
    assert keys(unscheduled(scheduled, scope="project:OTHER")) == ["REC-X"]
    assert "REC-X" not in keys(unscheduled(scheduled))
    with pytest.raises(ScheduleNotFoundError):
        unscheduled(scheduled, scope="project:OTHER", schedule_code="MAIN")


def test_a_retracted_link_or_one_a_person_flagged_no_longer_schedules_a_record(
    scheduled: ScheduleWorld,
) -> None:
    [a_link] = [
        r["link_id"]
        for r in scheduled.rows("SELECT link_id FROM cur_links WHERE status = 'active'")
    ]
    assert "REC-A" not in keys(unscheduled(scheduled))
    with open_uow(scheduled.db) as uow:
        handle_flag_link(uow, FlagLink(**BASE, link_id=a_link, status="stale", reason="check this"))
    assert "REC-A" in keys(unscheduled(scheduled))  # a stale link is not a schedule
    other = scheduled.record("REC-E")
    made = scheduled.link(other, "A1240").stream_id
    assert "REC-E" not in keys(unscheduled(scheduled))
    with open_uow(scheduled.db) as uow:
        handle_retract_link(uow, RetractLink(**BASE, link_id=made, reason="mistake"))
    assert "REC-E" in keys(unscheduled(scheduled))
