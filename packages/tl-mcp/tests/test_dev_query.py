"""``query_db``: read-only SQL on SQLite and Postgres, with limits, and what it must refuse."""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ToolError
from tl_adapters.postgres import admin
from tl_mcp.dev import query
from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.guard import DevTarget, find_repo_root, resolve_target
from tl_mcp.dev.query import QueryFailed, run_postgres, run_query

REPO = find_repo_root()


@pytest.fixture
def ledger(tmp_path: Path) -> DevHarness:
    env = DevHarness.build(tmp_path)
    for index in range(5):
        env.create_record(f"K-{index}", f"Record {index}")
    return env


def rows(env: DevHarness, sql: str, **kw: object) -> list[list[object]]:
    return env.structured("query_db", sql=sql, **kw)["rows"]  # type: ignore[no-any-return]


def test_a_select_returns_columns_and_rows(ledger: DevHarness) -> None:
    out = ledger.structured(
        "query_db", sql="SELECT key, title FROM cur_core_record ORDER BY key LIMIT 3"
    )
    assert out["dialect"] == "sqlite"
    assert out["columns"] == ["key", "title"]
    assert out["rows"] == [["K-0", "Record 0"], ["K-1", "Record 1"], ["K-2", "Record 2"]]
    assert out["row_count"] == 3 and out["truncated"] is False


def test_the_ledger_and_the_schema_can_be_read(ledger: DevHarness) -> None:
    assert rows(ledger, "SELECT count(*) FROM events") == [[5]]
    names = {r[0] for r in rows(ledger, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"events", "cur_core_record"} <= names


def test_rows_are_limited_and_the_answer_says_so(ledger: DevHarness) -> None:
    out = ledger.structured("query_db", sql="SELECT key FROM cur_core_record", limit=2)
    assert out["row_count"] == 2 and out["truncated"] is True
    assert out["truncated_by"] == "limit"


def test_the_answer_is_capped_in_bytes(ledger: DevHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query, "MAX_RESULT_BYTES", 200)
    out = ledger.structured(
        "query_db",
        sql="WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 500) "
        "SELECT i, printf('%0100d', i) FROM n",
        limit=500,
    )
    assert out["truncated_by"] == "bytes" and 0 < out["row_count"] < 500


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO events (event_id) VALUES ('x')",
        "DELETE FROM events",
        "UPDATE cur_core_record SET title = 'x'",
        "DROP TABLE events",
        "PRAGMA query_only = OFF",
        "ATTACH DATABASE ':memory:' AS m",
        "SELECT 1; DROP TABLE events",
        "WITH t AS (SELECT 1) DELETE FROM events",
        "WITH t AS (SELECT 1) INSERT INTO events (event_id) SELECT 'x'",
        "SELECT * FROM pragma_table_info('events')",
        "SELECT load_extension('/tmp/x.so')",
    ],
)
def test_a_statement_that_is_not_a_plain_select_is_refused_and_changes_nothing(
    ledger: DevHarness, sql: str
) -> None:
    before = rows(ledger, "SELECT count(*) FROM events")
    with pytest.raises(ToolError, match="refused"):
        ledger.call("query_db", sql=sql)
    assert rows(ledger, "SELECT count(*) FROM events") == before
    assert rows(ledger, "SELECT count(*) FROM cur_core_record") == [[5]]


def test_the_authoriser_stops_a_write_the_text_check_cannot_see(ledger: DevHarness) -> None:
    """Straight to the executor, past the guard: the connection itself must refuse."""
    assert ledger.ctx.target.path is not None
    path = str(ledger.ctx.target.path)
    for sql in (
        "INSERT INTO events (event_id) VALUES ('x')",
        "DELETE FROM cur_core_record",
        "CREATE TABLE t (a)",
        "PRAGMA writable_schema = 1",
    ):
        with pytest.raises((DevGuardError, QueryFailed)):
            query.run_sqlite(path, sql, 10)
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT count(*) FROM cur_core_record").fetchone() == (5,)
        assert "t" not in {r[0] for r in con.execute("SELECT name FROM sqlite_master")}


