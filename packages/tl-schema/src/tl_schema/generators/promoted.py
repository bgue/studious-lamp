"""Promoted columns: typed columns on ``cur_core_record`` for ``materialize: true`` properties.

Brief 5.4: current-state tables carry typed columns for company-standard pset properties marked
``materialize: true``. Which properties those are comes from the effective schema at runtime, so
the DDL is generated here from an ``EffectiveSchema`` (brief 27.7: "DDL diff: new promoted
columns"), not from ``schema/core``. This module only builds statements; adapters and the
projection code execute them, and the existing columns are found by introspection because SQLite
has no ``ADD COLUMN IF NOT EXISTS``.

Column name: ``pset__<pset>__<property>``. Pset and property names never contain a double
underscore (``tl_schema.packages`` enforces that), so a column name maps back to its path.
"""

from __future__ import annotations

from dataclasses import dataclass

from tl_schema.effective import EffectiveSchema
from tl_schema.generators.ddl_types import Dialect, column_type

TABLE = "cur_core_record"
PREFIX = "pset__"
SEPARATOR = "__"
MAX_IDENTIFIER = 63  # PostgreSQL's limit; SQLite has none

_LINKML_TYPE: dict[str, str] = {
    "string": "string",
    "text": "string",
    "enum": "string",
    "ref": "string",
    "date": "string",  # stored as ISO text on both dialects; a DATE cast would need Postgres SQL
    "datetime": "string",
    "int": "integer",
    "decimal": "decimal",
    "quantity": "decimal",
    "bool": "boolean",
}


class PromotionError(ValueError):
    """A materialized property that cannot become a column."""


@dataclass(frozen=True)
class PromotedColumn:
    name: str  # "pset__valve_data__size_in"
    pset: str
    property: str
    linkml_type: str  # a key of ddl_types.TYPE_TABLE


def column_name(pset: str, prop: str) -> str:
    return f"{PREFIX}{pset}{SEPARATOR}{prop}"


def split_column(name: str) -> tuple[str, str] | None:
    """``pset__valve_data__size_in`` becomes ``("valve_data", "size_in")``; others give ``None``."""
    if not name.startswith(PREFIX):
        return None
    parts = name[len(PREFIX) :].split(SEPARATOR)
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def promoted_columns(schema: EffectiveSchema) -> list[PromotedColumn]:
    """Columns for every standard-pset property with ``materialize`` set, in pset/property order.

    Custom-section and project properties are never promoted (the compiler rejects the flag
    there); they stay queryable through ``cur_pset_values``.
    """
    columns: list[PromotedColumn] = []
    for pset in schema.psets.values():
        if pset.layer != "standard":
            continue
        for prop in pset.properties.values():
            if not prop.materialize:
                continue
            linkml_type = _LINKML_TYPE.get(prop.kind)
            name = column_name(pset.name, prop.name)
            if linkml_type is None or len(name) > MAX_IDENTIFIER:
                raise PromotionError(f"{pset.name}.{prop.name} cannot be promoted to {name!r}")
            columns.append(PromotedColumn(name, pset.name, prop.name, linkml_type))
    return columns


def column_ddl(column: PromotedColumn, dialect: Dialect) -> list[str]:
    """``ALTER TABLE`` and index statements adding one promoted column.

    The ``ADD COLUMN`` has ``IF NOT EXISTS`` on Postgres only; callers skip existing columns.
    """
    sql_type = column_type(column.linkml_type, dialect)
    guard = " IF NOT EXISTS" if dialect == "postgres" else ""
    return [
        f"ALTER TABLE {TABLE} ADD COLUMN{guard} {column.name} {sql_type}",
        f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_{column.name} ON {TABLE} ({column.name})",
    ]
