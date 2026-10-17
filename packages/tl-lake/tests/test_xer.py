"""P6 schedule snapshots in the lake: silver, bronze, the mart, rebuilds and what is left out."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from builder import LedgerBuilder
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_lake import LakeConfig, LakeQueryService, LakeSyncError, read_snapshot, sync_lake
from tl_lake.duck import lake_tables, open_lake
from tl_lake.xer import (
    ACTIVITY_TABLE,
    LOADED_TABLE,
    SNAPSHOT_TABLE,
    LedgerSnapshot,
    XerSyncResult,
    sync_xer,
)
from tl_lake.xer import _load_bronze as load_bronze  # pyright: ignore[reportPrivateUsage]
from tl_mod_schedule.reconcile import reconcile_tables
from tl_mod_schedule.store import SnapshotFiles
from tl_mod_schedule.testing import ScheduleWorld
from tl_xer.bundle import write_bundle
from tl_xer.reader import RawTable, RawXer
from tl_xer.synth import make_xer, slipped, week_pair


class Lakes:
    """A ledger with a schedule world on it, a lake and the calls the tests make."""

    def __init__(self, ledger: LedgerBuilder, lake: LakeConfig, tmp_path: Path) -> None:
        self.ledger, self.lake = ledger, lake
        self.world = ScheduleWorld(ledger.db, tmp_path / "objects")
        self.store = SnapshotFiles(self.world.files)

    def raw(self, scope: str, file_id: str, sha256: str) -> bytes:
        with open_uow(self.world.db, readonly=True) as uow:
            return self.store.read_raw(uow, scope, file_id)

    def sync(self, *, bronze: bool = True, rebuild: bool = False, **more: Any) -> XerSyncResult:
        engine = self.ledger.engine()
        try:
            with read_snapshot(engine) as conn:
                sync_lake(self.lake, conn, rebuild=rebuild)
            with read_snapshot(engine) as conn:
                return sync_xer(self.lake, conn, self.raw if bronze else None, **more)
        finally:
            engine.dispose()

    def rows(self, sql: str) -> list[tuple[Any, ...]]:
        with open_lake(self.lake, write=False) as con:
            return con.execute(sql).fetchall()

    def tables(self) -> dict[str, list[tuple[str, str]]]:
        with open_lake(self.lake, write=False) as con:
            return lake_tables(con)


@pytest.fixture
def lakes(ledger: LedgerBuilder, lake: LakeConfig, tmp_path: Path) -> Lakes:
    return Lakes(ledger, lake, tmp_path)


def published_pair(lakes: Lakes) -> tuple[str, str]:
    world = lakes.world
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    world.publish(two)
    return one, two


def dump(lakes: Lakes) -> dict[str, list[tuple[Any, ...]]]:
    """Every schedule table of the lake, rows sorted, for a comparison."""
    out: dict[str, list[tuple[Any, ...]]] = {}
    for name in sorted(lakes.tables()):
        if name.startswith(("xer_", "schedule_", "mart_")) or name == LOADED_TABLE:
            out[name] = sorted(lakes.rows(f"SELECT * FROM lake.main.{name}"), key=repr)
    return out


# --- silver --------------------------------------------------------------------------------------


def test_the_built_snapshots_and_their_activities_are_in_the_lake(lakes: Lakes) -> None:
    published_pair(lakes)
    result = lakes.sync()
    assert (result.loaded, result.dropped, result.bronze, result.waiting) == (2, 0, 2, 0)
    assert result.activity_rows == 42 and result.snapshot_id is not None
    states = lakes.rows(
        "SELECT schedule_code, number, state, is_current, data_date, activity_count "
        f"FROM lake.main.{SNAPSHOT_TABLE} ORDER BY number"
    )
    assert [(r[0], r[1], r[2], r[3], r[5]) for r in states] == [
        ("MAIN", 1, "Superseded", False, 21),
        ("MAIN", 2, "Published", True, 21),
    ]
    assert str(states[1][4]) == "2026-10-12 08:00:00"
    [row] = lakes.rows(
        "SELECT total_float_hr, total_float_days, critical, early_finish, snapshot_number, "
        f"schedule_code FROM lake.main.{ACTIVITY_TABLE} "
        "WHERE activity_id = 'A1230' AND snapshot_number = 2"
    )
    assert row[:3] == (32.0, 4.0, False) and str(row[3]) == "2026-10-19 16:00:00"
    assert row[4:] == (2, "MAIN")
    assert lakes.rows(f"SELECT count(*) FROM lake.main.{ACTIVITY_TABLE}")[0][0] == 42


def test_the_floats_are_days_of_the_activitys_own_calendar(lakes: Lakes) -> None:
    published_pair(lakes)
    lakes.sync()
    rows = lakes.rows(
        f"SELECT snapshot_number, total_float_days FROM lake.main.{ACTIVITY_TABLE} "
        "WHERE activity_id = 'A1230' ORDER BY snapshot_number"
    )
    assert rows == [(1, 9.0), (2, 4.0)]
    # a calendar with a ten hour day: 40 hours of float are 4 days there
    with open_uow(lakes.world.db) as uow:
        uow.conn().execute(text("UPDATE sched_calendar SET day_hr = 10"))
    lakes.sync(rebuild=True)
    rows = lakes.rows(
        f"SELECT snapshot_number, total_float_days FROM lake.main.{ACTIVITY_TABLE} "
        "WHERE activity_id = 'A1230' ORDER BY snapshot_number"
    )
    assert rows == [(1, 7.2), (2, 3.2)]
    # a calendar that says 0 hours a day is a calendar of the default 8
    with open_uow(lakes.world.db) as uow:
        uow.conn().execute(text("UPDATE sched_calendar SET day_hr = 0"))
    lakes.sync(rebuild=True)
    rows = lakes.rows(
        f"SELECT snapshot_number, total_float_days FROM lake.main.{ACTIVITY_TABLE} "
        "WHERE activity_id = 'A1230' ORDER BY snapshot_number"
    )
    assert rows == [(1, 9.0), (2, 4.0)]


def test_a_second_sync_with_nothing_new_makes_no_lake_snapshot(lakes: Lakes) -> None:
    published_pair(lakes)
    first = lakes.sync()
    again = lakes.sync()
    assert first.snapshot_id is not None and again.up_to_date and again.snapshot_id is None
    assert (again.loaded, again.dropped, again.bronze) == (0, 0, 0)


def test_a_state_change_replaces_the_snapshot_rows_and_the_mart(lakes: Lakes) -> None:
    world = lakes.world
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    lakes.sync()
    assert lakes.rows(f"SELECT state FROM lake.main.{SNAPSHOT_TABLE} ORDER BY number") == [
        ("Published",),
        ("Valid",),
    ]
    assert lakes.rows("SELECT count(*) FROM lake.main.mart_float_trend")[0][0] == 21  # one only
    world.publish(two)
    later = lakes.sync()
    assert (later.loaded, later.dropped) == (0, 0) and later.snapshot_id is not None
    assert lakes.rows(f"SELECT state FROM lake.main.{SNAPSHOT_TABLE} ORDER BY number") == [
        ("Superseded",),
        ("Published",),
    ]
    assert lakes.rows("SELECT count(*) FROM lake.main.mart_float_trend")[0][0] == 42


def test_a_snapshot_that_is_voided_after_it_was_loaded_is_taken_out(lakes: Lakes) -> None:
    world = lakes.world
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    lakes.sync()
    assert lakes.rows(f"SELECT count(*) FROM lake.main.{ACTIVITY_TABLE}")[0][0] == 42
    world.void(two)
    result = lakes.sync()
    assert (result.loaded, result.dropped) == (0, 1)
    assert lakes.rows(f"SELECT DISTINCT snapshot_number FROM lake.main.{ACTIVITY_TABLE}") == [(1,)]
    assert lakes.rows(f"SELECT count(*) FROM lake.main.{LOADED_TABLE}")[0][0] == 1
    assert {r[0] for r in lakes.rows("SELECT DISTINCT _snapshot_id FROM lake.main.xer_task")} == {
        world.snapshot(one).id
    }


# --- bronze --------------------------------------------------------------------------------------


def test_every_table_of_the_file_is_in_the_lake_as_text_with_its_row_numbers(
    lakes: Lakes,
) -> None:
    one, _ = published_pair(lakes)
    lakes.sync()
    names = set(lakes.tables())
    assert {"xer_project", "xer_projwbs", "xer_calendar", "xer_task", "xer_taskpred"} <= names
    snapshot = lakes.world.snapshot(one).id
    rows = lakes.rows(
        "SELECT _row_no, task_code, task_name FROM lake.main.xer_task "
        f"WHERE _snapshot_id = '{snapshot}' ORDER BY _row_no"
    )
    assert [r[0] for r in rows] == list(range(1, 22))
    assert "A1230" in {r[1] for r in rows}
    types = dict(lakes.tables()["xer_task"])
    assert types["_snapshot_id"] == "VARCHAR" and types["_row_no"] == "BIGINT"
    assert types["task_code"] == "VARCHAR" and types["total_float_hr_cnt"] == "VARCHAR"
    assert lakes.rows("SELECT count(*) FROM lake.main.xer_task")[0][0] == 42


def test_without_a_reader_the_bronze_tables_wait_and_a_later_sync_loads_them(
    lakes: Lakes,
) -> None:
    published_pair(lakes)
    first = lakes.sync(bronze=False)
    assert (first.loaded, first.bronze, first.bronze_waiting) == (2, 0, 2)
    assert not any(name.startswith("xer_") for name in lakes.tables())
    assert lakes.rows(f"SELECT bronze FROM lake.main.{LOADED_TABLE}") == [(False,), (False,)]
    second = lakes.sync()
    assert (second.loaded, second.bronze, second.bronze_waiting) == (0, 2, 0)
    assert second.snapshot_id is not None
    assert lakes.rows(f"SELECT bronze FROM lake.main.{LOADED_TABLE}") == [(True,), (True,)]
    assert lakes.rows("SELECT count(*) FROM lake.main.xer_task")[0][0] == 42


def test_a_snapshot_that_arrives_later_gets_its_bronze_tables_once(lakes: Lakes) -> None:
    published_pair(lakes)
    lakes.sync()
    later = make_xer(slipped(week_pair()[1], days=3, codes=("A1230",)))
    lakes.world.upload(later, "MAIN", name="third.xer")
    waiting = lakes.sync(bronze=False)
    assert (waiting.loaded, waiting.bronze, waiting.bronze_waiting) == (1, 0, 1)
    done = lakes.sync()
    assert (done.loaded, done.bronze, done.bronze_waiting) == (0, 1, 0)
    assert lakes.sync().up_to_date
    assert lakes.rows("SELECT count(*) FROM lake.main.xer_task")[0][0] == 63  # 21 each, once
    assert lakes.rows(f"SELECT bronze FROM lake.main.{LOADED_TABLE}") == [(True,)] * 3


def test_field_names_are_lowercased_and_a_table_grows_the_columns_a_file_adds(
    lakes: Lakes, lake: LakeConfig
) -> None:
    def bundle(columns: tuple[str, ...], row: tuple[str, ...]) -> tuple[bytes, str]:
        table = RawTable("Thing", columns, (row,))
        return write_bundle(RawXer(("19.12",), (table,), "utf-8", 1, 1))

    def snapshot(snapshot_id: str, sha: str) -> LedgerSnapshot:
        return LedgerSnapshot(
            snapshot_id, "project:P123", "MAIN", 1, "Valid", False, None, None, None,
            (None,) * 6, None, None, None, None, None, None, None, "file", sha,
        )  # fmt: skip

    first, first_sha = bundle(("Thing_ID", "Name"), ("1", "one"))
    second, second_sha = bundle(("THING_ID", "Name", "Extra"), ("2", "two", "x"))
    with open_lake(lake, write=True) as con:
        load_bronze(con, lake, snapshot("S1", first_sha), lambda *_: first, 100)
        load_bronze(con, lake, snapshot("S2", second_sha), lambda *_: second, 100)
    types = dict(lakes.tables()["xer_thing"])
    assert list(types) == ["_snapshot_id", "_row_no", "thing_id", "name", "extra"]
    assert lakes.rows("SELECT _snapshot_id, thing_id, name, extra FROM lake.main.xer_thing") == [
        ("S1", "1", "one", None),
        ("S2", "2", "two", "x"),
    ]


def test_a_bad_bundle_fails_the_sync_and_leaves_the_lake_as_it_was(lakes: Lakes) -> None:
    published_pair(lakes)
    lakes.sync(bronze=False)
    before = dump(lakes)

    def broken(scope: str, file_id: str, sha256: str) -> bytes:
        return b"not a gzip stream"

    engine = lakes.ledger.engine()
    try:
        with read_snapshot(engine) as conn, pytest.raises(LakeSyncError, match="raw bundle"):
            sync_xer(lakes.lake, conn, broken)
    finally:
        engine.dispose()
    assert dump(lakes) == before


def test_a_bundle_that_is_not_the_one_recorded_is_refused(lakes: Lakes) -> None:
    one, two = published_pair(lakes)
    other = lakes.world.snapshot(two)

    def swapped(scope: str, file_id: str, sha256: str) -> bytes:
        return lakes.raw(scope, other.raw_file_id or "", sha256)  # snapshot 2's bundle for both

    engine = lakes.ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lakes.lake, conn)
        with read_snapshot(engine) as conn, pytest.raises(LakeSyncError, match="raw bundle"):
            sync_xer(lakes.lake, conn, swapped)
    finally:
        engine.dispose()


# --- the mart ------------------------------------------------------------------------------------


def test_the_float_trend_follows_each_activity_through_the_published_snapshots(
    lakes: Lakes,
) -> None:
    published_pair(lakes)
    lakes.sync()
    rows = lakes.rows(
        "SELECT snapshot_number, total_float_days, previous_float_days, float_change_days, "
        "eroded, state FROM lake.main.mart_float_trend WHERE activity_id = 'A1230' "
        "ORDER BY snapshot_number"
    )
    assert rows == [
        (1, 9.0, None, None, False, "Superseded"),
        (2, 4.0, 9.0, -5.0, True, "Published"),
    ]
    only_first = lakes.rows(
        "SELECT snapshot_number, float_change_days FROM lake.main.mart_float_trend "
        "WHERE activity_id = 'A1990'"
    )
    assert only_first == [(1, None)]  # it left in snapshot 2
    new = lakes.rows(
        "SELECT previous_float_days, eroded FROM lake.main.mart_float_trend "
        "WHERE activity_id = 'A2500'"
    )
    assert new == [(None, False)]  # it arrived in snapshot 2
    eroded = lakes.rows(
        "SELECT count(*) FROM lake.main.mart_float_trend WHERE eroded AND snapshot_number = 2"
    )
    assert eroded[0][0] == 8


def test_two_schedules_with_the_same_activity_ids_have_trends_of_their_own(lakes: Lakes) -> None:
    published_pair(lakes)
    world = lakes.world
    world.define("OTHER")
    one, two = world.two_weeks("OTHER")
    world.publish(one)
    world.publish(two)
    lakes.sync()
    rows = lakes.rows(
        "SELECT schedule_code, snapshot_number, previous_float_days, float_change_days "
        "FROM lake.main.mart_float_trend WHERE activity_id = 'A1230' "
        "ORDER BY schedule_code, snapshot_number"
    )
    assert rows == [
        ("MAIN", 1, None, None),
        ("MAIN", 2, 9.0, -5.0),
        ("OTHER", 1, None, None),
        ("OTHER", 2, 9.0, -5.0),
    ]
    assert lakes.rows("SELECT count(*) FROM lake.main.mart_float_trend")[0][0] == 84
    codes = lakes.rows(f"SELECT schedule_code, count(*) FROM lake.main.{ACTIVITY_TABLE} GROUP BY 1")
    assert sorted(codes) == [("MAIN", 42), ("OTHER", 42)]


# --- rebuilds and restores -----------------------------------------------------------------------


def test_a_rebuild_equals_the_incremental_result(lakes: Lakes) -> None:
    world = lakes.world
    world.define()
    one, two = world.two_weeks()
    world.publish(one)
    lakes.sync()
    world.publish(two)
    lakes.sync()
    later = make_xer(slipped(week_pair()[1], days=3, codes=("A1230",)))
    third = world.upload(later, "MAIN", name="third.xer")  # built, never published
    lakes.sync()
    world.void(third)
    lakes.sync()
    incremental = dump(lakes)
    assert incremental[ACTIVITY_TABLE]
    lakes.sync(rebuild=True)
    assert dump(lakes) == incremental


def test_a_snapshot_without_its_typed_rows_waits_until_they_are_back(lakes: Lakes) -> None:
    one, two = published_pair(lakes)
    with open_uow(lakes.world.db) as uow:
        uow.conn().execute(text("DELETE FROM sched_activity WHERE snapshot_id = :i"), {"i": two})
    waiting = lakes.sync()
    assert (waiting.loaded, waiting.waiting) == (1, 1)
    assert lakes.rows(f"SELECT DISTINCT snapshot_number FROM lake.main.{ACTIVITY_TABLE}") == [(1,)]
    reconcile_tables(lakes.world.db, lakes.world.files)
    done = lakes.sync()
    assert (done.loaded, done.waiting) == (1, 0)
    assert lakes.rows(f"SELECT count(*) FROM lake.main.{ACTIVITY_TABLE}")[0][0] == 42


def test_a_ledger_with_no_schedule_adds_no_schedule_tables_to_the_lake(lakes: Lakes) -> None:
    result = lakes.sync()
    assert result.up_to_date and (result.loaded, result.dropped, result.waiting) == (0, 0, 0)
    assert not any(
        name.startswith(("xer_", "schedule_", "mart_", "_tl_xer")) for name in lakes.tables()
    )
    assert lakes.sync().up_to_date


def test_a_small_chunk_gives_the_same_tables(lakes: Lakes) -> None:
    published_pair(lakes)
    lakes.sync()
    whole = dump(lakes)
    lakes.sync(rebuild=True, chunk=7)
    assert dump(lakes) == whole


def test_the_guarded_query_service_reads_the_new_tables(lakes: Lakes) -> None:
    published_pair(lakes)
    lakes.sync()
    answer = LakeQueryService(lakes.lake).query(
        "SELECT activity_id, float_change_days FROM mart_float_trend "
        "WHERE snapshot_number = 2 AND eroded ORDER BY float_change_days, activity_id LIMIT 2",
        caller="test",
    )
    assert len(answer.rows) == 2 and not answer.truncated
    assert all(row[1] < 0 for row in answer.rows)
