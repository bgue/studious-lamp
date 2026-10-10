"""Add promoted pset columns to ``cur_core_record`` for an effective schema (brief 5.4, 27.7).

``ensure_promoted_columns`` is idempotent: it adds the columns the schema's ``materialize: true``
properties need and are missing, then fills them for existing rows from ``psets_json``. It uses
SQLAlchemy introspection and the generated statements of ``tl_schema.generators.promoted``, so it
contains no dialect-specific SQL. It runs inside the caller's transaction (SQLite and Postgres both
support transactional DDL).
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import Connection, text
from tl_schema.effective import EffectiveSchema
from tl_schema.generators.ddl_types import Dialect
from tl_schema.generators.promoted import TABLE, PromotedColumn, column_ddl, promoted_columns

_ROWS_SQL = text(f"SELECT id, psets_json FROM {TABLE}")


def _dialect(conn: Connection) -> Dialect:
    name = conn.dialect.name
    if name == "sqlite":
        return "sqlite"
    if name == "postgresql":
        return "postgres"
    raise ValueError(f"unsupported dialect: {name}")


def table_columns(conn: Connection, table: str) -> list[str]:
    """The column names of ``table`` in table order, read with a query that returns no rows.

    Not ``sqlalchemy.inspect(conn).get_columns``: on Postgres its reflection parses JSON values the
    adapter deliberately returns as text, and it fails on a column with a non-default collation.
    """
    return list(conn.execute(text(f"SELECT * FROM {table} WHERE 1 = 0")).keys())


def ensure_promoted_columns(conn: Connection, schema: EffectiveSchema) -> list[str]:
    """Add the schema's missing promoted columns and backfill them. Returns the names added."""
    wanted = promoted_columns(schema)
    if not wanted:
        return []
    present = set(table_columns(conn, TABLE))
    missing = [column for column in wanted if column.name not in present]
    if not missing:
        return []
    dialect = _dialect(conn)
    for column in missing:
        for statement in column_ddl(column, dialect):
            conn.exec_driver_sql(statement)
    _backfill(conn, missing)
    return [column.name for column in missing]


def _backfill(conn: Connection, columns: list[PromotedColumn]) -> None:
    assignments = ", ".join(f"{c.name} = :{c.name}" for c in columns)
    update = text(f"UPDATE {TABLE} SET {assignments} WHERE id = :id")
    for row in conn.execute(_ROWS_SQL).fetchall():
        psets = cast(dict[str, Any], json.loads(row.psets_json))
        params: dict[str, Any] = {"id": row.id}
        found = False
        for column in columns:
            section: Any = psets.get(column.pset)
            value: Any = (
                cast(dict[str, Any], section).get(column.property)
                if isinstance(section, dict)
                else None
            )
            if isinstance(value, (dict, list)):
                value = None
            params[column.name] = value
            found = found or value is not None
        if found:
            conn.execute(update, params)
