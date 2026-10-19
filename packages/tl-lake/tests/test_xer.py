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
from tl_lake.schema import Column
from tl_lake.xer import (
    ACTIVITY_TABLE,
    FAILED_TABLE,
    LOADED_TABLE,
    MAX_BRONZE_COLUMNS,
    P6_TABLES,
    SNAPSHOT_TABLE,
    LedgerSnapshot,
    SnapshotLoadError,
    XerSyncResult,
    sync_xer,
)
from tl_lake.xer import _ensure_table as ensure_table  # pyright: ignore[reportPrivateUsage]
from tl_lake.xer import _load_bronze as load_bronze  # pyright: ignore[reportPrivateUsage]
from tl_lake.xer import _sync_bronze as sync_bronze  # pyright: ignore[reportPrivateUsage]
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


def snapshot(snapshot_id: str, sha: str) -> LedgerSnapshot:
    return LedgerSnapshot(
        snapshot_id, "project:P123", "MAIN", 1, "Valid", False, None, None, None,
        (None,) * 6, None, None, None, None, None, None, None, "file", sha,
    )  # fmt: skip


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
        table = RawTable("TASK", columns, (row,))
        return write_bundle(RawXer(("19.12",), (table,), "utf-8", 1, 1))

    first, first_sha = bundle(("Task_ID", "Name"), ("1", "one"))
    second, second_sha = bundle(("TASK_ID", "Name", "Extra"), ("2", "two", "x"))
    with open_lake(lake, write=True) as con:
        load_bronze(con, lake, snapshot("S1", first_sha), lambda *_: first, 100)
        load_bronze(con, lake, snapshot("S2", second_sha), lambda *_: second, 100)
    types = dict(lakes.tables()["xer_task"])
    assert list(types) == ["_snapshot_id", "_row_no", "task_id", "name", "extra"]
    assert lakes.rows("SELECT _snapshot_id, task_id, name, extra FROM lake.main.xer_task") == [
        ("S1", "1", "one", None),
        ("S2", "2", "two", "x"),
    ]


def failed_ids(lakes: Lakes) -> list[str]:
    rows = lakes.rows(f"SELECT snapshot_id FROM lake.main.{FAILED_TABLE}")
    return sorted(str(r[0]) for r in rows)


def damaged_content(monkeypatch: pytest.MonkeyPatch, only: str | None = None) -> None:
    """The hash of the bundle matches but its content cannot be read (for ``only``, or all)."""
    from tl_xer.bundle import BundleError, read_bundle

    real = read_bundle
    first_blob: dict[str, bytes] = {}

    def read(blob: bytes) -> Any:
        if only is None or (only == "first" and blob == first_blob.setdefault("blob", blob)):
            raise BundleError("damaged")
        return real(blob)

    monkeypatch.setattr("tl_lake.xer.read_bundle", read)


