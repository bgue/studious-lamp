"""Fixes of the security review (P1-I4): each test fails when its fix is taken out."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core.services.errors import UnsupportedRecordTypeError
from tl_core.services.links import (
    AddLink,
    FlagLink,
    RepinLink,
    RetractLink,
    SuggestLink,
    handle_add_link,
    handle_flag_link,
    handle_repin_link,
    handle_retract_link,
    handle_suggest_link,
)
from tl_core.util import effective_time
from tl_mod_schedule import compare, limits, registry, resolver, typed_store, views
from tl_mod_schedule.common import stamp
from tl_mod_schedule.errors import (
    FutureDataDateError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    TooManyLinksError,
    TooManyOpenSnapshotsError,
    TooManyReferencesError,
    TypedRowsMissingError,
)
from tl_mod_schedule.handlers.activity import LinkActivity
from tl_mod_schedule.handlers.schedules import DefineSchedule
from tl_mod_schedule.handlers.snapshots import OpenScheduleSnapshot, VoidScheduleSnapshot
from tl_mod_schedule.lookahead import look_ahead
from tl_mod_schedule.names import ORPHAN_REASON, SERVICE
from tl_mod_schedule.orphans import outstanding, run_once
from tl_mod_schedule.reconcile import reconcile_tables, requeue_orphans
from tl_mod_schedule.testing import BASE, ScheduleWorld
from tl_xer.synth import Spec, make_xer, slipped, week_pair
from tl_xer.typed import Snapshot
from xer_files import first_xer

SCOPE = BASE["scope"]


def third_file() -> bytes:
    """A week after the second, the activity that left (A1990) back."""
    later = slipped(week_pair()[1], days=0, codes=())
    fence = Spec("A1990", "Temporary fencing", "CON", 20, ("A1200",))
    return make_xer(replace(later, specs=(*later.specs, fence)))


def events(world: ScheduleWorld, event_type: str) -> list[Any]:
    with open_uow(world.db, readonly=True) as uow:
        return [e for e in uow.ledger.read_after(0, limit=100_000) if e.event_type == event_type]


def queued_flag_jobs(world: ScheduleWorld) -> int:
    return int(world.scalar("SELECT COUNT(*) FROM job_queue WHERE kind = 'schedule.flag_orphans'"))


def linked_pair(world: ScheduleWorld, links: int = 1) -> tuple[str, str, list[str]]:
    """Snapshot 1 published, ``links`` records linked to A1990 (which snapshot 2 lacks)."""
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    made = [world.link(world.record(f"R-{n}"), "A1990").stream_id for n in range(links)]
    return one, two, made


# --- 6. publishing queues the flagging; a job does it in bounded runs ---------------------------


def test_publishing_flags_nothing_itself_and_queues_the_job(world: ScheduleWorld) -> None:
    _, two, [link] = linked_pair(world)
    result = world.publish(two, check=False)
    assert world.link_row(link)["status"] == "active"  # the window: not yet
    assert "Link.Flagged" not in [e.event_type for e in result.events]
    assert queued_flag_jobs(world) == 1
    [pointed] = events(world, "Schedule.SnapshotPublished")[-1:]
    assert pointed.payload["orphan_check_queued"] is True
    assert world.scalar("SELECT present FROM cur_schedule_activity_ref WHERE activity_id = 'A1990'")
    world.work()
    assert world.link_row(link)["status"] == "stale"
    assert queued_flag_jobs(world) == int(
        world.scalar("SELECT COUNT(*) FROM job_queue WHERE kind = 'schedule.flag_orphans'")
    )


def test_the_schedule_says_while_its_links_are_being_checked(world: ScheduleWorld) -> None:
    _, two, _ = linked_pair(world)

    def checking() -> bool:
        with open_uow(world.db, readonly=True) as uow:
            return views.schedule_detail(uow.conn(), SCOPE, "MAIN").links_being_checked

    assert checking() is False
    world.publish(two, check=False)
    assert checking() is True  # the window: the link still reads as current
    world.work()
    assert checking() is False


def test_no_job_is_queued_for_a_schedule_nothing_is_linked_to(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one, check=False)
    world.publish(two, check=False)
    assert queued_flag_jobs(world) == 0
    made = events(world, "ScheduleSnapshot.MadeCurrent")
    assert [e.payload["orphan_check_queued"] for e in made] == [False, False]


def test_a_run_does_a_bounded_amount_and_queues_the_next(
    world: ScheduleWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "FLAG_BATCH", 3)
    _, two, links = linked_pair(world, links=5)
    world.publish(two, check=False)
    first = world.work_once()
    assert first is not None and first.kind == "schedule.flag_orphans" and first.outcome == "done"
    [run] = events(world, "Schedule.OrphansChecked")
    assert (run.payload["refs_changed"], run.payload["links_flagged"]) == (1, 2)
    assert run.payload["complete"] is False
    assert [world.link_row(x)["status"] for x in links].count("stale") == 2
    assert queued_flag_jobs(world) >= 1  # the next run is waiting
    world.work()
    assert {world.link_row(x)["status"] for x in links} == {"stale"}
    runs = events(world, "Schedule.OrphansChecked")
    # a run that used its whole budget cannot know that nothing is left: the next one says so
    assert [r.payload["links_flagged"] for r in runs] == [2, 3, 0]
    assert [r.payload["complete"] for r in runs] == [False, False, True]
    assert sum(r.payload["links_flagged"] for r in runs) == 5


def test_a_run_is_idempotent_and_a_lost_run_changes_nothing(world: ScheduleWorld) -> None:
    _, two, [link] = linked_pair(world)
    world.publish(two)
    schedule = world.schedule()
    assert not outstanding_for(world, schedule.id)
    with open_uow(world.db) as uow:
        again = run_once(uow, schedule.id)
    assert again is not None and (again.refs_changed, again.links_flagged) == (0, 0)
    assert again.complete
    assert world.link_row(link)["status"] == "stale"
    assert len(events(world, "Link.Flagged")) == 1


def outstanding_for(world: ScheduleWorld, schedule_id: str) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return outstanding(uow.conn(), schedule_id)


def test_the_job_is_a_service_and_its_events_say_so(world: ScheduleWorld) -> None:
    one, two, [link] = linked_pair(world)
    world.publish(two)
    [flagged] = events(world, "Link.Flagged")
    assert (flagged.actor, flagged.source) == (SERVICE, SERVICE)
    assert flagged.payload["reason"].startswith(ORPHAN_REASON)
    three = world.upload(third_file(), name="third.xer")
    world.publish(three)
    [restored] = events(world, "Link.Repinned")
    assert (restored.actor, restored.source) == (SERVICE, SERVICE)
    assert world.link_row(link)["status"] == "active"
    assert world.schedule().current_snapshot_number == 3
    assert one != two


# --- 8. the module's own flags are recognised by their source, never by their words ---------------


def person_flag(world: ScheduleWorld, link_id: str, reason: str) -> None:
    with open_uow(world.db) as uow:
        handle_flag_link(uow, FlagLink(**BASE, link_id=link_id, status="stale", reason=reason))


def test_a_person_flag_with_the_modules_words_is_not_an_orphan_and_is_not_restored(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    mine, theirs = (
        world.link(world.record("R-1"), "A1990"),
        world.link(world.record("R-2"), "A1990"),
    )
    person_flag(world, theirs.stream_id, f"{ORPHAN_REASON} MAIN#2")  # the very words, by a person
    world.publish(two)  # the module flags `mine` only: `theirs` is already stale
    [listed] = orphan_ids(world)
    assert listed == mine.stream_id
    three = world.upload(third_file(), name="third.xer")
    world.publish(three)
    assert world.link_row(mine.stream_id)["status"] == "active"
    assert world.link_row(theirs.stream_id)["status"] == "stale"  # a person's flag stays


def test_a_link_flagged_by_the_module_and_flagged_again_by_a_person_is_theirs_now(
    world: ScheduleWorld,
) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    link = world.link(world.record(), "A1990")
    world.publish(two)
    with open_uow(world.db) as uow:  # a person takes it back, then flags it themselves
        handle_repin_link(uow, RepinLink(**BASE, link_id=link.stream_id))
    person_flag(world, link.stream_id, "see Anna")
    assert orphan_ids(world) == []
    world.publish(world.upload(third_file(), name="third.xer"))
    assert world.link_row(link.stream_id)["status"] == "stale"


def orphan_ids(world: ScheduleWorld) -> list[str]:
    schedule = world.schedule()
    with open_uow(world.db, readonly=True) as uow:
        return [o.link_id for o in resolver.orphaned_links(uow.conn(), schedule.id, scope=SCOPE)]


def test_a_retracted_link_is_not_flagged_by_the_job(world: ScheduleWorld) -> None:
    _, two, [link] = linked_pair(world)
    with open_uow(world.db) as uow:
        handle_retract_link(uow, RetractLink(**BASE, link_id=link, reason="mistake"))
    world.publish(two)
    assert events(world, "Link.Flagged") == []


# --- 6. a person cannot make unbounded work: caps on links and references -----------------------


def test_an_activity_takes_a_bounded_number_of_links(
    world: ScheduleWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "MAX_LINKS_PER_ACTIVITY", 2)
    world.define()
    world.publish(world.upload(first_xer()))
    one = world.link(world.record("R-1"), "A1230")
    world.link(world.record("R-2"), "A1230")
    with pytest.raises(TooManyLinksError, match="already has 2 links"):
        world.link(world.record("R-3"), "A1230")
    with open_uow(world.db) as uow:  # a retracted link frees its place
        handle_retract_link(uow, RetractLink(**BASE, link_id=one.stream_id, reason="x"))
    world.link(world.record("R-4"), "A1230")
    world.link(world.record("R-5"), "A1240")  # another activity has its own count


def test_snapshots_waiting_for_a_build_are_bounded_and_building_or_voiding_frees_a_place(
    world: ScheduleWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "MAX_OPEN_SNAPSHOTS", 2)
    world.define()
    first = world.open_snapshot().stream_id
    second = world.open_snapshot().stream_id
    with pytest.raises(TooManyOpenSnapshotsError, match="already has 2 snapshots waiting"):
        world.open_snapshot()
    world.void(first)  # a voided snapshot is not waiting
    third = world.open_snapshot().stream_id
    with pytest.raises(TooManyOpenSnapshotsError):
        world.open_snapshot()
    world.attach_xer(second, first_xer())
    world.start(second)
    world.work()  # built: Valid, no longer waiting
    assert world.snapshot(second).state == "Valid"
    world.open_snapshot()
    with pytest.raises(TooManyOpenSnapshotsError):  # third and the new one wait
        world.open_snapshot()
    assert world.snapshot(third).state == "Uploaded"


def test_a_generic_link_to_an_activity_reference_cannot_skip_the_cap(
    world: ScheduleWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only `LinkActivity` links to a reference: a generic `AddLink` would not count the links."""
    monkeypatch.setattr(limits, "MAX_LINKS_PER_ACTIVITY", 1)
    world.define()
    world.publish(world.upload(first_xer()))
    world.link(world.record("R-1"), "A1230")
    ref = world.ref("MAIN", "A1230")
    assert ref is not None
    other = world.record("R-2")
    with open_uow(world.db) as uow, pytest.raises(UnsupportedRecordTypeError, match="own command"):
        handle_add_link(uow, AddLink(**BASE, from_id=other, to_id=ref.id, relation="references"))
    with open_uow(world.db) as uow, pytest.raises(UnsupportedRecordTypeError, match="own command"):
        handle_suggest_link(
            uow, SuggestLink(**BASE, from_id=other, to_id=ref.id, relation="references")
        )
    with pytest.raises(TooManyLinksError):
        world.link(other, "A1230")  # the command still counts
    assert world.scalar("SELECT COUNT(*) FROM cur_links WHERE to_id = :r", r=ref.id) == 1


