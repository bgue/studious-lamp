"""The snapshot lifecycle: open, attach the XER file, queue, build (P1-I4-T05, ADR-0015)."""

from __future__ import annotations

import json

import pytest
from tl_adapters.db import open_uow
from tl_core.files.queries import list_files
from tl_mod_schedule import registry, typed_store
from tl_mod_schedule.build import BuildKind
from tl_mod_schedule.errors import (
    DuplicateSnapshotError,
    ScheduleNotFoundError,
    SnapshotStateError,
    SourceFileError,
)
from tl_mod_schedule.names import TYPED_TABLES
from tl_mod_schedule.testing import BASE, PROJECT, ScheduleWorld
from tl_xer.synth import make_xer, week_pair
from tl_xer.typed import ACTIVITY_COLUMNS
from xer_files import bad_xer, first_xer, multi_project_xer


def events_of(world: ScheduleWorld, snapshot_id: str) -> list[dict[str, object]]:
    return world.rows(
        "SELECT event_type, payload, actor, correlation_id FROM events "
        "WHERE stream_id = :i ORDER BY seq",
        i=snapshot_id,
    )


def types_of(world: ScheduleWorld, snapshot_id: str) -> list[object]:
    return [e["event_type"] for e in events_of(world, snapshot_id)]


def test_a_new_snapshot_is_numbered_and_waits_for_its_file(world: ScheduleWorld) -> None:
    world.define()
    one = world.open_snapshot()
    two = world.open_snapshot()
    assert (one.key, two.key) == ("MAIN#1", "MAIN#2")
    snap = world.snapshot(one.stream_id)
    assert snap.state == "Uploaded" and not snap.queued and snap.number == 1
    assert snap.data_date is None and snap.activity_count is None


