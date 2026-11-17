"""The job ``scaffold.inspections_due``: flags a due scaffold once and writes nothing twice."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from scaffold_world import SCOPE, World
from sqlalchemy import text
from tl_adapters.db import make_uow_factory, open_uow
from tl_adapters.queue import job_queue_for
from tl_core.jobs import JobFailure, JobRunner
from tl_core.jobs.types import Claim
from tl_mod_scaffold import inspections_due
from tl_mod_scaffold.inspections_due import InspectionsDueKind, job_id, parse_job_id, request
from tl_mod_scaffold.names import JOB_KIND, JOB_SOURCE

TODAY = datetime.now(UTC).date()


def run(world: World, day: date) -> int:
    """Queue and run the job of the project for ``day``; the number of events it appended."""
    open_uow = make_uow_factory(world.db)
    try:
        before = world.count()
        with open_uow() as uow:
            request(uow, "P123", day)
        with open_uow() as uow:
            queue = job_queue_for(uow.conn())
        runner = JobRunner(open_uow, queue, [InspectionsDueKind()], worker_id="test")
        runner.run_until_idle()
        return world.count() - before
    finally:
        open_uow.dispose()


def flagged(world: World) -> list[dict[str, object]]:
    return world.rows(
        "SELECT e.stream_id, e.payload, e.actor, e.source FROM events e "
        "WHERE e.event_type = 'Scaffold.InspectionDue' ORDER BY e.seq"
    )


def test_job_ids_round_trip() -> None:
    assert job_id("P123", date(2026, 11, 9)) == "inspdue:P123:2026-11-09"
    assert parse_job_id("inspdue:P123:2026-11-09") == ("P123", date(2026, 11, 9))
    for bad in ("ready:P123", "inspdue:2026-11-09", "inspdue:P1:11-09"):
        with pytest.raises(ValueError):
            parse_job_id(bad)
    assert JOB_KIND == "scaffold.inspections_due" and JOB_SOURCE == "job:scaffold.inspections_due"


def test_an_overdue_scaffold_is_flagged_once_and_a_second_run_writes_nothing(world: World) -> None:
    sid = world.advance(world.register(), "In Use")
    due = world.row(sid)["next_due_on"]
    assert run(world, TODAY + timedelta(days=3)) == 0  # not yet due
    assert run(world, TODAY + timedelta(days=8)) == 1
    row = world.row(sid)
    assert row["flagged_due_on"] == due == row["next_due_on"]
    (event,) = flagged(world)
    assert event["stream_id"] == sid and event["source"] == JOB_SOURCE
    assert due in str(event["payload"]) and "In Use" in str(event["payload"])
    # the same run again and the next day: nothing more
    assert run(world, TODAY + timedelta(days=8)) == 0
    assert run(world, TODAY + timedelta(days=9)) == 0
    assert len(flagged(world)) == 1


def test_a_scaffold_due_today_is_flagged(world: World) -> None:
    sid = world.advance(world.register(), "Inspected")
    assert run(world, TODAY + timedelta(days=7)) == 1
    assert world.row(sid)["flagged_due_on"] == world.row(sid)["next_due_on"]


def test_the_job_never_changes_a_tag_or_a_state(world: World) -> None:
    sid = world.advance(world.register(), "In Use")
    before = world.row(sid)
    state = world.state(sid)
    run(world, TODAY + timedelta(days=30))
    after = world.row(sid)
    assert world.state(sid) == state == "In Use"
    assert {k: v for k, v in after.items() if k not in ("flagged_due_on", "last_seq")} == {
        k: v for k, v in before.items() if k not in ("flagged_due_on", "last_seq")
    }


def test_a_flag_for_an_older_due_day_does_not_stop_the_next_one(world: World) -> None:
    sid = world.advance(world.register(), "In Use")
    run(world, TODAY + timedelta(days=8))
    # the scaffold was flagged for an earlier due day: the current one is flagged again
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_scaffold_scaffold SET flagged_due_on = '2020-01-01' WHERE id = :i"),
            {"i": sid},
        )
    assert run(world, TODAY + timedelta(days=9)) == 1
    assert world.row(sid)["flagged_due_on"] == world.row(sid)["next_due_on"]
    assert len(flagged(world)) == 2


@pytest.mark.parametrize("stage", ["Requested", "Designed", "Erecting", "Dismantle", "Removed"])
def test_a_scaffold_that_does_not_stand_is_not_flagged(world: World, stage: str) -> None:
    sid = world.register()
    if stage in ("Designed", "Erecting"):
        world.advance(sid, stage)
    if stage == "Dismantle":
        world.advance(sid, "Inspected")
        world.call("uma", "DismantleScaffold", scaffold=sid, reason="Done")
    if stage == "Removed":
        world.call("uma", "RemoveScaffold", scaffold=sid)
    assert run(world, TODAY + timedelta(days=60)) == 0


def test_another_project_is_not_touched(world: World) -> None:
    sid = world.advance(world.register(), "In Use")
    open_uow = make_uow_factory(world.db)
    try:
        with open_uow() as uow:
            request(uow, "P999", TODAY + timedelta(days=30))
        with open_uow() as uow:
            queue = job_queue_for(uow.conn())
        JobRunner(open_uow, queue, [InspectionsDueKind()], worker_id="test").run_until_idle()
    finally:
        open_uow.dispose()
    assert world.row(sid)["flagged_due_on"] is None and not flagged(world)


def test_one_run_per_project_and_day(world: World) -> None:
    open_uow = make_uow_factory(world.db)
    try:
        with open_uow() as uow:
            assert request(uow, "P123", TODAY)
            assert not request(uow, "P123", TODAY)
            assert request(uow, "P123", TODAY + timedelta(days=1))
    finally:
        open_uow.dispose()


def test_a_job_with_a_bad_id_fails_for_good(world: World) -> None:
    claim = Claim(
        job_id="inspdue:nope",
        kind=JOB_KIND,
        scope=SCOPE,
        attempt=1,
        max_attempts=3,
        owner="t",
        lease_until="2026-01-01T00:00:00.000000Z",
    )
    open_uow = make_uow_factory(world.db)
    try:
        with open_uow() as uow, pytest.raises(JobFailure) as caught:
            InspectionsDueKind().prepare(uow, claim)
    finally:
        open_uow.dispose()
    assert not caught.value.retryable


def test_the_module_exports_the_job_kind() -> None:
    assert inspections_due.InspectionsDueKind.kind == JOB_KIND
