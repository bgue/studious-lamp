"""lake_query end to end: results, limits, as-of seq, refusals, sandbox and the audit log."""

from __future__ import annotations

import json
from typing import Any

import pytest
from builder import LedgerBuilder
from tl_lake import (
    GuardError,
    LakeConfig,
    LakeNotInitialisedError,
    LakeQueryService,
    QueryError,
    lake_query,
    read_snapshot,
    sync_lake,
)
from tl_lake.duck import open_lake
from tl_lake.errors import LakeLockTimeout
from tl_lake.query import _sandbox


@pytest.fixture
def synced(ledger: LedgerBuilder, lake: LakeConfig) -> LedgerBuilder:
    a = ledger.record("A-1")
    b = ledger.record("B-1")
    ledger.values(a, "valve_data", {"size_in": 4, "manufacturer": "Acme"})
    ledger.link(a, b)
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lake, conn)
    finally:
        engine.dispose()
    return ledger


def audit(lake: LakeConfig) -> list[dict[str, Any]]:
    return [json.loads(line) for line in lake.audit_log_path.read_text().splitlines()]


def test_returns_rows_and_the_as_of_seq(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = LakeQueryService(lake).query("SELECT key, title FROM cur_core_record ORDER BY key")
    assert result.columns == ["key", "title"]
    assert result.rows == [["A-1", "Record A-1"], ["B-1", "Record B-1"]]
    assert result.as_of_seq == synced.head() and not result.truncated
    assert result.as_of_line() == f"as of seq {synced.head()} (snapshot {result.snapshot_id})"


def test_the_module_function_takes_a_lake_dir(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = lake_query("SELECT count(*) FROM events", lake_dir=str(lake.lake_dir), limit=5)
    assert result.rows == [[synced.head()]] and result.limit == 5


def test_applies_the_row_limit_and_says_when_it_cut(
    synced: LedgerBuilder, lake: LakeConfig
) -> None:
    service = LakeQueryService(lake)
    cut = service.query("SELECT seq FROM events ORDER BY seq", limit=2)
    assert cut.rows == [[1], [2]] and cut.truncated and cut.limit == 2
    whole = service.query("SELECT seq FROM events ORDER BY seq", limit=1000)
    assert whole.row_count == synced.head() and not whole.truncated
    exact = service.query("SELECT seq FROM events ORDER BY seq", limit=synced.head())
    assert exact.row_count == synced.head() and not exact.truncated


def test_a_generator_cannot_run_past_the_limit(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = LakeQueryService(lake).query("SELECT * FROM range(100000000000)", limit=3)
    assert result.rows == [[0], [1], [2]] and result.truncated


@pytest.mark.parametrize("limit", [0, -1, 10_001, True, 2.5])
def test_refuses_a_bad_limit(synced: LedgerBuilder, lake: LakeConfig, limit: Any) -> None:
    with pytest.raises(GuardError, match="limit"):
        LakeQueryService(lake).query("SELECT 1", limit=limit)


def test_zone_aware_values_come_back_as_text(synced: LedgerBuilder, lake: LakeConfig) -> None:
    result = LakeQueryService(lake).query(
        "SELECT TIMESTAMPTZ '2026-01-01 00:00:00+00' AS t, 1 AS n, DATE '2026-02-03' AS d"
    )
    assert result.columns == ["t", "n", "d"]
    assert result.rows[0][1:] == [1, "2026-02-03"] and result.rows[0][0].startswith("2026-01-01")
    json.dumps(result.rows)


def test_time_travel_reads_an_earlier_sync(synced: LedgerBuilder, lake: LakeConfig) -> None:
    first = LakeQueryService(lake).query("SELECT snapshot_id, last_seq FROM _tl_sync")
    [[snapshot, first_head]] = first.rows
    synced.record("C-1")
    engine = synced.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lake, conn)
    finally:
        engine.dispose()
    service = LakeQueryService(lake)
    now = service.query("SELECT count(*) FROM cur_core_record")
    then = service.query(f"SELECT count(*) FROM cur_core_record AT (VERSION => {snapshot})")
    assert now.rows == [[3]] and then.rows == [[2]]
    assert now.as_of_seq == synced.head() and first_head < now.as_of_seq


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE events",
        "SELECT 1; SELECT 2",
        "INSERT INTO events SELECT * FROM events",
        "ATTACH ':memory:' AS x",
        "COPY events TO '/tmp/leak.csv'",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_text('/etc/hostname')",
        "SELECT * FROM '/etc/passwd.csv'",
        "PRAGMA database_list",
        "SET enable_external_access = true",
        "LOAD httpfs",
        "INSTALL httpfs",
    ],
)
def test_refused_statements_change_nothing(
    synced: LedgerBuilder, lake: LakeConfig, sql: str
) -> None:
    service = LakeQueryService(lake)
    before = service.query("SELECT count(*) FROM events").rows
    with pytest.raises(GuardError):
        service.query(sql)
    assert service.query("SELECT count(*) FROM events").rows == before
    assert not (lake.lake_dir / "leak.csv").exists()


