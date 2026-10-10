"""The six demo queries in dev/lake/queries/ run through lake_query and return the expected rows."""

from __future__ import annotations

from pathlib import Path

import pytest
from builder import LedgerBuilder
from tl_lake import LakeConfig, LakeQueryResult, LakeQueryService, read_snapshot, sync_lake

QUERIES = Path(__file__).resolve().parents[3] / "dev" / "lake" / "queries"


@pytest.fixture
def synced(ledger: LedgerBuilder, lake: LakeConfig) -> LedgerBuilder:
    a = ledger.record("A-1")
    b = ledger.record("B-1")
    ledger.record("C-1")
    ledger.values(a, "valve_data", {"size_in": 4, "manufacturer": "Acme"})
    ledger.values(b, "valve_data", {"manufacturer": "Beta"})
    ledger.link(a, b)
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lake, conn)
    finally:
        engine.dispose()
    return ledger


def run(lake: LakeConfig, name: str) -> LakeQueryResult:
    sql = (QUERIES / f"{name}.sql").read_text()
    result = LakeQueryService(lake).query(sql)
    assert not result.truncated, name
    return result


def test_events_by_type(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = run(lake, "events_by_type")
    assert result.columns == ["event_type", "n"]
    assert ["Record.Created", 3] in result.rows
    counts = [row[1] for row in result.rows]
    assert counts == sorted(counts, reverse=True)


def test_records_overview(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = run(lake, "records_overview")
    assert [row[0] for row in result.rows] == ["A-1", "B-1", "C-1"]
    assert all(row[2] is False for row in result.rows)


def test_links_by_relation(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = run(lake, "links_by_relation")
    assert len(result.rows) == 1
    assert result.rows[0][2] == 1


def test_valve_sizes(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = run(lake, "valve_sizes")
    assert result.columns == ["key", "size_in"]
    assert result.rows == [["A-1", 4.0]]


def test_pset_coverage(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = run(lake, "pset_coverage")
    assert result.columns == ["pset", "records", "values"]
    assert result.rows == [["valve_data", 2, 3]]


def test_as_of(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = run(lake, "as_of")
    assert result.rows == [[synced.head()]]
    assert result.as_of_seq == synced.head()