def test_a_schedule_takes_a_bounded_number_of_references(
    world: ScheduleWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(limits, "MAX_REFS_PER_SCHEDULE", 1)
    world.define()
    world.publish(world.upload(first_xer()))
    world.link(world.record("R-1"), "A1230")
    world.link(world.record("R-2"), "A1230")  # the same activity: no new reference
    with pytest.raises(TooManyReferencesError, match="already has 1 linked activities"):
        world.link(world.record("R-3"), "A1240")


# --- 5. the data date: bounded in the future, compared as a date --------------------------------


def test_a_data_date_far_after_today_cannot_be_published(world: ScheduleWorld) -> None:
    world.define()
    one = world.upload(first_xer())  # data date 2026-10-05
    clock = datetime(2026, 8, 1, tzinfo=UTC)
    with effective_time(clock), pytest.raises(FutureDataDateError, match="more than 31 days"):
        world.publish(one)
    assert world.snapshot(one).state == "Valid" and world.schedule().current_snapshot_id is None
    with effective_time(datetime(2026, 9, 10, tzinfo=UTC)):  # within the 31 days: allowed
        world.publish(one)
    assert world.schedule().current_snapshot_id == one


def test_the_day_after_the_allowance_is_refused(world: ScheduleWorld) -> None:
    world.define()
    one = world.upload(first_xer())  # 2026-10-05T08:00
    with (
        effective_time(datetime(2026, 9, 4, 7, 59, tzinfo=UTC)),
        pytest.raises(FutureDataDateError),
    ):
        world.publish(one)  # 2026-10-05 08:00 is 31 days and one minute away
    with effective_time(datetime(2026, 9, 4, 8, 0, tzinfo=UTC)):
        world.publish(one)


def test_the_series_is_ordered_by_dates_not_by_text(world: ScheduleWorld) -> None:
    """``999-...`` sorts after ``2026-...`` as text; as a date it is long before."""
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    with open_uow(world.db) as uow:
        for table, column, key in (
            ("cur_schedule_schedule_snapshot", "data_date", "id"),
            ("cur_schedule_schedule", "current_data_date", "current_snapshot_id"),
        ):
            uow.conn().execute(
                text(f"UPDATE {table} SET {column} = '999-12-31T08:00' WHERE {key} = :i"),
                {"i": one},
            )
    world.publish(two)  # as text "2026-10-12..." <= "999-..." would have been refused as stale
    assert world.schedule().current_snapshot_id == two


def test_a_stamp_is_a_date_whatever_its_padding() -> None:
    assert stamp("999-12-31T08:00") < stamp("2026-10-12T08:00")
    assert stamp("2026-1-5T8:0") == stamp("2026-01-05T08:00")
    for bad in (
        "",
        "2026-10-12",
        "2026-13-01T00:00",
        "x",
        "2026-10-12T08:00:30",
        "٢026-10-12T08:00",
    ):
        with pytest.raises(ValueError):
            stamp(bad)


def test_the_latest_finish_of_a_comparison_is_the_latest_as_a_date() -> None:
    from tl_mod_schedule.testing import make_activity

    late = make_activity("A2", early_finish="2026-10-30T16:00")
    early = make_activity("A1", early_finish="999-01-05T16:00")  # text would call this the latest
    data = compare.SnapshotData("M#1", 1, "2026-10-05T08:00", {"A1": early, "A2": late}, [], {})
    assert compare._latest(data) == "2026-10-30T16:00"  # pyright: ignore[reportPrivateUsage]


# --- 9. scope is enforced by the reads ----------------------------------------------------------


def test_a_read_in_another_project_finds_nothing(world: ScheduleWorld) -> None:
    one, two, [link] = linked_pair(world)
    world.publish(two)
    schedule = world.schedule()
    record = str(world.link_row(link)["from_id"])
    other = "project:OTHER"
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        for call in (
            lambda: resolver.resolve_snapshot(conn, schedule.id, scope=other),
            lambda: resolver.resolve_activity(conn, schedule.id, "A1230", scope=other),
            lambda: resolver.orphaned_links(conn, schedule.id, scope=other),
        ):
            with pytest.raises(ScheduleNotFoundError):
                call()
        snapshot = registry.get_snapshot(conn, two)
        assert snapshot is not None
        with pytest.raises(SnapshotNotFoundError):
            compare.load(conn, snapshot, scope=other)
        with pytest.raises(SnapshotNotFoundError):
            look_ahead(conn, snapshot, 4, scope=other)
        assert resolver.links_to_activities(conn, record, scope=other) == []
        assert len(resolver.links_to_activities(conn, record, scope=SCOPE)) == 1
        assert resolver.resolve_snapshot(conn, schedule.id, scope=SCOPE) is not None
        assert compare.load(conn, snapshot, scope=SCOPE).number == 2
        assert look_ahead(conn, snapshot, 4, scope=SCOPE).snapshot_number == 2


def test_the_links_of_a_record_are_limited_and_each_snapshot_is_found_once(
    world: ScheduleWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.define()
    world.publish(world.upload(first_xer()))
    record = world.record()
    for activity in ("A1230", "A1240", "A1250", "A1260", "A1270"):
        world.link(record, activity)
    calls: list[object] = []
    real = resolver.resolve_snapshot

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(resolver, "resolve_snapshot", counting)
    with open_uow(world.db, readonly=True) as uow:
        found = resolver.links_to_activities(uow.conn(), record, scope=SCOPE)
        assert len(found) == 5 and len(calls) == 1  # one schedule, one as-of: found once
        assert len(resolver.links_to_activities(uow.conn(), record, scope=SCOPE, limit=2)) == 2
        assert len(resolver.links_to_activities(uow.conn(), record, scope=SCOPE, limit=0)) == 1
    monkeypatch.setattr(resolver, "MAX_LINKS", 3)
    with open_uow(world.db, readonly=True) as uow:
        assert len(resolver.links_to_activities(uow.conn(), record, scope=SCOPE, limit=99)) == 3


def test_a_date_written_with_other_digits_names_no_snapshot(world: ScheduleWorld) -> None:
    world.define()
    world.publish(world.upload(first_xer()))
    schedule = world.schedule()
    with open_uow(world.db, readonly=True) as uow:
        arabic = "٢٠٢٦-١٠-٠٨"
        assert resolver.resolve_snapshot(uow.conn(), schedule.id, arabic, scope=SCOPE) is None
        assert resolver.resolve_snapshot(uow.conn(), schedule.id, "2026-10-04", scope=SCOPE) is None
        found = resolver.resolve_snapshot(uow.conn(), schedule.id, "2026-10-05", scope=SCOPE)
        assert found is not None and found.number == 1


def test_the_baseline_is_a_published_snapshot_never_a_later_upload(world: ScheduleWorld) -> None:
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    three = world.upload(third_file(), name="third.xer")  # Valid, not published
    with open_uow(world.db, readonly=True) as uow:
        row = registry.get_snapshot(uow.conn(), three)
        assert row is not None
        before = registry.previous_of(uow.conn(), row)
    assert before is not None and before.id == one  # not `two`, which is merely Valid
    world.publish(two)
    with open_uow(world.db, readonly=True) as uow:
        row = registry.get_snapshot(uow.conn(), three)
        assert row is not None
        before = registry.previous_of(uow.conn(), row)
    assert before is not None and before.id == two


# --- 2. after a restore the flagging waits for the typed rows -----------------------------------


def test_a_lost_flagging_job_is_queued_again_but_not_before_the_rows_are_back(
    world: ScheduleWorld,
) -> None:
    _, two, [link] = linked_pair(world)
    world.publish(two, check=False)
    with open_uow(world.db) as uow:
        uow.conn().execute(text("DELETE FROM job_queue"))  # a restore
    with open_uow(world.db) as uow:
        assert requeue_orphans(uow.conn()) == 1
        assert requeue_orphans(uow.conn()) == 0  # one run is queued: not another
    assert queued_flag_jobs(world) == 1
    world.work()
    assert world.link_row(link)["status"] == "stale"
    with open_uow(world.db) as uow:
        assert requeue_orphans(uow.conn()) == 0  # nothing is outstanding now


def test_with_the_typed_rows_missing_nothing_is_flagged_or_queued(world: ScheduleWorld) -> None:
    _, two, [link] = linked_pair(world)
    world.publish(two, check=False)
    with open_uow(world.db) as uow:
        uow.conn().execute(text("DELETE FROM job_queue"))
        uow.conn().execute(text("DELETE FROM sched_activity"))  # a restore without reconcile
    schedule = world.schedule()
    assert not outstanding_for(world, schedule.id)
    with open_uow(world.db) as uow:
        assert requeue_orphans(uow.conn()) == 0
    with open_uow(world.db) as uow, pytest.raises(TypedRowsMissingError, match="reconcile"):
        run_once(uow, schedule.id)
    assert world.link_row(link)["status"] == "active"  # not one activity was called gone


# --- 7. text of the commands --------------------------------------------------------------------

BAD = ["\n", "\x85", chr(0x2028), chr(0x202E), chr(0x200F), "\x00", "\x7f"]


@pytest.mark.parametrize("char", BAD, ids=[f"U+{ord(c):04X}" for c in BAD])
def test_every_text_field_of_the_schedule_commands_refuses_control_and_direction_characters(
    char: str,
) -> None:
    bad = f"x{char}y"
    cases: list[tuple[type, dict[str, Any]]] = [
        (DefineSchedule, {"code": "MAIN", "name": bad}),
        (DefineSchedule, {"code": "MAIN", "name": "n", "owner": bad}),
        (DefineSchedule, {"code": "MAIN", "name": "n", "p6_project": bad}),
        (OpenScheduleSnapshot, {"schedule_id": "s", "p6_project": bad}),
        (VoidScheduleSnapshot, {"snapshot_id": "s", "reason": bad}),
        (LinkActivity, {"from_id": "a", "schedule_id": "s", "activity_id": bad}),
        (LinkActivity, {"from_id": "a", "schedule_id": "s", "activity_id": "A1", "note": bad}),
    ]
    for model, fields in cases:
        with pytest.raises(ValidationError) as caught:
            model(**BASE, **fields)
        assert "control" in str(caught.value)
        assert all(f"x{char}" not in e["msg"] for e in caught.value.errors())  # not echoed


def test_ordinary_names_in_other_scripts_pass() -> None:
    made = DefineSchedule(**BASE, code="MAIN", name="Hauptterminplan Überholung €", owner="م")
    assert made.name.startswith("Hauptterminplan")


# --- 2. the typed rows go in unchanged on both databases ----------------------------------------


def test_the_typed_rows_are_written_and_read_back_unchanged(world: ScheduleWorld) -> None:
    awkward = [
        "quote \" and ' and \\ back",
        'json {"a": [1, 2]}',
        "null",
        "é€\U0001f600",
        " spaced ",
        "",
    ]
    snap = Snapshot(project={})
    snap.tables["calendars"] = [("1", awkward[0], 8.0, 40.0, None, None, True, 1)]
    snap.tables["wbs"] = [
        ("100", None, "BIG", awkward[1], "BIG", True, 1),
        ("101", "100", "W", awkward[3], "BIG > W", False, 2),
    ]
    snap.tables["activities"] = [
        (
            f"A{n}", f"T{n}", awkward[n], "100", "BIG", "task", "not_started", "1", 0.1, None,
            "2026-10-12T08:00", None, None, None, None, None, None, None, -1.5, 1e-3, 33.33,
            awkward[2], None, None, n % 2 == 0, False, n + 1,
        )
        for n in range(6)
    ]  # fmt: skip
    snap.tables["relationships"] = [("A0", "A1", "FS", 0.5, 1), ("A1", "A2", "SS", -8.0, 2)]
    snap.tables["codes"] = [("A0", awkward[0], awkward[1], awkward[3], 1)]
    snap.tables["udfs"] = [
        ("A0", "uf", None, "text", awkward[5], 1),
        ("A1", "uf", awkward[0], "number", "12", 2),
    ]
    with open_uow(world.db) as uow:
        typed_store.write_snapshot(uow.conn(), SCOPE, "SNAPX", snap)
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        assert typed_store.count_rows(conn, "SNAPX") == {k: len(v) for k, v in snap.tables.items()}
        read = registry.activities(conn, "SNAPX")
        assert [a.name for a in read] == awkward
        assert [a.original_duration_hr for a in read] == [0.1] * 6
        assert [a.free_float_hr for a in read] == [1e-3] * 6
        assert [a.critical for a in read] == [n % 2 == 0 for n in range(6)]
        assert [a.constraint_type for a in read] == [None] * 6
        assert [(r.pred_activity_id, r.lag_hr) for r in registry.relationships(conn, "SNAPX")] == [
            ("A0", 0.5),
            ("A1", -8.0),
        ]
        rows = conn.execute(text("SELECT code_type, code_name FROM sched_activity_code")).all()
        assert [tuple(r) for r in rows] == [(awkward[0], awkward[3])]
        udf = conn.execute(text("SELECT udf_label, value FROM sched_udf_value ORDER BY seq")).all()
        assert [tuple(r) for r in udf] == [(None, ""), (awkward[0], "12")]
        calendar = conn.execute(
            text("SELECT name, month_hr, is_default FROM sched_calendar")
        ).first()
        assert calendar is not None and (calendar.name, calendar.month_hr) == (awkward[0], None)
        assert bool(calendar.is_default) is True
    # the json text never reaches the SQL: a hostile value is data
    assert json.dumps(awkward)  # the cells survive a JSON round trip too


def test_the_lease_outlasts_the_envelope_and_the_settle() -> None:
    from tl_core.derivation.envelope import DEFAULT_TIMEOUT_S

    assert limits.BUILD_LEASE_S >= 5 * (DEFAULT_TIMEOUT_S + 60)  # read + settle at the limits: 60 s


# --- a restore that has not been reconciled must not read as "nothing there" -------------------


def test_every_read_refuses_while_the_typed_rows_are_missing_and_works_after_reconcile(
    world: ScheduleWorld,
) -> None:
    _, two, [link] = linked_pair(world)
    world.publish(two)
    reads = {
        "activities": lambda c: views.activity_page(c, SCOPE, "MAIN"),
        "activity": lambda c: views.activity_detail(c, SCOPE, "MAIN", "A1230"),
        "comparison": lambda c: views.comparison(c, SCOPE, "MAIN"),
        "look-ahead": lambda c: views.look_ahead_view(c, SCOPE, "MAIN"),
        "resolution": lambda c: views.resolution(c, SCOPE, "MAIN", "A1230"),
        "resolution as of": lambda c: views.resolution(c, SCOPE, "MAIN", "A1230", 1),
        "trend": lambda c: views.float_trend(c, SCOPE, "MAIN", "A1230"),
        "activity links": lambda c: views.activity_links(c, SCOPE, world.link_row(link)["from_id"]),
    }

    def attempt(name: str) -> None:
        with open_uow(world.db, readonly=True) as uow:
            reads[name](uow.conn())

    with open_uow(world.db) as uow:
        uow.conn().execute(text("DELETE FROM sched_activity"))
    for name in reads:
        with pytest.raises(TypedRowsMissingError, match="tl xer reconcile"):
            attempt(name)
    reconcile_tables(world.db, world.files)
    for name in reads:
        attempt(name)  # all well again


def test_a_snapshot_that_lost_only_some_rows_is_refused_too(world: ScheduleWorld) -> None:
    linked_pair(world)  # snapshot 1 is the current one
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("DELETE FROM sched_activity WHERE activity_id = 'A1230' AND snapshot_id = :i"),
            {"i": world.schedule().current_snapshot_id},
        )
    with open_uow(world.db, readonly=True) as uow, pytest.raises(TypedRowsMissingError):
        views.activity_page(uow.conn(), SCOPE, "MAIN")


def test_no_dialect_specific_sql_lives_in_the_module() -> None:
    """AGENTS rule 5: SQLite- or Postgres-specific SQL is under tl_adapters (`bulk_insert`)."""
    from pathlib import Path

    source = Path(limits.__file__).parent
    found = {
        f"{path.name}: {word}"
        for path in sorted(source.rglob("*.py"))
        for word in ("dialect.name", "json_array_elements", "FOR UPDATE SKIP LOCKED")
        if word in path.read_text()
    }
    assert found == set()