def test_every_call_is_logged_accepted_or_not(synced: LedgerBuilder, lake: LakeConfig) -> None:
    service = LakeQueryService(lake)
    service.query("SELECT 1", caller="agent:analyst")
    with pytest.raises(GuardError):
        service.query("DROP TABLE events", caller="agent:analyst")
    with pytest.raises(QueryError):
        service.query("SELECT CAST('x' AS INTEGER)", caller="agent:analyst")
    ok, refused, failed = audit(lake)
    assert (ok["outcome"], ok["caller"], ok["sql"], ok["rows"]) == (
        "ok",
        "agent:analyst",
        "SELECT 1",
        1,
    )
    assert ok["as_of_seq"] == synced.head() and "ts" in ok and ok["limit"] == 100
    assert refused["outcome"] == "refused" and "single SELECT" in refused["detail"]
    assert refused["sql"] == "DROP TABLE events"
    assert failed["outcome"] == "error"


def test_a_missing_lake_is_an_error_and_is_logged(lake: LakeConfig) -> None:
    with pytest.raises(LakeNotInitialisedError):
        LakeQueryService(lake).query("SELECT 1")
    assert audit(lake)[0]["outcome"] == "error"


def test_a_slow_query_is_interrupted(synced: LedgerBuilder, lake: LakeConfig) -> None:
    service = LakeQueryService(lake, timeout_s=0.5)
    with pytest.raises(QueryError, match="longer than"):
        service.query(
            "SELECT count(*) FROM range(3000000000) a, range(3000000000) b WHERE a.range = b.range",
            limit=1,
        )
    assert audit(lake)[-1]["outcome"] == "error"


def test_the_sandbox_blocks_what_the_guard_would_miss(
    synced: LedgerBuilder, lake: LakeConfig
) -> None:
    """Layers 2 and 3 on their own: even unguarded SQL cannot read a file or change settings."""
    with open_lake(lake, write=False) as con:
        _sandbox(con, lake)
        assert con.execute("SELECT count(*) FROM events").fetchone() == (synced.head(),)
        for sql in (
            "SELECT * FROM read_csv('/etc/passwd')",
            "SELECT * FROM read_text('/etc/hostname')",
            f"SELECT * FROM read_text('{lake.catalog_path}')",
            "SET enable_external_access = true",
            "SET lock_configuration = false",
            "INSTALL httpfs",
            "COPY events TO '/tmp/should-not-exist.csv'",
            "INSERT INTO events SELECT * FROM events",
            "DROP TABLE events",
        ):
            with pytest.raises(Exception):  # noqa: B017, PT011 - any refusal will do here
                con.execute(sql)


