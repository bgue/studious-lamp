"""The lake's tables: bronze ``events``, the ``_tl_sync`` watermark, and the silver mapping.

Silver tables are mapped from the generated current-state schema (brief 28.2): the column list and
types come from the committed Postgres DDL in ``tl_schema/generated/ddl/postgres``, which is the
dialect-neutral statement of each column's type, translated to DuckDB types here. Promoted pset
columns (``pset__<pset>__<property>``) are not in the generated files, because they depend on the
effective schema at run time; they are found by reflecting the ledger table and mapped by their
reflected type.

Type decisions
--------------
* Timestamps are ``TIMESTAMP`` holding UTC (no zone), so a Python client needs no pytz.
* Booleans are ``BOOLEAN`` even where SQLite stores 0/1.
* ``REAL``, ``DOUBLE PRECISION`` and ``NUMERIC`` are ``DOUBLE``; JSON columns are ``VARCHAR``
  holding the canonical JSON text.
* Bronze ``recorded_at`` and ``effective_at`` stay ``VARCHAR`` holding the exact ISO text the ledger
  hashed, so ``event_hash`` re-verifies from the lake and from archive Parquet alike.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
)
from sqlalchemy.types import TypeEngine
from tl_schema.ddl_loader import statements

SYNC_TABLE = "_tl_sync"
EVENTS_TABLE = "events"


@dataclass(frozen=True)
class Column:
    name: str
    duck_type: str
    not_null: bool = False


EVENTS_COLUMNS: tuple[Column, ...] = (
    Column("seq", "BIGINT", True),
    Column("event_id", "VARCHAR", True),
    Column("stream_id", "VARCHAR", True),
    Column("stream_type", "VARCHAR", True),
    Column("stream_version", "BIGINT", True),
    Column("event_type", "VARCHAR", True),
    Column("schema_version", "BIGINT", True),
    Column("scope", "VARCHAR", True),
    Column("payload", "VARCHAR", True),
    Column("actor", "VARCHAR", True),
    Column("recorded_at", "VARCHAR", True),
    Column("effective_at", "VARCHAR", True),
    Column("correlation_id", "VARCHAR", True),
    Column("causation_id", "VARCHAR"),
    Column("source", "VARCHAR", True),
    Column("prev_hash", "VARCHAR"),
    Column("hash", "VARCHAR", True),
)
"""Bronze ``events``: the columns of the ledger ``events`` table, in table order. An archive
segment's ``events.parquet`` carries the same names, with the same text for timestamps and
payload."""

SYNC_COLUMNS: tuple[Column, ...] = (
    Column("snapshot_id", "BIGINT", True),
    Column("first_seq", "BIGINT", True),
    Column("last_seq", "BIGINT", True),
    Column("synced_at", "TIMESTAMP", True),
)


@dataclass(frozen=True)
class SilverTable:
    """One conformed table: a lake name, the ledger table it mirrors, and how rows are replaced.

    A row is replaced when its stream changes, which every projector records in ``last_seq``.
    ``key`` is the column rows are matched on when replacing. A table with a ``driver`` is replaced
    for every key that changed in the driver table instead: ``pset_values`` has several rows per
    record and a record that loses its last value has no changed row to find.
    """

    name: str
    source: str
    key: str
    driver: str | None = None


SILVER_TABLES: tuple[SilverTable, ...] = (
    SilverTable("cur_core_record", "cur_core_record", "id"),
    SilverTable("links", "cur_links", "link_id"),
    SilverTable("pset_values", "cur_pset_values", "record_id", driver="cur_core_record"),
)
RECORD_SOURCE = "cur_core_record"
"""The ledger table that drives ``pset_values`` and carries one row per record."""

_PG_TO_DUCK = {
    "TEXT": "VARCHAR",
    "BIGINT": "BIGINT",
    "INTEGER": "BIGINT",
    "BOOLEAN": "BOOLEAN",
    "REAL": "DOUBLE",
    "DOUBLE PRECISION": "DOUBLE",
    "NUMERIC": "DOUBLE",
    "TIMESTAMPTZ": "TIMESTAMP",
    "DATE": "DATE",
    "TIME": "TIME",
    "JSONB": "VARCHAR",
}
_COLUMN_LINE = re.compile(r"^\s*(\w+)\s+([A-Z]+(?: PRECISION)?)\b(.*?),?\s*$")
_SKIP = ("CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK")


def generated_columns(source: str) -> list[Column]:
    """The columns of a generated current-state table, typed for DuckDB, in declared order."""
    create = next(s for s in statements(source, "postgres") if s.startswith("CREATE TABLE"))
    columns: list[Column] = []
    for line in create.splitlines()[1:]:
        if line.startswith(")"):
            break
        match = _COLUMN_LINE.match(line)
        if match is None or match.group(1).upper() in _SKIP:
            continue
        name, pg_type, rest = match.groups()
        duck = _PG_TO_DUCK.get(pg_type)
        if duck is None:
            raise ValueError(f"{source}.{name}: no DuckDB type for generated type {pg_type}")
        not_null = "NOT NULL" in rest or "PRIMARY KEY" in rest
        columns.append(Column(name, duck, not_null))
    return columns


def reflected_duck_type(sql_type: TypeEngine[object]) -> str:
    """DuckDB type for a ledger column the generated DDL does not describe (promoted columns)."""
    if isinstance(sql_type, Boolean):
        return "BOOLEAN"
    if isinstance(sql_type, Integer):
        return "BIGINT"
    if isinstance(sql_type, (Float, Numeric)):
        return "DOUBLE"
    if isinstance(sql_type, DateTime):
        return "TIMESTAMP"
    if isinstance(sql_type, Date):
        return "DATE"
    return "VARCHAR"


def silver_columns(
    table: SilverTable, ledger_columns: list[tuple[str, TypeEngine[object]]]
) -> list[Column]:
    """The lake columns for ``table``: the ledger's columns, typed from the generated DDL.

    ``ledger_columns`` is the ledger table as reflected, in order. A column the generated DDL
    knows takes its type and nullability; any other (a promoted pset column) is typed by
    reflection and nullable. The generated columns come first in the generated order, then the
    rest in ledger order, so a fresh lake and an evolved one list columns the same way.
    """
    generated = {c.name: c for c in generated_columns(table.source)}
    present = {name for name, _ in ledger_columns}
    missing = [name for name in generated if name not in present]
    if missing:
        raise ValueError(f"ledger table {table.source} lacks generated columns {missing}")
    extra = [
        Column(name, reflected_duck_type(sql_type))
        for name, sql_type in ledger_columns
        if name not in generated
    ]
    return [*generated.values(), *extra]
