"""After a restore: builds are queued again and the typed rows come back from the files (P1-I4)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from tl_adapters.db import open_uow, rebuild_projections
from tl_mod_schedule import registry, typed_store
from tl_mod_schedule.names import TYPED_TABLES
from tl_mod_schedule.reconcile import reconcile_tables, requeue, requeue_orphans
from tl_mod_schedule.testing import ScheduleWorld
from tl_xer.synth import make_xer, week_pair

TYPED = ("sched_activity", "sched_relationship", "sched_wbs", "sched_calendar")


def counts(world: ScheduleWorld) -> dict[str, int]:
    return {t: int(world.scalar(f"SELECT COUNT(*) FROM {t}")) for t in TYPED}


def lose_operational_tables(world: ScheduleWorld) -> None:
    """What a restore does not bring back: the typed rows and the queue."""
    with open_uow(world.db) as uow:
        for table in (*TYPED_TABLES.values(), "job_queue"):
            uow.conn().execute(text(f"DELETE FROM {table}"))


def test_a_projection_rebuild_leaves_the_typed_rows_and_the_queue_alone(
    world: ScheduleWorld,
) -> None:
    world.define()
    world.two_weeks()
    before = counts(world)
    assert all(before.values())
    rebuild_projections(world.db)
    assert counts(world) == before
    state = world.rows(
        "SELECT r.key, r.status FROM cur_core_record r WHERE r.type LIKE 'schedule.S%'"
    )
    assert state  # the records themselves come back from the events


def test_the_typed_rows_are_written_again_from_the_source_files(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    before = counts(world)
    lose_operational_tables(world)
    assert not any(counts(world).values())
    done = reconcile_tables(world.db, world.files)
    assert [(r.key, r.outcome) for r in done] == [("MAIN#1", "rebuilt"), ("MAIN#2", "rebuilt")]
    assert counts(world) == before
    with open_uow(world.db, readonly=True) as uow:
        for snapshot_id in (one, two):
            snapshot = registry.get_snapshot(uow.conn(), snapshot_id)
            assert snapshot is not None and typed_store.count_rows(uow.conn(), snapshot_id)
    again = reconcile_tables(world.db, world.files)
    assert [r.outcome for r in again] == ["ok", "ok"]
    assert counts(world) == before


def test_reconcile_repairs_a_snapshot_with_some_rows_missing(world: ScheduleWorld) -> None:
    world.define()
    one, _ = world.two_weeks()
    before = counts(world)
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("DELETE FROM sched_relationship WHERE snapshot_id = :id"), {"id": one}
        )
    assert counts(world) != before
    done = reconcile_tables(world.db, world.files)
    assert [(r.key, r.outcome) for r in done] == [("MAIN#1", "rebuilt"), ("MAIN#2", "ok")]
    assert counts(world) == before


def test_a_file_that_no_longer_gives_the_recorded_rows_writes_nothing(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, _ = world.two_weeks()
    lose_operational_tables(world)

    def other_reader(data: bytes, options: Any, **limits: Any) -> Any:
        from tl_xer.run import read_xer_file

        altered = make_xer(week_pair()[1])  # a different file than the one recorded
        return read_xer_file(altered, options, **limits)

    done = reconcile_tables(world.db, world.files, reader=other_reader)
    assert [(r.key, r.outcome) for r in done] == [("MAIN#1", "mismatch"), ("MAIN#2", "rebuilt")]
    assert (
        int(world.scalar("SELECT COUNT(*) FROM sched_activity WHERE snapshot_id = :i", i=one)) == 0
    )


def test_a_missing_source_file_is_reported_not_raised(world: ScheduleWorld, tmp_path: Any) -> None:
    world.define()
    world.two_weeks()
    lose_operational_tables(world)
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_schedule_schedule_snapshot SET source_sha256 = :x"), {"x": "0" * 64}
        )
    done = reconcile_tables(world.db, world.files)
    assert {r.outcome for r in done} == {"unreadable"}


def test_a_scope_limits_reconcile(world: ScheduleWorld) -> None:
    world.define()
    world.two_weeks()
    lose_operational_tables(world)
    assert reconcile_tables(world.db, world.files, scope="project:OTHER") == []
    assert len(reconcile_tables(world.db, world.files, scope="project:P123")) == 2


def test_builds_the_queue_lost_are_queued_again_and_then_run(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.open_snapshot().stream_id
    world.attach_xer(snapshot_id, make_xer(week_pair()[0]))
    world.start(snapshot_id)
    assert world.scalar("SELECT COUNT(*) FROM job_queue") == 1
    with open_uow(world.db) as uow:
        uow.conn().execute(text("DELETE FROM job_queue"))  # a restore
        assert requeue_orphans(uow.conn()) == 1
        assert requeue_orphans(uow.conn()) == 0  # already queued
    assert world.scalar("SELECT COUNT(*) FROM job_queue") == 1
    world.work()
    assert world.snapshot(snapshot_id).state == "Valid"
    assert requeue(world.db) == 0  # nothing waits any more


def test_a_snapshot_that_was_never_started_or_is_void_is_not_queued(world: ScheduleWorld) -> None:
    world.define()
    plain = world.open_snapshot().stream_id  # no file
    attached = world.open_snapshot().stream_id
    world.attach_xer(attached, make_xer(week_pair()[0]))  # a file, never started
    gone = world.open_snapshot().stream_id
    world.void(gone)
    assert requeue(world.db) == 0
    assert plain and attached
