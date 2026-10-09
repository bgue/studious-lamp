"""Map LinkML built-in types to SQL column types and DEFAULT literals.

Pure and table-driven: no LinkML or SQLAlchemy import. The DDL generator core (P0-I1-T04b)
calls these functions. The generated DDL targets SQLite and PostgreSQL (brief §14,
build spec 03 §9).
"""

import decimal
import json as _json
from typing import Final, Literal

Dialect = Literal["sqlite", "postgres"]

TYPE_TABLE: Final[dict[str, dict[Dialect, str]]] = {
    "string": {"sqlite": "TEXT", "postgres": "TEXT"},
    "uri": {"sqlite": "TEXT", "postgres": "TEXT"},
    "uriorcurie": {"sqlite": "TEXT", "postgres": "TEXT"},
    "curie": {"sqlite": "TEXT", "postgres": "TEXT"},
    "ncname": {"sqlite": "TEXT", "postgres": "TEXT"},
    "objectidentifier": {"sqlite": "TEXT", "postgres": "TEXT"},
    "nodeidentifier": {"sqlite": "TEXT", "postgres": "TEXT"},
    "jsonpointer": {"sqlite": "TEXT", "postgres": "TEXT"},
    "jsonpath": {"sqlite": "TEXT", "postgres": "TEXT"},
    "sparqlpath": {"sqlite": "TEXT", "postgres": "TEXT"},
    "enum": {"sqlite": "TEXT", "postgres": "TEXT"},
    "integer": {"sqlite": "INTEGER", "postgres": "BIGINT"},
    "boolean": {"sqlite": "INTEGER", "postgres": "BOOLEAN"},
    "float": {"sqlite": "REAL", "postgres": "REAL"},
    "double": {"sqlite": "REAL", "postgres": "DOUBLE PRECISION"},
    "decimal": {"sqlite": "NUMERIC", "postgres": "NUMERIC"},
    "date": {"sqlite": "TEXT", "postgres": "DATE"},
    "datetime": {"sqlite": "TEXT", "postgres": "TIMESTAMPTZ"},
    "time": {"sqlite": "TEXT", "postgres": "TIME"},
    "date_or_datetime": {"sqlite": "TEXT", "postgres": "TEXT"},
}


def _lookup(linkml_type: str) -> dict[Dialect, str]:
    row = TYPE_TABLE.get(linkml_type)
    if row is None:
        raise ValueError(f"unsupported LinkML type: {linkml_type}")
    return row


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def column_type(linkml_type: str, dialect: Dialect, *, json: bool = False) -> str:
    """SQL type for a LinkML built-in type name (lower case, as in linkml:types).

    json=True returns the JSON column type for the dialect whatever linkml_type is: TEXT on sqlite,
    JSONB on postgres. Raise ValueError(f"unsupported LinkML type: {linkml_type}") for a name not in
    the table.
    """
    if json:
        return "TEXT" if dialect == "sqlite" else "JSONB"
    return _lookup(linkml_type)[dialect]


def sql_literal(linkml_type: str, value: object, dialect: Dialect, *, json: bool = False) -> str:
    """Render value as a SQL literal for a DEFAULT clause. See the rules below."""
    # Rule 1: None is NULL for every type.
    if value is None:
        return "NULL"
    # Rule 2: JSON columns serialise the value, whatever linkml_type is.
    if json:
        return _quote(_json.dumps(value, sort_keys=True, separators=(",", ":")))
    # Rule 3: unknown type names raise, as column_type does.
    _lookup(linkml_type)
    # Rule 4: boolean.
    if linkml_type == "boolean":
        if not isinstance(value, bool):
            raise TypeError(f"boolean literal requires a bool, got {type(value).__name__}")
        if dialect == "sqlite":
            return "1" if value else "0"
        return "TRUE" if value else "FALSE"
    # Rule 5: integer.
    if linkml_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"integer literal requires an int, got {type(value).__name__}")
        return str(value)
    # Rule 6: float and double.
    if linkml_type in ("float", "double"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"{linkml_type} literal requires an int or float, got {type(value).__name__}"
            )
        return repr(float(value))
    # Rule 7: decimal.
    if linkml_type == "decimal":
        if isinstance(value, bool) or not isinstance(value, (int, float, decimal.Decimal)):
            raise TypeError(
                f"decimal literal requires an int, float or Decimal, got {type(value).__name__}"
            )
        return str(value)
    # Rule 8: every other known type (text-like, enum, date, datetime, time) is a quoted string.
    if not isinstance(value, str):
        raise TypeError(f"{linkml_type} literal requires a str, got {type(value).__name__}")
    return _quote(value)