def test_a_refusal_prints_nothing_unless_the_application_configures_logging(
    synced: LedgerBuilder, lake: LakeConfig, capfd: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(GuardError):
        LakeQueryService(lake).query("DROP TABLE events")
    captured = capfd.readouterr()
    assert captured.err == "" and captured.out == ""
    assert audit(lake)[-1]["outcome"] == "refused"


AUDIT_KEYS = {
    "ts",
    "caller",
    "sql",
    "limit",
    "outcome",
    "detail",
    "error_class",
    "rows",
    "truncated",
    "as_of_seq",
    "snapshot_id",
    "elapsed_ms",
}


def test_every_failure_mode_writes_one_audit_line_with_the_same_keys(
    synced: LedgerBuilder, lake: LakeConfig
) -> None:
    service = LakeQueryService(lake)
    service.query("SELECT 1")
    with pytest.raises(GuardError):
        service.query("DROP TABLE events")
    with pytest.raises(GuardError, match="text"):
        service.query(123)  # type: ignore[arg-type]
    with pytest.raises(GuardError, match="NUL"):
        service.query("SELECT 1\x00")
    with pytest.raises(QueryError):
        service.query("SELECT CAST('x' AS INTEGER)")
    with pytest.raises(Exception):  # noqa: B017, PT011 - a lone surrogate fails inside DuckDB
        service.query("SELECT '\ud800'")
    with open_lake(lake, write=True):  # a sync holds the lock, so the query cannot start
        with pytest.raises(LakeLockTimeout):
            LakeQueryService(lake, lock_timeout_s=0.2).query("SELECT 1", caller="agent:x")
    lines = audit(lake)
    assert len(lines) == 7
    assert all(set(line) == AUDIT_KEYS for line in lines)
    outcomes = [(line["outcome"], line["error_class"]) for line in lines]
    assert outcomes[:4] == [("ok", None), ("refused", None), ("refused", None), ("refused", None)]
    assert outcomes[4] == ("error", "ConversionException")
    assert outcomes[6] == ("error", "LakeLockTimeout")
    assert lines[6]["caller"] == "agent:x" and lines[6]["rows"] == 0
    assert lines[1]["rows"] == 0 and lines[1]["as_of_seq"] == synced.head()
    assert lines[2]["sql"].startswith("<int>")


def test_a_unicode_line_separator_cannot_split_an_audit_record(
    synced: LedgerBuilder, lake: LakeConfig
) -> None:
    sql = "SELECT 'a b\x85c' AS s"
    result = LakeQueryService(lake).query(sql)
    assert result.rows == [["a b\x85c"]]
    text = lake.audit_log_path.read_text(encoding="ascii")
    assert len(text.splitlines()) == 1  # str.splitlines() also splits on U+2028 and U+0085
    assert json.loads(text)["sql"] == sql


def test_the_result_byte_cap_truncates_and_says_so(synced: LedgerBuilder, lake: LakeConfig) -> None:
    service = LakeQueryService(lake, max_bytes=500)
    result = service.query("SELECT repeat('x', 100) AS s FROM range(50)", limit=50)
    assert result.truncated and result.truncated_by == "bytes"
    assert 1 <= result.row_count < 50
    assert len(json.dumps(result.rows)) <= 500
    one = service.query("SELECT repeat('x', 1000) AS s")
    assert one.rows == [] and one.truncated_by == "bytes"
    capped_by_rows = service.query("SELECT 1 FROM range(10)", limit=3)
    assert capped_by_rows.truncated_by == "limit" and capped_by_rows.row_count == 3
    whole = service.query("SELECT 1")
    assert whole.truncated_by is None and not whole.truncated


def test_errors_are_short_classed_and_free_of_paths(
    synced: LedgerBuilder, lake: LakeConfig
) -> None:
    service = LakeQueryService(lake)
    with pytest.raises(QueryError) as caught:
        service.query("SELECT CAST('x' AS INTEGER)")
    assert caught.value.error_class == "ConversionException"
    assert str(caught.value).startswith("ConversionException: ") and len(str(caught.value)) < 260
    text = service._scrub(
        f"cannot read {lake.lake_dir}/data/main/events/f.parquet and /etc/passwd x"
    )
    assert text == "cannot read <lake>/data/main/events/f.parquet and <path> x"


def test_a_cte_named_like_a_lake_data_file_cannot_read_it(
    synced: LedgerBuilder, lake: LakeConfig
) -> None:
    [parquet, *_] = sorted(lake.data_path.rglob("*.parquet"))
    name = str(parquet)
    service = LakeQueryService(lake)
    for sql in (
        f'WITH "{name}" AS (SELECT * FROM "{name}") SELECT * FROM "{name}"',
        f"SELECT * FROM '{name}'",
        f"SELECT * FROM '{lake.data_path}/main/*/*.parquet'",
    ):
        with pytest.raises(GuardError) as caught:
            service.query(sql)
        assert str(lake.lake_dir) not in str(caught.value)
    assert all(str(lake.lake_dir) not in line["detail"] for line in audit(lake))
