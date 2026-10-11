"""The ``query_db`` SQL guard: SQLite statements accepted and refused; Postgres always refused."""

from __future__ import annotations

import pytest
from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.sqlguard import POSTGRES_REFUSAL, check_select, check_sqlite_select

SQLITE_OK = [
    "SELECT 1",
    "select * from cur_core_record where scope = 'project:P1' limit 5",
    "  -- a comment\n SELECT count(*) FROM events",
    "/* c */ WITH t AS (SELECT 1 AS a) SELECT a FROM t",
    "SELECT name, sql FROM sqlite_master",
    "SELECT 1;",
]


@pytest.mark.parametrize("sql", SQLITE_OK)
def test_sqlite_accepts_a_select(sql: str) -> None:
    check_sqlite_select(sql)
    check_select(sql, "sqlite")


NOT_A_SELECT = [
    "INSERT INTO events VALUES (1)",
    "UPDATE cur_core_record SET title = 'x'",
    "DELETE FROM events",
    "DROP TABLE events",
    "CREATE TABLE x (a int)",
    "ALTER TABLE events ADD COLUMN a int",
    "PRAGMA writable_schema = ON",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "VACUUM",
    "REINDEX",
    "BEGIN",
    "COMMIT",
    "EXPLAIN SELECT 1",
    "REPLACE INTO events VALUES (1)",
    "",
    "   ",
    "-- only a comment",
]


@pytest.mark.parametrize("sql", NOT_A_SELECT)
def test_sqlite_refuses_text_that_is_not_a_select(sql: str) -> None:
    with pytest.raises(DevGuardError):
        check_sqlite_select(sql)


def test_a_statement_with_a_nul_character_is_refused() -> None:
    with pytest.raises(DevGuardError, match="NUL"):
        check_select("SELECT 1\x00; DROP TABLE x", "sqlite")


def test_an_over_long_statement_is_refused() -> None:
    with pytest.raises(DevGuardError, match="longer than"):
        check_select("SELECT " + "1," * 20_000 + "1", "sqlite")


def test_sqlite_refuses_to_name_the_secret_table() -> None:
    with pytest.raises(DevGuardError, match="signing secrets"):
        check_sqlite_select("SELECT * FROM wh_secret")


@pytest.mark.parametrize(
    "table", ["auth_credential", "auth_session", "auth_token_secret", "auth_attempt"]
)
def test_sqlite_refuses_to_name_a_credential_table(table: str) -> None:
    with pytest.raises(DevGuardError, match="holds credentials"):
        check_sqlite_select(f"SELECT * FROM {table.upper()}")


# The review of S41 found that a Postgres function deny-list cannot be complete: ts_stat and
# ts_rewrite run a SQL string server-side, so a denied name split with `||` reads files, the role
# password hashes and wh_secret as the superuser. There is no Postgres guard to bypass any more:
# every statement is refused before it is parsed.
POSTGRES_PAYLOADS = [
    "SELECT (ts_stat('select to_tsvector(pg_re'||'ad_file(''/etc/hostname''))')).word",
    "SELECT (ts_stat('select to_tsvector(rolpassword) from pg_au'||'thid')).word",
    "SELECT (ts_stat('select to_tsvector(setting) from pg_set'||'tings where name='||"
    "chr(39)||'data_directory'||chr(39))).word",
    "SELECT (ts_stat('select to_tsvector(secret) from wh_'||'secret')).word",
    "SELECT ts_rewrite('a'::tsquery, 'select ''a''::tsquery, ''b''::tsquery')",
    "SELECT loread(0, 10)",
    "SELECT lowrite(0, 'x')",
    "SELECT txid_current_snapshot()",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT 1",  # even a harmless statement: there is no Postgres reader
]


@pytest.mark.parametrize("sql", POSTGRES_PAYLOADS)
def test_every_postgres_statement_is_refused(sql: str) -> None:
    with pytest.raises(DevGuardError) as caught:
        check_select(sql, "postgres")
    assert str(caught.value) == POSTGRES_REFUSAL


def test_an_unknown_dialect_is_refused() -> None:
    with pytest.raises(DevGuardError, match="dialect"):
        check_select("SELECT 1", "mysql")