def test_content_the_lake_cannot_read_is_recorded_and_skipped_and_the_pass_goes_on(
    lakes: Lakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, two = published_pair(lakes)
    lakes.sync(bronze=False)
    before = dump(lakes)
    damaged_content(monkeypatch)
    result = lakes.sync()
    again = lakes.sync()
    assert (result.bronze, result.failed, result.bronze_waiting) == (0, 2, 0)
    assert result.snapshot_id is not None  # the failures were recorded
    assert again.up_to_date and again.failed == 2  # and are not tried again
    assert failed_ids(lakes) == sorted([one, two])
    assert not any(name.startswith("xer_") for name in lakes.tables())
    after = dump(lakes)
    assert {k: v for k, v in after.items() if k != FAILED_TABLE} == before
    assert lakes.rows(f"SELECT bronze FROM lake.main.{LOADED_TABLE}") == [(False,), (False,)]


def test_one_snapshot_with_unreadable_content_costs_only_that_snapshot(
    lakes: Lakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, two = published_pair(lakes)
    damaged_content(monkeypatch, only="first")
    result = lakes.sync()
    assert (result.loaded, result.bronze, result.failed) == (2, 1, 1)
    assert failed_ids(lakes) == [one]
    assert lakes.rows("SELECT DISTINCT _snapshot_id FROM lake.main.xer_task") == [(two,)]
    assert lakes.rows(f"SELECT count(*) FROM lake.main.{ACTIVITY_TABLE}")[0][0] == 42  # whole


def test_a_snapshot_that_stops_being_built_leaves_the_failed_list(
    lakes: Lakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, two = published_pair(lakes)
    later = make_xer(slipped(week_pair()[1], days=3, codes=("A1230",)))
    third = lakes.world.upload(later, "MAIN", name="t.xer")
    damaged_content(monkeypatch)
    assert lakes.sync().failed == 3
    lakes.world.void(third)
    lakes.sync(bronze=False)
    assert failed_ids(lakes) == sorted([one, two])


def test_a_bundle_that_is_not_gzip_stops_the_pass_and_leaves_the_lake_as_it_was(
    lakes: Lakes,
) -> None:
    published_pair(lakes)
    lakes.sync(bronze=False)
    before = dump(lakes)

    def broken(scope: str, file_id: str, sha256: str) -> bytes:
        return b"not a gzip stream"

    engine = lakes.ledger.engine()
    try:
        with read_snapshot(engine) as conn, pytest.raises(LakeSyncError, match="not the one"):
            sync_xer(lakes.lake, conn, broken)
    finally:
        engine.dispose()
    assert dump(lakes) == before
    assert failed_ids(lakes) == []  # a hash that does not match is not the file's fault


def test_a_bundle_that_is_not_the_one_recorded_is_refused(lakes: Lakes) -> None:
    one, two = published_pair(lakes)
    other = lakes.world.snapshot(two)

    def swapped(scope: str, file_id: str, sha256: str) -> bytes:
        return lakes.raw(scope, other.raw_file_id or "", sha256)  # snapshot 2's bundle for both

    engine = lakes.ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lakes.lake, conn)
        with read_snapshot(engine) as conn, pytest.raises(LakeSyncError, match="not the one"):
            sync_xer(lakes.lake, conn, swapped)
    finally:
        engine.dispose()
    assert failed_ids(lakes) == []


def test_a_bundle_the_reader_would_now_refuse_cannot_stop_the_lake(
    lakes: Lakes, lake: LakeConfig
) -> None:
    """Columns `A` and `a` fold to one name: the catalog refuses it, the snapshot is skipped."""
    table = RawTable("TASK", ("A", "a"), (("1", "2"),))
    blob, sha = write_bundle(RawXer(("19.12",), (table,), "utf-8", 2, 1))
    with open_lake(lake, write=True) as con:
        tables = lake_tables(con)
        for name, columns in (
            (
                LOADED_TABLE,
                [Column("snapshot_id", "VARCHAR", True), Column("bronze", "BOOLEAN", True)],
            ),
            (
                FAILED_TABLE,
                [Column("snapshot_id", "VARCHAR", True), Column("reason", "VARCHAR", True)],
            ),
        ):
            ensure_table(con, tables, name, columns)
        con.execute(f"INSERT INTO lake.main.{LOADED_TABLE} VALUES ('S1', FALSE)")
        with pytest.raises(SnapshotLoadError):
            load_bronze(con, lake, snapshot("S1", sha), lambda *_: blob, 100)
        assert sync_bronze(con, lake, snapshot("S1", sha), lambda *_: blob, 100) is None
        assert con.execute(f"SELECT snapshot_id FROM lake.main.{FAILED_TABLE}").fetchall() == [
            ("S1",)
        ]
        assert con.execute(f"SELECT bronze FROM lake.main.{LOADED_TABLE}").fetchall() == [(False,)]
    assert "xer_task" not in lakes.tables()  # the half-made table was rolled back


def test_only_the_tables_p6_defines_get_a_lake_table_of_their_own(
    lakes: Lakes, lake: LakeConfig
) -> None:
    junk = [RawTable(f"Junk{n}", ("a", "b"), (("x", ""),)) for n in range(250)]
    task = RawTable("TASK", ("task_id", "task_code"), (("1", "A1"),))
    blob, sha = write_bundle(RawXer(("19.12",), (task, *junk), "utf-8", 504, 1))
    with open_lake(lake, write=True) as con:
        load_bronze(con, lake, snapshot("S1", sha), lambda *_: blob, 100)
    names = sorted(n for n in lakes.tables() if n.startswith("xer_"))
    assert names == ["xer_other", "xer_task"]
    assert lakes.rows("SELECT thing FROM (SELECT count(*) AS thing FROM lake.main.xer_other)") == [
        (250,)
    ]
    [row] = lakes.rows(
        "SELECT _snapshot_id, _table, _row_no, _column, value FROM lake.main.xer_other "
        "WHERE _table = 'Junk7'"
    )
    assert row == ("S1", "Junk7", 1, "a", "x")  # the empty cell of the row is not stored


def test_a_table_p6_defines_that_would_grow_too_wide_goes_to_the_long_table(
    lakes: Lakes, lake: LakeConfig
) -> None:
    wide_names = tuple(f"c{n}" for n in range(MAX_BRONZE_COLUMNS))
    ok = RawTable("TASK", ("task_id",), (("1",),))
    wide = RawTable("TASK", wide_names, (tuple("v" for _ in wide_names),))
    first, first_sha = write_bundle(RawXer(("19.12",), (ok,), "utf-8", 1, 1))
    second, second_sha = write_bundle(RawXer(("19.12",), (wide,), "utf-8", MAX_BRONZE_COLUMNS, 1))
    with open_lake(lake, write=True) as con:
        load_bronze(con, lake, snapshot("S1", first_sha), lambda *_: first, 100)
        load_bronze(con, lake, snapshot("S2", second_sha), lambda *_: second, 100)
    assert [c for c, _ in lakes.tables()["xer_task"]] == ["_snapshot_id", "_row_no", "task_id"]
    assert lakes.rows("SELECT count(*) FROM lake.main.xer_other")[0][0] == MAX_BRONZE_COLUMNS
    assert lakes.rows("SELECT DISTINCT _snapshot_id, _table FROM lake.main.xer_other") == [
        ("S2", "TASK")
    ]


def test_the_allow_list_holds_every_table_the_synthetic_files_and_the_typed_analysis_use() -> None:
    from tl_xer.reader import read_xer
    from tl_xer.synth import week_pair

    used = {t.name for scenario in week_pair() for t in read_xer(make_xer(scenario)).tables}
    assert used <= P6_TABLES, sorted(used - P6_TABLES)
    assert {
        "PROJECT",
        "PROJWBS",
        "CALENDAR",
        "TASK",
        "TASKPRED",
        "ACTVTYPE",
        "ACTVCODE",
    } <= P6_TABLES
    assert "OTHER" not in P6_TABLES  # `xer_other` is the long table, not a P6 table's


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


# --- two projects with a schedule of the same code (round 3, finding F2) --------------------------


def scopes(lakes: Lakes, table: str) -> list[tuple[Any, ...]]:
    return lakes.rows(f"SELECT DISTINCT scope FROM lake.main.{table}")


def second_project(monkeypatch: pytest.MonkeyPatch, lakes: Lakes) -> None:
    """Define MAIN in another project and build its first snapshot only."""
    from tl_mod_schedule import testing as schedule_testing

    monkeypatch.setattr(schedule_testing, "PROJECT", "project:P456")
    monkeypatch.setitem(schedule_testing.BASE, "scope", "project:P456")
    lakes.world.define()
    lakes.world.publish(lakes.world.upload(make_xer(week_pair()[0]), "MAIN"))


def test_the_tables_and_the_mart_keep_the_projects_apart(
    lakes: Lakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_pair(lakes)  # P123: MAIN#1 and MAIN#2
    second_project(monkeypatch, lakes)  # P456: MAIN#1, the same number and the same file
    lakes.sync()
    snapshots = lakes.rows(
        f"SELECT scope, schedule_code, number FROM lake.main.{SNAPSHOT_TABLE} "
        "ORDER BY scope, number"
    )
    assert snapshots == [
        ("project:P123", "MAIN", 1),
        ("project:P123", "MAIN", 2),
        ("project:P456", "MAIN", 1),
    ]
    per_scope = lakes.rows(
        f"SELECT scope, count(*) FROM lake.main.{ACTIVITY_TABLE} GROUP BY scope ORDER BY scope"
    )
    assert per_scope == [("project:P123", 42), ("project:P456", 21)]
    trend = lakes.rows(
        "SELECT scope, snapshot_number, previous_float_days FROM lake.main.mart_float_trend "
        "WHERE activity_id = 'A1230' ORDER BY scope, snapshot_number"
    )
    # P456 has one snapshot: nothing before it, though P123's snapshot 1 has the same number
    assert trend == [
        ("project:P123", 1, None),
        ("project:P123", 2, 9.0),
        ("project:P456", 1, None),
    ]


def test_a_lake_made_before_the_tables_carried_the_project_loads_again(lakes: Lakes) -> None:
    published_pair(lakes)
    lakes.sync()
    with open_lake(lakes.lake, write=True) as con:  # the shape of an earlier lake
        for table in (SNAPSHOT_TABLE, ACTIVITY_TABLE):
            con.execute(f"ALTER TABLE lake.main.{table} DROP COLUMN scope")
    result = lakes.sync()
    assert (result.loaded, result.bronze) == (2, 2)
    assert lakes.rows(f"SELECT DISTINCT scope FROM lake.main.{ACTIVITY_TABLE}") == [
        ("project:P123",)
    ]
    assert lakes.rows(f"SELECT DISTINCT scope FROM lake.main.{SNAPSHOT_TABLE}") == [
        ("project:P123",)
    ]
    assert lakes.rows("SELECT count(*) FROM lake.main.xer_task")[0][0] == 42  # once, not twice
    assert lakes.rows("SELECT DISTINCT scope FROM lake.main.mart_float_trend") == [
        ("project:P123",)
    ]
    assert lakes.sync().up_to_date