def test_a_valid_file_becomes_a_valid_snapshot_with_its_typed_rows(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.upload(first_xer())
    snap = world.snapshot(snapshot_id)
    assert snap.state == "Valid" and snap.attempts == 1 and snap.last_error is None
    assert snap.data_date == "2026-10-05T08:00" and snap.p6_version == "20.12"
    assert snap.p6_project == "DEMO-RACK"
    assert (snap.activity_count, snap.relationship_count, snap.wbs_count) == (21, 23, 4)
    assert (snap.calendar_count, snap.code_count, snap.udf_count) == (1, 21, 12)
    assert (snap.error_count, snap.warning_count) == (0, 0)
    assert snap.source_name == "export.xer" and snap.requested_by == BASE["actor"]
    with open_uow(world.db, readonly=True) as uow:
        counts = typed_store.count_rows(uow.conn(), snapshot_id)
    assert counts == {
        "calendars": 1, "wbs": 4, "activities": 21, "relationships": 23, "codes": 21, "udfs": 12,
    }  # fmt: skip
    a1230 = next(a for a in world.activities(snapshot_id) if a.activity_id == "A1230")
    assert a1230.name == "Install pipe rack supports" and a1230.total_float_hr == 72.0
    assert a1230.early_finish == "2026-10-12T16:00" and a1230.status == "in_progress"


def test_the_events_of_a_build_in_order(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.upload(first_xer())
    assert types_of(world, snapshot_id) == [
        "Record.Created",
        "ScheduleSnapshot.Defined",
        "ScheduleSnapshot.Queued",
        "Workflow.Transitioned",
        "ScheduleSnapshot.BuildStarted",
        "ScheduleSnapshot.Built",
        "Workflow.Transitioned",
    ]
    built = json.loads(str(events_of(world, snapshot_id)[5]["payload"]))
    assert built["counts"]["activities"] == 21 and built["warning_count"] == 0
    snap = world.snapshot(snapshot_id)
    assert built["typed_sha256"] == snap.typed_sha256 and len(snap.typed_sha256 or "") == 64
    assert built["data_date"] == "2026-10-05T08:00"
    # the worker's events are the service's, not a person's
    assert {e["actor"] for e in events_of(world, snapshot_id)[4:]} == {"svc:schedule"}
    queued = json.loads(str(events_of(world, snapshot_id)[2]["payload"]))
    assert queued["source_name"] == "export.xer" and queued["source_size"] == len(first_xer())


def test_the_report_and_the_raw_tables_are_files_of_the_snapshot(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.upload(first_xer())
    snap = world.snapshot(snapshot_id)
    with open_uow(world.db, readonly=True) as uow:
        slots = {f.slot: f for f in list_files(uow, PROJECT, snapshot_id)}
    assert set(slots) == {"xer", "report", "raw"}
    assert (
        slots["report"].file_id == snap.report_file_id and slots["raw"].file_id == snap.raw_file_id
    )
    assert slots["report"].content_type == "application/json"
    assert slots["raw"].content_type == "application/gzip"
    with open_uow(world.db, readonly=True) as uow:
        opened = world.files.open_file(uow, PROJECT, slots["report"].file_id, actor="svc:schedule")
        report = json.loads(opened.data.read())
    assert report["status"] == "valid" and report["snapshot"] == "MAIN#1"
    assert report["source_sha256"] == snap.source_sha256


def test_a_file_that_fails_the_document_schema_is_an_invalid_snapshot_with_a_report(
    world: ScheduleWorld,
) -> None:
    world.define()
    snapshot_id = world.upload(bad_xer("TASK"))
    snap = world.snapshot(snapshot_id)
    assert snap.state == "Invalid" and snap.last_error == "missing_table"
    assert (snap.error_count, snap.activity_count, snap.data_date) == (1, None, None)
    assert snap.raw_file_id is None and snap.report_file_id is not None
    with open_uow(world.db, readonly=True) as uow:
        assert sum(typed_store.count_rows(uow.conn(), snapshot_id).values()) == 0
    assert "ScheduleSnapshot.Rejected" in types_of(world, snapshot_id)
    rejected = json.loads(
        str(
            next(
                e
                for e in events_of(world, snapshot_id)
                if e["event_type"] == "ScheduleSnapshot.Rejected"
            )["payload"]
        )
    )
    assert rejected["outcome"] == "invalid" and rejected["first_codes"] == ["missing_table"]


def test_a_file_that_is_not_an_xer_is_refused_with_its_own_report(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.upload(b"hello, this is not a schedule")
    snap = world.snapshot(snapshot_id)
    assert snap.state == "Invalid" and snap.last_error == "not_xer"
    rejected = next(
        e for e in events_of(world, snapshot_id) if e["event_type"] == "ScheduleSnapshot.Rejected"
    )
    assert json.loads(str(rejected["payload"]))["outcome"] == "refused"


def test_a_build_that_breaks_the_envelope_fails_for_good_and_leaves_the_snapshot_invalid(
    world: ScheduleWorld,
) -> None:
    world.define()
    snapshot_id = world.open_snapshot().stream_id
    world.attach_xer(snapshot_id, first_xer())
    world.start(snapshot_id)
    results = world.work(timeout_s=0.001)
    assert [r.outcome for r in results] == ["final"]
    snap = world.snapshot(snapshot_id)
    assert snap.state == "Invalid" and snap.last_error == "xer_limit" and snap.attempts == 1
    failed = next(
        e
        for e in events_of(world, snapshot_id)
        if e["event_type"] == "ScheduleSnapshot.BuildFailed"
    )
    payload = json.loads(str(failed["payload"]))
    assert payload["final"] is True and payload["error_code"] == "xer_limit"
    assert "Traceback" not in payload["error_message"] and "/" not in payload["error_message"]
    with open_uow(world.db, readonly=True) as uow:
        assert sum(typed_store.count_rows(uow.conn(), snapshot_id).values()) == 0
    assert world.work() == []  # the queue is empty: nothing runs a second time


def test_an_unexpected_failure_of_the_reader_is_retried_not_final(world: ScheduleWorld) -> None:
    from tl_adapters.db import make_uow_factory
    from tl_adapters.queue import job_queue_for
    from tl_core.jobs import JobRunner

    world.define()
    snapshot_id = world.open_snapshot().stream_id
    world.attach_xer(snapshot_id, first_xer())
    world.start(snapshot_id)

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("bug in the reader")

    open_uow_ = make_uow_factory(world.db)
    with open_uow_() as uow:
        queue = job_queue_for(uow.conn())
    runner = JobRunner(open_uow_, queue, [BuildKind(world.files, reader=boom)], worker_id="t")
    [result] = runner.run_until_idle()
    open_uow_.dispose()  # type: ignore[attr-defined]
    assert result.outcome == "retry"
    snap = world.snapshot(snapshot_id)
    assert snap.state == "Processing" and snap.last_error == "internal_error"
    failed = next(
        e
        for e in events_of(world, snapshot_id)
        if e["event_type"] == "ScheduleSnapshot.BuildFailed"
    )
    assert json.loads(str(failed["payload"]))["final"] is False


# --- starting ---------------------------------------------------------------------------------


def test_a_snapshot_without_a_file_cannot_be_started(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.open_snapshot().stream_id
    with pytest.raises(SourceFileError, match="no XER file"):
        world.start(snapshot_id)


def test_a_snapshot_is_queued_once(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.open_snapshot().stream_id
    world.attach_xer(snapshot_id, first_xer())
    world.start(snapshot_id)
    with pytest.raises(SnapshotStateError, match="already queued"):
        world.start(snapshot_id)
    assert world.scalar("SELECT COUNT(*) FROM job_queue WHERE job_id = :i", i=snapshot_id) == 1
    world.work()
    with pytest.raises(SnapshotStateError):
        world.start(snapshot_id)


def test_a_second_file_replaces_the_first_before_the_build_is_queued(world: ScheduleWorld) -> None:
    world.define()
    snapshot_id = world.open_snapshot().stream_id
    world.attach_xer(snapshot_id, bad_xer("TASK"), "wrong.xer")
    world.attach_xer(snapshot_id, first_xer(), "right.xer")
    world.start(snapshot_id)
    world.work()
    snap = world.snapshot(snapshot_id)
    assert snap.state == "Valid" and snap.source_name == "right.xer"


def test_the_same_file_is_not_queued_twice_for_a_schedule(world: ScheduleWorld) -> None:
    world.define()
    first = world.upload(first_xer())
    again = world.open_snapshot().stream_id
    world.attach_xer(again, first_xer(), "copy.xer")
    with pytest.raises(DuplicateSnapshotError, match="same SHA-256"):
        world.start(again)
    world.void(first)
    world.start(again)  # a void snapshot does not count
    world.define("OTHER")
    other = world.open_snapshot("OTHER").stream_id
    world.attach_xer(other, first_xer(), "elsewhere.xer")
    world.start(other)  # another schedule may hold the same file


def test_a_snapshot_of_another_scope_or_a_missing_one_is_not_found(world: ScheduleWorld) -> None:
    from tl_mod_schedule.errors import SnapshotNotFoundError
    from tl_mod_schedule.handlers.snapshots import (
        OpenScheduleSnapshot,
        StartScheduleSnapshot,
        handle_open_schedule_snapshot,
        handle_start_schedule_snapshot,
    )

    world.define()
    snapshot_id = world.open_snapshot().stream_id
    with open_uow(world.db) as uow, pytest.raises(SnapshotNotFoundError):
        handle_start_schedule_snapshot(
            uow,
            StartScheduleSnapshot(**{**BASE, "scope": "project:OTHER"}, snapshot_id=snapshot_id),
        )
    with open_uow(world.db) as uow, pytest.raises(ScheduleNotFoundError):
        handle_open_schedule_snapshot(
            uow, OpenScheduleSnapshot(**BASE, schedule_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6P6")
        )


# --- the project of a file with several ---------------------------------------------------------


def test_the_project_to_read_comes_from_the_snapshot_or_the_schedule(world: ScheduleWorld) -> None:
    world.define("PICKED", p6_project="DEMO-RACK")
    one = world.upload(multi_project_xer(), "PICKED", "a.xer")
    assert world.snapshot(one).state == "Valid"
    world.define("NOTHING")
    two = world.upload(multi_project_xer(), "NOTHING", "b.xer")
    assert (
        world.snapshot(two).state == "Invalid" and world.snapshot(two).last_error == "multi_project"
    )
    world.define("OPTION")
    three = world.upload(multi_project_xer(), "OPTION", "c.xer", p6_project="DEMO-RACK")
    assert world.snapshot(three).state == "Valid"
    assert world.snapshot(three).p6_project_option == "DEMO-RACK"


# --- voiding ----------------------------------------------------------------------------------


def test_a_snapshot_is_voided_while_uploaded_invalid_or_valid_and_not_after(
    world: ScheduleWorld,
) -> None:
    world.define()
    uploaded = world.open_snapshot().stream_id
    world.void(uploaded)
    assert world.snapshot(uploaded).state == "Void"
    invalid = world.upload(bad_xer("TASK"))
    world.void(invalid)
    valid = world.upload(first_xer())
    world.publish(valid)
    with pytest.raises(SnapshotStateError, match="only an Uploaded, Invalid or Valid"):
        world.void(valid)
    with pytest.raises(SnapshotStateError):
        world.void(uploaded)


def test_a_snapshot_voided_before_its_build_runs_is_failed_by_the_worker_not_built(
    world: ScheduleWorld,
) -> None:
    world.define()
    snapshot_id = world.open_snapshot().stream_id
    world.attach_xer(snapshot_id, first_xer())
    world.start(snapshot_id)
    world.void(snapshot_id)
    assert world.work() == []  # the queue row could not be started and was failed
    assert world.snapshot(snapshot_id).state == "Void"
    assert world.scalar("SELECT state FROM job_queue WHERE job_id = :i", i=snapshot_id) == "failed"
    assert world.activities(snapshot_id) == []


def test_the_typed_table_names_are_those_of_the_schema() -> None:
    assert sorted(TYPED_TABLES.values()) == [
        "sched_activity", "sched_activity_code", "sched_calendar", "sched_relationship",
        "sched_udf_value", "sched_wbs",
    ]  # fmt: skip
    assert "activity_id" in ACTIVITY_COLUMNS
    assert registry.DEFAULT_DAY_HOURS == 8.0


def test_two_snapshots_of_the_demo_both_build(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    first, second = (world.snapshot(i) for i in (one, two))
    assert (first.number, second.number) == (1, 2)
    assert first.data_date == "2026-10-05T08:00" and second.data_date == "2026-10-12T08:00"
    assert second.activity_count == 21  # one gone, one new
    assert make_xer(week_pair()[0]) != make_xer(week_pair()[1])
