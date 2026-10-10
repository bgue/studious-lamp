"""The ``query_db`` SQL guard: what is accepted, and the statements that must be refused."""

from __future__ import annotations

import pytest
from tl_mcp.dev import sqlguard
from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.sqlguard import check_postgres_select, check_select, check_sqlite_select

SQLITE_OK = [
    "SELECT 1",
    "select * from cur_core_record where scope = 'project:P1' limit 5",
    "  -- a comment\n SELECT count(*) FROM events",
    "/* c */ WITH t AS (SELECT 1 AS a) SELECT a FROM t",
    "SELECT name, sql FROM sqlite_master",
    "SELECT 1;",
]

POSTGRES_OK = [
    "SELECT 1",
    "select * from cur_core_record where scope = 'project:P1' order by seq desc limit 5",
    "SELECT payload::jsonb ->> 'title' AS t, count(*) FROM events GROUP BY 1",
    "SELECT * FROM public.cur_core_record",
    "WITH t AS (SELECT 1 AS a) SELECT a FROM t",
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 5) SELECT n FROM r",
    "SELECT * FROM generate_series(1, 3) AS g(n)",
    "SELECT * FROM jsonb_each('{\"a\": 1}'::jsonb)",
    "SELECT table_name, column_name FROM information_schema.columns",
    "SELECT a.id FROM cur_core_record a JOIN cur_links b ON b.from_id = a.id",
    "SELECT now(), length('x'), lower('X'), 'a%b' LIKE 'a%'",
    "SELECT 1 UNION SELECT 2",
]


@pytest.mark.parametrize("sql", SQLITE_OK)
def test_sqlite_accepts_a_select(sql: str) -> None:
    check_sqlite_select(sql)
    check_select(sql, "sqlite")


@pytest.mark.parametrize("sql", POSTGRES_OK)
def test_postgres_accepts_a_select(sql: str) -> None:
    check_postgres_select(sql)
    check_select(sql, "postgres")


WRITES = [
    "INSERT INTO events VALUES (1)",
    "UPDATE cur_core_record SET title = 'x'",
    "DELETE FROM events",
    "DROP TABLE events",
    "CREATE TABLE x (a int)",
    "ALTER TABLE events ADD COLUMN a int",
    "TRUNCATE events",
    "PRAGMA writable_schema = ON",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "VACUUM",
    "REINDEX",
    "BEGIN",
    "COMMIT",
    "SET search_path = x",
    "COPY events TO '/tmp/x'",
    "EXPLAIN SELECT 1",
    "CALL f()",
    "GRANT ALL ON events TO public",
    "REPLACE INTO events VALUES (1)",
    "WITH t AS (SELECT 1) DELETE FROM events",
    "SELECT 1; DROP TABLE events",
    "SELECT 1; SELECT 2",
    "",
    "   ",
    "-- only a comment",
    "SELECT 1\x00; DROP TABLE x",
]


@pytest.mark.parametrize("sql", WRITES)
def test_postgres_refuses_everything_but_a_select(sql: str) -> None:
    with pytest.raises(DevGuardError):
        check_postgres_select(sql)


@pytest.mark.parametrize(
    "sql",
    [s for s in WRITES if not s.startswith(("SELECT 1; SELECT", "WITH t AS (SELECT 1) DELETE"))],
)
def test_sqlite_refuses_text_that_is_not_a_select(sql: str) -> None:
    # `SELECT 1; SELECT 2` and the WITH ... DELETE are refused by SQLite and its authoriser, which
    # tests/test_dev_query.py checks against a real database.
    if sql.upper().startswith(("SELECT 1; DROP", "SELECT 1\x00")):
        return  # starts like a select: the one-statement rule and the NUL check are elsewhere
    with pytest.raises(DevGuardError):
        check_sqlite_select(sql)


def test_a_statement_with_a_nul_character_is_refused_whatever_the_dialect() -> None:
    for dialect in ("sqlite", "postgres"):
        with pytest.raises(DevGuardError, match="NUL"):
            check_select("SELECT 1\x00; DROP TABLE x", dialect)


def test_an_over_long_statement_is_refused() -> None:
    sql = "SELECT " + "1," * 20_000 + "1"
    for dialect in ("sqlite", "postgres"):
        with pytest.raises(DevGuardError, match="longer than"):
            check_select(sql, dialect)