def test_webhook_secrets_cannot_be_read(ledger: DevHarness) -> None:
    with sqlite3.connect(ledger.db) as con:
        con.execute(
            "INSERT INTO wh_secret (secret_id, subscription_id, secret, state, created_at) "
            "VALUES ('s1', 'sub1', 'topsecret', 'active', '2026-10-10T00:00:00Z')"
        )
    for sql in (
        "SELECT secret FROM wh_secret",
        "SELECT * FROM wh_secret",
        "SELECT secret_id FROM wh_secret",
        'SELECT "secret" FROM "WH_SECRET"',
    ):
        with pytest.raises(ToolError, match="refused"):
            ledger.call("query_db", sql=sql)
    assert ledger.ctx.target.path is not None
    for sql in (  # past the text check: the authoriser alone
        "SELECT secret FROM wh_secret",
        "SELECT * FROM wh_secret",
        "SELECT count(*) FROM wh_secret",
        "SELECT (SELECT secret FROM wh_secret)",
    ):
        with pytest.raises(DevGuardError, match="authoriser"):
            query.run_sqlite(str(ledger.ctx.target.path), sql, 10)


def test_a_statement_that_runs_too_long_is_stopped(
    ledger: DevHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(query, "TIMEOUT_S", 0.3)
    with pytest.raises(ToolError, match="ran longer"):
        ledger.call(
            "query_db",
            sql="WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
            "SELECT count(*) FROM n",
        )


def test_a_huge_blob_is_refused_by_the_length_limit(ledger: DevHarness) -> None:
    with pytest.raises(ToolError):
        ledger.call("query_db", sql="SELECT length(zeroblob(2000000000))")


def test_an_error_names_no_server_path(ledger: DevHarness) -> None:
    with pytest.raises(ToolError) as caught:
        ledger.call("query_db", sql="SELECT * FROM no_such_table_in_/home/user/secret/path")
    assert "/home/user" not in str(caught.value)
    with pytest.raises(ToolError) as caught2:
        ledger.call("query_db", sql="SELECT * FROM no_such_table")
    assert "no_such_table" in str(caught2.value)


def test_a_missing_database_is_reported_not_created(tmp_path: Path) -> None:
    env = DevHarness.build(tmp_path, create=False)
    with pytest.raises(ToolError, match="does not exist"):
        env.call("query_db", sql="SELECT 1")
    assert not (tmp_path / "tl.db").exists()


def test_a_database_path_with_special_characters_still_opens(tmp_path: Path) -> None:
    root = tmp_path / "a b#c%d"
    root.mkdir()
    env = DevHarness.build(root)
    assert rows(env, "SELECT 1") == [[1]]


def test_the_limit_is_bounded(ledger: DevHarness) -> None:
    for bad in (0, 1001):
        with pytest.raises(ToolError):
            ledger.call("query_db", sql="SELECT 1", limit=bad)
    with pytest.raises(DevGuardError):
        run_query(ledger.ctx.target, "SELECT 1", limit=0)


def test_every_call_is_audited_with_its_outcome(ledger: DevHarness) -> None:
    rows(ledger, "SELECT 1")
    with pytest.raises(ToolError):
        ledger.call("query_db", sql="DROP TABLE events")
    lines = ledger.audit_lines()
    assert [(line["tool"], line["outcome"]) for line in lines] == [
        ("query_db", "ok"),
        ("query_db", "refused"),
    ]
    assert lines[1]["detail"]["sql"] == "DROP TABLE events"


# --- Postgres ----------------------------------------------------------------------------------


@pytest.fixture
def pg_target() -> Iterator[DevTarget]:
    """A throw-away schema in the ``tl_test`` database of ``TL_PG_URL`` (the guard's own rule)."""
    server = os.environ.get("TL_PG_URL", admin.DEFAULT_URL)
    if not admin.reachable(server):
        if os.environ.get("TL_REQUIRE_POSTGRES") == "1":
            pytest.fail("Postgres is not reachable at TL_PG_URL")
        pytest.skip("Postgres is not reachable at TL_PG_URL")
    schema = "tl_t_" + uuid.uuid4().hex[:16]
    admin.create_schema_namespace(server, schema)
    try:
        url = admin.schema_url(server, schema)
        try:
            target = resolve_target(url, repo_root=REPO)
        except DevGuardError:
            pytest.skip("TL_PG_URL names a database that is not tl_test* or tl_dev*")
        from tl_adapters.db import create_schema

        create_schema(url)
        yield target
    finally:
        admin.drop_schema_namespace(server, schema)


@pytest.mark.requires_postgres
def test_postgres_select_reads_the_ledger_tables(pg_target: DevTarget) -> None:
    result = run_query(pg_target, "SELECT count(*) AS n FROM events")
    assert result.dialect == "postgres" and result.columns == ["n"] and result.rows == [[0]]


@pytest.mark.requires_postgres
def test_postgres_percent_signs_are_not_parameters(pg_target: DevTarget) -> None:
    result = run_query(pg_target, "SELECT 'a%b' LIKE 'a%' AS m, '%s' AS lit")
    assert result.rows == [[True, "%s"]]


@pytest.mark.requires_postgres
def test_postgres_refuses_writes_and_system_reads(pg_target: DevTarget) -> None:
    for sql in (
        "DELETE FROM events",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM pg_shadow",
        "SELECT set_config('transaction_read_only', 'off', true)",
    ):
        with pytest.raises(DevGuardError):
            run_query(pg_target, sql)


@pytest.mark.requires_postgres
def test_the_postgres_transaction_is_read_only_even_without_the_guard(pg_target: DevTarget) -> None:
    assert pg_target.url is not None
    with pytest.raises(QueryFailed, match="read-only"):
        run_postgres(pg_target.url, "CREATE TABLE should_not_exist (a int)", 10)
    assert run_query(pg_target, "SELECT to_regclass('should_not_exist') IS NULL").rows == [[True]]


@pytest.mark.requires_postgres
def test_a_postgres_statement_that_runs_too_long_is_stopped(
    pg_target: DevTarget, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(query, "TIMEOUT_S", 0.5)
    with pytest.raises(QueryFailed, match="timeout"):
        run_query(pg_target, "SELECT count(*) FROM generate_series(1, 1000000000)")


@pytest.mark.requires_postgres
def test_postgres_rows_are_limited(pg_target: DevTarget) -> None:
    result = run_query(pg_target, "SELECT g FROM generate_series(1, 50) AS t(g)", limit=10)
    assert len(result.rows) == 10 and result.truncated_by == "limit"


def test_the_authoriser_denies_raw_page_tables_and_pragma_functions() -> None:
    import sqlite3

    for table in ("sqlite_dbpage", "dbstat", "pragma_table_info", "wh_secret"):
        assert query._authorizer(sqlite3.SQLITE_READ, table, "x", None, None) == sqlite3.SQLITE_DENY
    assert query._authorizer(sqlite3.SQLITE_READ, "events", "seq", None, None) == sqlite3.SQLITE_OK
    assert query._authorizer(sqlite3.SQLITE_INSERT, "events", None, None, None) == (
        sqlite3.SQLITE_DENY
    )


def test_a_failure_is_not_reported_as_a_refusal(
    ledger: DevHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(query, "TIMEOUT_S", 0.2)
    with pytest.raises(ToolError) as caught:
        ledger.call(
            "query_db",
            sql="WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
            "SELECT count(*) FROM n",
        )
    assert "refused" not in str(caught.value)
    assert ledger.audit_lines()[-1]["outcome"] == "error"


def test_file_functions_do_not_exist_in_the_python_sqlite(ledger: DevHarness) -> None:
    with pytest.raises(ToolError, match="no such function"):
        ledger.call("query_db", sql="SELECT readfile('/etc/passwd')")
