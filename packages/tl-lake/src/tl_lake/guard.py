"""The ``lake_query`` guard: one SELECT, reading only lake tables (brief 11.3, 28.4; FANOUT D6).

The statement is parsed by DuckDB itself, so the guard sees exactly what DuckDB would run, and
this module never inspects SQL text with regular expressions. ``json_serialize_sql`` returns the
parse tree as JSON for a SELECT and refuses everything else (DDL, DML, ATTACH, INSTALL, LOAD, COPY,
PRAGMA, SET, EXPLAIN, ...). The guard then requires:

* exactly one statement (a stacked ``SELECT 1; DROP TABLE x`` has two);
* every table reference is a lake table, a CTE of the same query visible at that point, a
  subquery, a join, a ``VALUES`` list, or a pivot of those;
* no table function except a short list of pure generators (``range`` and friends), which rules
  out ``read_csv``, ``read_parquet``, ``read_text``, ``glob``, ``query``, ``duckdb_*`` and the
  rest, as well as replacement scans such as ``FROM 'file.csv'`` (a table named like a path is not
  a lake table);
* no call to a function that reaches outside the lake (``getenv``, ``current_setting``,
  ``read_*``, ...).

Anything the guard does not recognise is refused: the checks fail closed. The guard is the first
of three layers. The connection is also READ_ONLY on the catalog, and :mod:`tl_lake.query` turns off
external file access and locks the configuration before the statement runs, so a gap here would
still not let a query read a file or change the lake.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from typing import Any

from tl_lake.duck import CATALOG, Duck

MAX_SQL_CHARS = 20_000

ALLOWED_TABLE_FUNCTIONS = frozenset({"range", "generate_series", "unnest", "generate_subscripts"})
"""Pure generators. They read nothing outside the query."""

_QUERY_NODES = frozenset({"SELECT_NODE", "SET_OPERATION_NODE", "RECURSIVE_CTE_NODE", "CTE_NODE"})
_TABLE_REFS = frozenset(
    {"BASE_TABLE", "SUBQUERY", "JOIN", "TABLE_FUNCTION", "EMPTY", "EXPRESSION_LIST", "PIVOT"}
)
_DENIED_FUNCTIONS = frozenset(
    {"getenv", "current_setting", "query", "query_table", "glob", "load_extension", "which_secret"}
)
_DENIED_FUNCTION_PREFIXES = (
    "read_",
    "write_",
    "parquet_",
    "sniff_",
    "pragma_",
    "duckdb_",
    "ducklake_",
    "iceberg_",
    "delta_",
)


class GuardError(ValueError):
    """The statement was refused. The message says why, in words a caller can show."""


def _check_function(name: str) -> None:
    lowered = name.lower()
    if lowered in _DENIED_FUNCTIONS or lowered.startswith(_DENIED_FUNCTION_PREFIXES):
        raise GuardError(f"function {name}() is not allowed: it reaches outside the lake")


def _check_table_function(node: dict[str, Any]) -> None:
    function: dict[str, Any] = node.get("function") or {}
    name = str(function.get("function_name", "")).lower()
    if function.get("catalog") or function.get("schema") not in ("", None, "main"):
        raise GuardError(f"table function {name or '?'}() must not be qualified")
    if name not in ALLOWED_TABLE_FUNCTIONS:
        raise GuardError(
            f"table function {name or '?'}() is not allowed: only "
            f"{', '.join(sorted(ALLOWED_TABLE_FUNCTIONS))} can be used in FROM"
        )


def _check_base_table(node: dict[str, Any], ctes: frozenset[str], tables: frozenset[str]) -> None:
    catalog = str(node.get("catalog_name", "")).lower()
    schema = str(node.get("schema_name", "")).lower()
    name = str(node.get("table_name", "")).lower()
    if not catalog and not schema and name in ctes:
        return
    if catalog not in ("", CATALOG) or schema not in ("", "main"):
        where = ".".join(part for part in (catalog, schema) if part)
        raise GuardError(f"only the {CATALOG} catalog can be queried, not {where}")
    if name not in tables:
        raise GuardError(f"{node.get('table_name')!r} is not a lake table")


def _walk(node: Any, ctes: frozenset[str], tables: frozenset[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, ctes, tables)
        return
    if not isinstance(node, dict):
        return
    cte_map = node.get("cte_map")
    if isinstance(cte_map, dict):
        ctes = ctes | {str(entry["key"]).lower() for entry in cte_map.get("map", [])}
    kind = node.get("type")
    if "class" not in node and isinstance(kind, str) and "alias" in node and "sample" in node:
        # A table reference (the only dicts with both keys and no expression class).
        if kind not in _TABLE_REFS:
            raise GuardError(f"{kind} in FROM is not allowed")
        if kind == "BASE_TABLE":
            _check_base_table(node, ctes, tables)
        elif kind == "TABLE_FUNCTION":
            _check_table_function(node)
    if node.get("class") in ("FUNCTION", "WINDOW") and "function_name" in node:
        _check_function(str(node["function_name"]))
    for value in node.values():
        _walk(value, ctes, tables)


def check_sql(con: Duck, sql: str, tables: Collection[str]) -> None:
    """Raise :class:`GuardError` unless ``sql`` is one SELECT over lake ``tables`` only.

    ``con`` is any DuckDB connection; it is used only to parse.
    """
    if len(sql) > MAX_SQL_CHARS:
        raise GuardError(f"the statement is longer than {MAX_SQL_CHARS} characters")
    if not sql.strip():
        raise GuardError("the statement is empty")
    row = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()
    assert row is not None
    parsed: dict[str, Any] = json.loads(row[0])
    if parsed.get("error"):
        message = str(parsed.get("error_message", "")).splitlines()[0]
        if "Only SELECT" in message:
            raise GuardError("only a single SELECT statement is allowed")
        raise GuardError(f"the statement does not parse: {message}")
    statements: list[dict[str, Any]] = parsed.get("statements", [])
    if len(statements) != 1:
        raise GuardError(
            "exactly one statement is allowed"
            if statements
            else "the statement is empty (comments only)"
        )
    node = statements[0]["node"]
    if node.get("type") not in _QUERY_NODES:
        raise GuardError(f"{node.get('type')} is not allowed")
    _walk(node, frozenset(), frozenset(t.lower() for t in tables))