DENIED_POSTGRES = [
    # files, settings, sequences, other databases, procedures that run SQL
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_read_binary_file('/etc/passwd')",
    "SELECT * FROM pg_ls_dir('/')",
    "SELECT \"pg_read_file\"('/etc/passwd')",
    "SELECT PG_READ_FILE('/etc/passwd')",
    "SELECT pg_sleep(10)",
    "SELECT pg_terminate_backend(1)",
    "SELECT lo_import('/etc/passwd')",
    "SELECT lo_export(1, '/tmp/x')",
    "SELECT set_config('transaction_read_only', 'off', true)",
    "SELECT current_setting('data_directory')",
    "SELECT nextval('s')",
    "SELECT setval('s', 1)",
    "SELECT dblink('host=x', 'select 1')",
    "SELECT query_to_xml('delete from events', true, true, '')",
    "SELECT table_to_xml('events'::regclass, true, true, '')",
    "SELECT cursor_to_xml('c', 1, true, true, '')",
    # secrets
    "SELECT * FROM wh_secret",
    "SELECT secret FROM public.wh_secret",
    'SELECT * FROM "wh_secret"',
    "WITH t AS (SELECT * FROM wh_secret) SELECT * FROM t",
    "SELECT (SELECT secret FROM wh_secret LIMIT 1)",
    # system catalogs and other schemas
    "SELECT * FROM pg_catalog.pg_shadow",
    "SELECT * FROM pg_shadow",
    "SELECT * FROM pg_user",
    "SELECT * FROM information_schema.routines",
    "SELECT * FROM otherschema.t",
    "SELECT * FROM other_db.public.t",
    # table functions and replacement scans
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM '/etc/passwd.csv'",
    "SELECT * FROM 'a.parquet'",
    "SELECT * FROM glob('/*')",
    "SELECT * FROM unknown_function(1)",
    "SELECT * FROM public.generate_series(1, 2)",
    "SELECT * FROM events FOR UPDATE",
]


@pytest.mark.parametrize("sql", DENIED_POSTGRES)
def test_postgres_refuses_what_reaches_outside_the_query(sql: str) -> None:
    with pytest.raises(DevGuardError):
        check_postgres_select(sql)


def test_a_cte_only_covers_the_query_that_defines_it() -> None:
    # Inside its own body a CTE name is the real table: `pg_shadow` here is the system catalog
    with pytest.raises(DevGuardError, match="system tables"):
        check_postgres_select("WITH pg_shadow AS (SELECT * FROM pg_shadow) SELECT * FROM pg_shadow")
    # a scalar subquery's CTE does not reach the outer query
    with pytest.raises(DevGuardError, match="system tables"):
        check_postgres_select(
            "SELECT (WITH pg_user AS (SELECT 1) SELECT 1), (SELECT * FROM pg_user)"
        )
    # but it is the CTE where it is visible, and a CTE defined earlier is visible later
    check_postgres_select("WITH pg_user AS (SELECT 1 AS n) SELECT * FROM pg_user")
    check_postgres_select("WITH a AS (SELECT 1 AS n), b AS (SELECT n FROM a) SELECT * FROM b")


def test_a_cte_cannot_hide_a_secret_table() -> None:
    with pytest.raises(DevGuardError, match="secret"):
        check_postgres_select("WITH wh_secret AS (SELECT 1) SELECT * FROM wh_secret")


def test_the_parse_tree_check_refuses_a_secret_or_a_denied_function_on_its_own() -> None:
    """The raw-text screen is a second layer: the tree walk alone must refuse these too."""
    for sql in (
        "WITH wh_secret AS (SELECT 1) SELECT * FROM wh_secret",
        "SELECT * FROM wh_secret",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT \"set_config\"('a', 'b', true)",
    ):
        tree = sqlguard._parse(sql)["statements"][0]["node"]
        with pytest.raises(DevGuardError):
            sqlguard._walk(tree, frozenset())


def test_a_table_or_cte_name_with_a_path_character_is_refused() -> None:
    for sql in (
        'WITH "/etc/x.csv" AS (SELECT 1) SELECT * FROM "/etc/x.csv"',
        'SELECT * FROM "a.b.c.d"',
        'SELECT * FROM "x*"',
    ):
        with pytest.raises(DevGuardError):
            check_postgres_select(sql)


def test_a_statement_that_does_not_parse_is_refused() -> None:
    with pytest.raises(DevGuardError, match="does not parse"):
        check_postgres_select("SELEC 1")


def test_an_unknown_dialect_is_refused() -> None:
    with pytest.raises(DevGuardError, match="dialect"):
        check_select("SELECT 1", "mysql")


def test_sqlite_refuses_to_name_the_secret_table() -> None:
    with pytest.raises(DevGuardError, match="signing secrets"):
        check_sqlite_select("SELECT * FROM wh_secret")
