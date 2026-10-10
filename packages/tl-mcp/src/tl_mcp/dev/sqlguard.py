"""The ``query_db`` SQL guard: one SELECT (or WITH ... SELECT), reading dev tables only.

It follows the approach of the lake guard (:mod:`tl_lake.guard`, LEARNINGS L-P0-I7-B4, B7): the
statement is parsed by a real parser, the checks run on the parse tree, CTE names are scoped the
way SQL scopes them, and anything not recognised is refused. The guard is the first of three layers;
the executor (:mod:`tl_mcp.dev.query`) adds a read-only connection and, on SQLite, an authoriser, so
a gap here still cannot write or read a secret.

* **SQLite** is checked on the text (one statement; it must start with SELECT or WITH after
  comments); SQLite's own authoriser is the strict layer, because SQLite SQL is not DuckDB SQL.
* **Postgres** is parsed with DuckDB's parser (``json_serialize_sql`` parses and runs nothing).
  DuckDB's grammar is derived from Postgres's, so ordinary Postgres SELECTs parse. The tree must
  hold exactly one SELECT whose tables are in the default schema (or ``information_schema.tables``
  and ``.columns``), none of them denied, whose table functions come from a short list of pure
  generators, and whose function calls avoid everything that reaches outside the query (files,
  settings, sequences, other databases, procedures that run SQL). The raw text is checked for the
  same names as well, so a difference between the two parsers cannot hide one.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

import duckdb
from tl_lake.guard import MAX_SQL_CHARS

from tl_mcp.dev.errors import DevGuardError

DENIED_TABLES = frozenset({"wh_secret"})
"""Tables no dev tool may read: webhook signing secrets live in ``wh_secret.secret``."""

ALLOWED_TABLE_FUNCTIONS = frozenset(
    {
        "generate_series",
        "generate_subscripts",
        "unnest",
        "range",
        "json_each",
        "json_each_text",
        "jsonb_each",
        "jsonb_each_text",
        "json_array_elements",
        "json_array_elements_text",
        "jsonb_array_elements",
        "jsonb_array_elements_text",
        "string_to_table",
    }
)
_INFORMATION_SCHEMA_TABLES = frozenset({"tables", "columns"})

_QUERY_NODES = frozenset({"SELECT_NODE", "SET_OPERATION_NODE", "RECURSIVE_CTE_NODE", "CTE_NODE"})
_TABLE_REFS = frozenset(
    {"BASE_TABLE", "SUBQUERY", "JOIN", "TABLE_FUNCTION", "EMPTY", "EXPRESSION_LIST", "PIVOT"}
)
_DENIED_FUNCTIONS = frozenset(
    {
        "set_config",
        "current_setting",
        "nextval",
        "setval",
        "currval",
        "lastval",
        "dblink",
        "query",
        "query_table",
        "load_extension",
        "txid_current",
    }
)
_DENIED_FUNCTION_PREFIXES = (
    "pg_",
    "lo_",
    "dblink_",
    "query_to_",
    "cursor_to_",
    "table_to_",
    "schema_to_",
    "database_to_",
    "read_",
    "write_",
    "glob",
    "duckdb_",
)
_RAW_DENY = re.compile(
    r"pg_[a-z_0-9]*\s*\(|\blo_[a-z_]+\s*\(|dblink|set_config|current_setting|query_to_"
    r"|cursor_to_|table_to_xml|schema_to_xml|database_to_xml|\b(?:next|set|curr|last)val\b"
    r"|wh_secret|pg_read|copy\s+|load_extension",
    re.IGNORECASE,
)
_PATH_CHARS = re.compile(r"[/\\.*?\[\x00-\x1f]")

_parser: Any = None
_parser_lock = threading.Lock()


def _parse(sql: str) -> dict[str, Any]:
    """The parse tree of ``sql`` as DuckDB sees it (parse only; nothing runs)."""
    global _parser
    with _parser_lock:
        if _parser is None:
            _parser = duckdb.connect(":memory:")
        row = _parser.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()
    assert row is not None
    parsed: dict[str, Any] = json.loads(row[0])
    return parsed


def _common_checks(sql: str) -> None:
    if not sql.strip():
        raise DevGuardError("the statement is empty")
    if len(sql) > MAX_SQL_CHARS:
        raise DevGuardError(f"the statement is longer than {MAX_SQL_CHARS} characters")
    if "\x00" in sql:
        raise DevGuardError("the statement contains a NUL character")


# --- SQLite --------------------------------------------------------------------------------------

_LEADING_NOISE = re.compile(r"\A(?:\s+|--[^\n]*(?:\n|\Z)|/\*.*?\*/)*", re.DOTALL)


def check_sqlite_select(sql: str) -> None:
    """Refuse text that is not a single SELECT or WITH statement.

    This is a pre-check for a clear message. The strict layers are SQLite's one-statement rule for
    ``execute``, the read-only connection and the authoriser in :mod:`tl_mcp.dev.query`.
    """
    _common_checks(sql)
    body = sql[_LEADING_NOISE.match(sql).end() :]  # type: ignore[union-attr]
    keyword = re.match(r"[A-Za-z]+", body)
    if keyword is None or keyword.group(0).lower() not in ("select", "with"):
        raise DevGuardError("only a single SELECT (or WITH ... SELECT) statement is allowed")
    if re.search(r"wh_secret", sql, re.IGNORECASE):
        raise DevGuardError("wh_secret holds signing secrets and cannot be read")


# --- Postgres ------------------------------------------------------------------------------------


def _check_function(name: str) -> None:
    lowered = name.lower()
    if lowered in _DENIED_FUNCTIONS or lowered.startswith(_DENIED_FUNCTION_PREFIXES):
        raise DevGuardError(f"function {name}() is not allowed: it reaches outside the query")


def _check_name(name: str) -> None:
    if _PATH_CHARS.search(name):
        raise DevGuardError("a table name must not contain a path or glob character")


def _check_base_table(node: dict[str, Any], ctes: frozenset[str]) -> None:
    catalog = str(node.get("catalog_name", "")).lower()
    schema = str(node.get("schema_name", "")).lower()
    name = str(node.get("table_name", "")).lower()
    _check_name(name)
    if name in DENIED_TABLES:
        raise DevGuardError(f"{name} holds secrets and cannot be read")
    if not catalog and not schema and name in ctes:
        return
    if catalog:
        raise DevGuardError("a table name must not name a catalog")
    if schema == "information_schema":
        if name not in _INFORMATION_SCHEMA_TABLES:
            raise DevGuardError("only information_schema.tables and .columns can be read")
        return
    if schema not in ("", "public"):
        raise DevGuardError(f"schema {schema!r} cannot be read; only the default schema")
    if name.startswith("pg_"):
        raise DevGuardError("system tables cannot be read")


def _check_table_function(node: dict[str, Any]) -> None:
    function: dict[str, Any] = node.get("function") or {}
    name = str(function.get("function_name", "")).lower()
    if function.get("catalog") or function.get("schema") not in ("", None):
        raise DevGuardError(f"table function {name or '?'}() must not be qualified")
    if name not in ALLOWED_TABLE_FUNCTIONS:
        raise DevGuardError(
            f"table function {name or '?'}() is not allowed: only "
            f"{', '.join(sorted(ALLOWED_TABLE_FUNCTIONS))} can be used in FROM"
        )


def _walk_ctes(cte_map: dict[str, Any], ctes: frozenset[str]) -> frozenset[str]:
    """Check each CTE body with only the names visible there; return the names the rest sees.

    A CTE is visible to the CTEs after it in the same WITH and to the query that owns the WITH,
    never inside its own body, except in the recursive term of a recursive CTE.
    """
    visible = ctes
    for entry in cte_map.get("map", []):
        name = str(entry["key"]).lower()
        _check_name(name)
        body = entry["value"]["query"]["node"]
        if isinstance(body, dict) and body.get("type") == "RECURSIVE_CTE_NODE":
            inner = body.get("cte_map")
            seen = _walk_ctes(inner, visible) if isinstance(inner, dict) else visible
            for key, part in body.items():
                if key != "cte_map":
                    _walk(part, seen | {name} if key == "right" else seen)
        else:
            _walk(body, visible)
        visible = visible | {name}
    return visible


def _walk(node: Any, ctes: frozenset[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, ctes)
        return
    if not isinstance(node, dict):
        return
    cte_map = node.get("cte_map")
    if isinstance(cte_map, dict):
        ctes = _walk_ctes(cte_map, ctes)
    kind = node.get("type")
    if "class" not in node and isinstance(kind, str) and "alias" in node and "sample" in node:
        if kind not in _TABLE_REFS:
            raise DevGuardError(f"{kind} in FROM is not allowed")
        if kind == "BASE_TABLE":
            _check_base_table(node, ctes)
        elif kind == "TABLE_FUNCTION":
            _check_table_function(node)
    if node.get("class") in ("FUNCTION", "WINDOW") and "function_name" in node:
        _check_function(str(node["function_name"]))
    for key, value in node.items():
        if key != "cte_map":
            _walk(value, ctes)


def check_postgres_select(sql: str) -> None:
    """Raise :class:`DevGuardError` unless ``sql`` is one SELECT over dev tables."""
    _common_checks(sql)
    if _RAW_DENY.search(sql):
        raise DevGuardError(
            "the statement names something that reaches outside the query "
            "(a pg_* function, a secret table, set_config, a sequence function, dblink ...)"
        )
    parsed = _parse(sql)
    if parsed.get("error"):
        message = str(parsed.get("error_message", "")).splitlines()[0]
        if "Only SELECT" in message:
            raise DevGuardError("only a single SELECT statement is allowed")
        raise DevGuardError(f"the statement does not parse: {message}")
    statements: list[dict[str, Any]] = parsed.get("statements", [])
    if len(statements) != 1:
        raise DevGuardError(
            "exactly one statement is allowed"
            if statements
            else "the statement is empty (comments only)"
        )
    node = statements[0]["node"]
    if node.get("type") not in _QUERY_NODES:
        raise DevGuardError(f"{node.get('type')} is not allowed")
    _walk(node, frozenset())


def check_select(sql: str, dialect: str) -> None:
    """Dispatch on the dialect of the dev target (``sqlite`` or ``postgres``)."""
    if dialect == "sqlite":
        check_sqlite_select(sql)
    elif dialect == "postgres":
        check_postgres_select(sql)
    else:
        raise DevGuardError(f"unknown dialect {dialect!r}")
