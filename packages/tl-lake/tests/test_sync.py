"""Incremental sync into DuckLake: bronze, silver, the watermark and the snapshot boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from builder import LedgerBuilder
from sqlalchemy import MetaData, Table, text
from tl_lake import (
    LakeAheadError,
    LakeConfig,
    LakeDivergedError,
    LakeSyncError,
    lake_status,
    read_snapshot,
    sync_lake,
)
from tl_lake import sync as sync_module
from tl_lake.duck import open_lake, table_ref


def sync(ledger: LedgerBuilder, lake: LakeConfig, **kwargs: Any) -> Any:
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            return sync_lake(lake, conn, **kwargs)
    finally:
        engine.dispose()


def lake_rows(lake: LakeConfig, sql: str) -> list[tuple[Any, ...]]:
    with open_lake(lake, write=False) as con:
        return con.execute(sql).fetchall()


def populate(ledger: LedgerBuilder) -> tuple[str, str]:
    a = ledger.record("A-1")
    b = ledger.record("B-1")
    ledger.values(a, "valve_data", {"size_in": 4, "manufacturer": "Acme"})
    ledger.link(a, b)
    return a, b


def test_first_sync_loads_bronze_and_silver_in_one_snapshot(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    populate(ledger)
    result = sync(ledger, lake)
    head = ledger.head()
    assert (result.first_seq, result.last_seq, result.events) == (1, head, head)
    assert result.snapshot_id is not None
    assert lake_rows(lake, "SELECT count(*), min(seq), max(seq) FROM events") == [(head, 1, head)]
    assert lake_rows(lake, "SELECT key FROM cur_core_record ORDER BY key") == [("A-1",), ("B-1",)]
    assert lake_rows(lake, "SELECT count(*) FROM links") == [(1,)]
    assert lake_rows(lake, "SELECT path FROM pset_values ORDER BY path") == [
        ("psets.valve_data.manufacturer",),
        ("psets.valve_data.size_in",),
    ]
    # exactly one sync row, and it names the snapshot that holds the data
    assert lake_rows(lake, "SELECT snapshot_id, first_seq, last_seq FROM _tl_sync") == [
        (result.snapshot_id, 1, head)
    ]
    with open_lake(lake, write=False) as con:
        current = con.execute("SELECT id FROM lake.current_snapshot()").fetchone()
    assert current == (result.snapshot_id,)


def test_silver_has_typed_columns_including_promoted_pset_columns(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    a, _ = populate(ledger)
    sync(ledger, lake)
    with open_lake(lake, write=False) as con:
        types = dict(
            con.execute(
                "SELECT column_name, data_type FROM duckdb_columns() "
                "WHERE database_name = 'lake' AND table_name = 'cur_core_record'"
            ).fetchall()
        )
    assert types["voided"] == "BOOLEAN"
    assert types["created_at"] == "TIMESTAMP"
    assert types["version"] == "BIGINT"
    assert "pset__valve_data__size_in" in types and "pset__valve_data__body_material" in types
    rows = lake_rows(
        lake, f"SELECT pset__valve_data__size_in FROM cur_core_record WHERE id = '{a}'"
    )
    assert rows == [(4.0,)]


def test_an_unchanged_ledger_makes_no_snapshot(ledger: LedgerBuilder, lake: LakeConfig) -> None:
    populate(ledger)
    first = sync(ledger, lake)
    again = sync(ledger, lake)
    assert again.up_to_date and again.snapshot_id is None and again.last_seq == first.last_seq
    assert lake_rows(lake, "SELECT count(*) FROM _tl_sync") == [(1,)]


def test_incremental_sync_replaces_only_changed_streams(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    a, b = populate(ledger)
    first = sync(ledger, lake)
    ledger.update(a, title="Renamed")
    ledger.values(b, "valve_data", {"manufacturer": "Beta"})
    second = sync(ledger, lake)
    assert second.first_seq == first.last_seq + 1
    assert second.events == ledger.head() - first.last_seq
    assert second.silver_rows["cur_core_record"] == 2  # a and b changed
    assert second.silver_rows["links"] == 0
    assert lake_rows(lake, "SELECT title FROM cur_core_record ORDER BY key") == [
        ("Renamed",),
        ("Record B-1",),
    ]
    assert lake_rows(lake, "SELECT count(*) FROM cur_core_record") == [(2,)]
    assert lake_rows(lake, "SELECT count(*) FROM pset_values") == [(3,)]
    assert lake_rows(lake, "SELECT first_seq, last_seq FROM _tl_sync ORDER BY last_seq") == [
        (1, first.last_seq),
        (second.first_seq, ledger.head()),
    ]


def test_a_record_that_loses_all_its_values_loses_its_silver_rows(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    a, _ = populate(ledger)
    sync(ledger, lake)
    ledger.values(a, "valve_data", {"size_in": None, "manufacturer": None})
    sync(ledger, lake)
    assert lake_rows(lake, "SELECT count(*) FROM pset_values") == [(0,)]


def test_a_new_promoted_column_reloads_silver_in_full(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    a = ledger.record("A-1")
    b = ledger.record("B-1")
    ledger.values(a, "valve_data", {"size_in": 4, "manufacturer": "Acme"})
    ledger.values(b, "valve_data", {"size_in": 6, "manufacturer": "Acme"})
    sync(ledger, lake)
    # Dropping the lake's knowledge of a column: simulate a lake built before the column existed.
    with open_lake(lake, write=True) as con:
        con.execute(
            f"ALTER TABLE {table_ref('cur_core_record')} DROP COLUMN pset__valve_data__size_in"
        )
    ledger.update(a, title="Touched")  # only a changes, but the column must be restored for b too
    sync(ledger, lake)
    assert lake_rows(
        lake, "SELECT key, pset__valve_data__size_in FROM cur_core_record ORDER BY key"
    ) == [("A-1", 4.0), ("B-1", 6.0)]


def test_status_reports_the_watermark(ledger: LedgerBuilder, lake: LakeConfig) -> None:
    assert lake_status(lake).initialised is False
    populate(ledger)
    result = sync(ledger, lake, now=lambda: datetime(2026, 10, 9, 12, 0, tzinfo=UTC))
    status = lake_status(lake)
    assert status.initialised and status.as_of_seq == ledger.head()
    assert status.snapshot_id == result.snapshot_id and status.syncs == 1
    assert status.synced_at == datetime(2026, 10, 9, 12, 0)
    assert status.tables["events"] == ledger.head() and status.tables["links"] == 1


def test_a_failure_before_commit_leaves_the_lake_untouched(
    ledger: LedgerBuilder, lake: LakeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    populate(ledger)
    first = sync(ledger, lake)
    ledger.record("C-1")
    before = lake_rows(lake, "SELECT count(*) FROM events")

    real = sync_module.insert_rows  # type: ignore[attr-defined]
    calls = {"n": 0}

    def explode(*args: Any, **kwargs: Any) -> int:
        calls["n"] += 1
        if calls["n"] == 2:  # bronze went in; the first silver table blows up
            raise RuntimeError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(sync_module, "insert_rows", explode)
    with pytest.raises(RuntimeError, match="boom"):
        sync(ledger, lake)
    monkeypatch.setattr(sync_module, "insert_rows", real)

    assert lake_rows(lake, "SELECT count(*) FROM events") == before
    assert lake_rows(lake, "SELECT max(last_seq) FROM _tl_sync") == [(first.last_seq,)]
    assert lake_rows(lake, "SELECT count(*) FROM cur_core_record") == [(2,)]
    recovered = sync(ledger, lake)  # and the next sync picks up where the lake really is
    assert recovered.first_seq == first.last_seq + 1
    assert lake_rows(lake, "SELECT count(*) FROM cur_core_record") == [(3,)]


def test_the_lake_ahead_of_the_ledger_is_refused(
    ledger: LedgerBuilder, lake: LakeConfig, tmp_path: Any
) -> None:
    populate(ledger)
    sync(ledger, lake)
    other = LedgerBuilder.create(tmp_path / "other.db")
    other.record("X-1")
    with pytest.raises(LakeAheadError):
        sync(other, lake)


def test_a_different_ledger_with_the_same_seq_is_refused(
    ledger: LedgerBuilder, lake: LakeConfig, tmp_path: Any
) -> None:
    ledger.record("A-1")
    sync(ledger, lake)
    other = LedgerBuilder.create(tmp_path / "other.db")
    other.record("Z-1")
    other.record("Z-2")
    with pytest.raises(LakeDivergedError):
        sync(other, lake)


class RacingLedger:
    """Reads like a connection with no snapshot: a commit lands right after the head is read."""

    def __init__(self, engine: Any, after_first_read: Any) -> None:
        self.engine = engine
        self.after_first_read = after_first_read
        self.reads = 0

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        with self.engine.connect() as conn:
            frozen = conn.execute(statement, *args, **kwargs).freeze()
        self.reads += 1
        if self.reads == 1:
            self.after_first_read()
        return frozen()


def test_a_connection_that_is_not_a_snapshot_is_refused(
    ledger: LedgerBuilder, lake: LakeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = ledger.record("A-1")
    engine = ledger.engine()
    monkeypatch.setattr(
        sync_module,
        "_reflect",
        lambda _conn, name: Table(name, MetaData(), autoload_with=engine),
    )
    try:
        racing = RacingLedger(engine, lambda: ledger.update(a, title="raced"))
        with pytest.raises(LakeSyncError, match="consistent snapshot"):
            sync_lake(lake, racing)  # type: ignore[arg-type]
    finally:
        engine.dispose()
    assert lake_status(lake).syncs == 0


def test_a_snapshot_connection_sees_one_instant(ledger: LedgerBuilder, lake: LakeConfig) -> None:
    a = ledger.record("A-1")
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            head = conn.execute(text("SELECT max(seq) FROM events")).scalar_one()
            ledger.update(a, title="after the snapshot began")
            result = sync_lake(lake, conn)
    finally:
        engine.dispose()
    assert result.last_seq == head
    assert lake_rows(lake, "SELECT title FROM cur_core_record") == [("Record A-1",)]


def test_rebuild_wipes_and_reloads(ledger: LedgerBuilder, lake: LakeConfig) -> None:
    populate(ledger)
    sync(ledger, lake)
    ledger.record("C-1")
    sync(ledger, lake)
    assert lake_status(lake).syncs == 2
    result = sync(ledger, lake, rebuild=True)
    assert result.first_seq == 1 and result.last_seq == ledger.head()
    assert lake_status(lake).syncs == 1
    assert lake_rows(lake, "SELECT count(*) FROM cur_core_record") == [(3,)]
