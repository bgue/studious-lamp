"""The lake_query guard: SELECT over lake tables only."""

from __future__ import annotations

import duckdb
import pytest
from tl_lake.guard import GuardError, check_sql

TABLES = {"events", "cur_core_record", "links", "pset_values", "_tl_sync"}


@pytest.fixture(scope="module")
def con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:")


def refused(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    with pytest.raises(GuardError) as caught:
        check_sql(con, sql, TABLES)
    return str(caught.value)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM events",
        "select count(*) from lake.main.events",
        "SELECT * FROM main.cur_core_record WHERE key = 'A-1';",
        "WITH x AS (SELECT * FROM links) SELECT * FROM x",
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 5) "
        "SELECT * FROM r",
        "FROM events SELECT seq",
        "VALUES (1), (2)",
        "SELECT 1 UNION ALL SELECT 2",
        "SELECT * FROM events AT (VERSION => 1)",
        "SELECT e.seq, l.link_id FROM events e JOIN links l ON l.link_id = e.stream_id",
        "SELECT * FROM range(5)",
        "SELECT * FROM events, unnest([1, 2]) AS u(x)",
        "SELECT (SELECT max(seq) FROM events)",
        "SELECT * FROM (SELECT * FROM pset_values) q",
        "SELECT seq FROM events -- trailing comment",
        "SELECT sum(seq) OVER (ORDER BY seq) FROM events",
        "SELECT * FROM (SELECT * FROM pset_values) PIVOT (count(*) FOR layer IN ('standard'))",
    ],
)
def test_accepts_selects_over_lake_tables(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    check_sql(con, sql, TABLES)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP TABLE events",
        "SELECT * FROM events; INSERT INTO events VALUES (1)",
        "",
        "   ",
        "-- only a comment",
        "SELECT",
        "SELEC * FROM events",
    ],
)
def test_refuses_stacked_empty_and_unparseable(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    refused(con, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE t (a INT)",
        "CREATE TABLE t AS SELECT * FROM events",
        "CREATE VIEW v AS SELECT 1",
        "DROP TABLE events",
        "ALTER TABLE events ADD COLUMN x INT",
        "INSERT INTO events SELECT * FROM events",
        "UPDATE events SET seq = 1",
        "DELETE FROM events",
        "TRUNCATE events",
        "MERGE INTO events USING links ON true WHEN MATCHED THEN DELETE",
        "ATTACH ':memory:' AS other",
        "DETACH lake",
        "INSTALL httpfs",
        "LOAD httpfs",
        "COPY events TO '/tmp/out.csv'",
        "COPY events FROM '/tmp/in.csv'",
        "EXPORT DATABASE '/tmp/dump'",
        "PRAGMA database_list",
        "SET enable_external_access = true",
        "RESET threads",
        "CALL ducklake_flush_inlined_data('lake')",
        "EXPLAIN SELECT * FROM events",
        "DESCRIBE events",
        "SHOW TABLES",
        "SUMMARIZE events",
        "USE memory",
        "VACUUM",
        "CHECKPOINT",
        "BEGIN",
        "COMMIT",
    ],
)
def test_refuses_everything_that_is_not_a_select(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    refused(con, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "SELECT * FROM read_parquet('/tmp/x.parquet')",
        "SELECT * FROM read_text('/etc/hostname')",
        "SELECT * FROM read_blob('/etc/hostname')",
        "SELECT * FROM read_json('/tmp/x.json')",
        "SELECT * FROM parquet_scan('/tmp/x.parquet')",
        "SELECT * FROM parquet_metadata('/tmp/x.parquet')",
        "SELECT * FROM glob('/etc/*')",
        "SELECT * FROM sniff_csv('/etc/passwd')",
        "SELECT * FROM '/etc/passwd.csv'",
        "SELECT * FROM 'data.parquet'",
        "SELECT * FROM query_table('events')",
        "SELECT * FROM query('SELECT 1')",
        "SELECT * FROM duckdb_settings()",
        "SELECT * FROM duckdb_tables",
        "SELECT * FROM pragma_database_list()",
        "SELECT * FROM sqlite_scan('x.db', 't')",
        "SELECT * FROM memory.main.range(3)",
        "SELECT * FROM system.main.duckdb_tables()",
        "SELECT * FROM events e, read_csv('/etc/passwd') c",
        "SELECT * FROM (SELECT * FROM read_text('/etc/hostname')) q",
        "SELECT (SELECT count(*) FROM read_csv('/etc/passwd'))",
        "WITH x AS (SELECT * FROM read_csv('/etc/passwd')) SELECT * FROM x",
        "SELECT * FROM events WHERE seq IN (SELECT 1 FROM read_csv('/etc/passwd'))",
        "SELECT * FROM events UNION ALL SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_csv('/etc/passwd') UNION ALL SELECT * FROM events",
    ],
)
def test_refuses_file_reading_and_system_tables(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    refused(con, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT getenv('HOME')",
        "SELECT current_setting('threads')",
        "SELECT * FROM events WHERE getenv('X') = 'y'",
        "SELECT read_text('/etc/passwd')",
    ],
)
def test_refuses_functions_that_reach_outside_the_lake(
    con: duckdb.DuckDBPyConnection, sql: str
) -> None:
    refused(con, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM memory.main.events",
        "SELECT * FROM other.main.events",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM main.duckdb_tables",
        "SELECT * FROM not_a_table",
    ],
)
def test_refuses_other_catalogs_schemas_and_unknown_tables(
    con: duckdb.DuckDBPyConnection, sql: str
) -> None:
    refused(con, sql)


def test_a_cte_only_covers_the_query_that_defines_it(con: duckdb.DuckDBPyConnection) -> None:
    # The scalar subquery defines a CTE named like a system view; the outer FROM must not use it.
    refused(
        con,
        "SELECT (WITH duckdb_settings AS (SELECT 1) SELECT * FROM duckdb_settings), * "
        "FROM duckdb_settings",
    )
    # A CTE that shadows a name is fine where it is visible.
    check_sql(con, "WITH duckdb_settings AS (SELECT 1 AS x) SELECT * FROM duckdb_settings", TABLES)


def test_refusal_messages_name_the_reason(con: duckdb.DuckDBPyConnection) -> None:
    assert "single SELECT" in refused(con, "DROP TABLE events")
    assert "exactly one statement" in refused(con, "SELECT 1; SELECT 2")
    assert "read_csv" in refused(con, "SELECT * FROM read_csv('/etc/passwd')")
    assert "not a lake table" in refused(con, "SELECT * FROM '/etc/passwd.csv'")
    assert "longer than" in refused(con, "SELECT " + "1," * 20_000 + "1")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; -- harmless\nDROP TABLE events",
        "SELECT 1 /* ; */; DROP TABLE events",
        "-- note\nSELECT 1; DROP TABLE events",
        "SELECT 1 -- one\n; SELECT 2",
        "/* a */ SELECT 1; /* b */ INSERT INTO events SELECT * FROM events",
        "-- SELECT 1\nDROP TABLE events",
        "/* SELECT 1 */ DROP TABLE events",
    ],
)
def test_comments_cannot_hide_a_second_statement(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    refused(con, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "-- what this answers\nSELECT * FROM events",
        "/* what this answers */ SELECT * FROM events",
        "SELECT * FROM events -- trailing; DROP TABLE events",
        "SELECT '-- not a comment; DROP TABLE events' AS s",
        "SELECT 1; -- only a comment follows",
    ],
)
def test_comments_around_one_select_are_fine(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    check_sql(con, sql, TABLES)
