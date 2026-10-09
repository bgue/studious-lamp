"""Read queries over the current-state record table (brief 5.4, 6.2).

Both functions return plain envelope dictionaries. Clients (CLI now; TUI and API later) call these
instead of writing SQL. All values are bound parameters; the SQL text is fixed.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from tl_core.ledger import Event
from tl_core.uow import UnitOfWork

_SELECT = (
    "SELECT id, key, type, scope, title, description, status, psets_json, voided, "
    "version, last_seq, effective_schema_hash, conformance, created_at, updated_at "
    "FROM cur_core_record"
)

_GET_SQL = text(_SELECT + " WHERE scope = :scope AND key = :key")
_GET_BY_ID_SQL = text(_SELECT + " WHERE id = :id")


def _envelope(row: RowMapping) -> dict[str, Any]:
    psets: dict[str, Any] = json.loads(row["psets_json"])
    return {
        "id": row["id"],
        "key": row["key"],
        "type": row["type"],
        "scope": row["scope"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "psets": psets,
        "voided": bool(row["voided"]),
        "version": row["version"],
        "last_seq": row["last_seq"],
        "effective_schema_hash": row["effective_schema_hash"],
        "conformance": row["conformance"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def envelope_from_row(row: RowMapping) -> dict[str, Any]:
    """The envelope dictionary for one ``cur_core_record`` row (all envelope columns selected)."""
    return _envelope(row)


def get_record(uow: UnitOfWork, scope: str, key: str) -> dict[str, Any] | None:
    """The record with this ``(scope, key)``, voided or not; ``None`` when no row matches."""
    row = uow.conn().execute(_GET_SQL, {"scope": scope, "key": key}).mappings().first()
    if row is None:
        return None
    return _envelope(row)


def get_record_by_id(uow: UnitOfWork, record_id: str) -> dict[str, Any] | None:
    """The record with this ``id`` (its stream id), voided or not; ``None`` when no row matches."""
    row = uow.conn().execute(_GET_BY_ID_SQL, {"id": record_id}).mappings().first()
    if row is None:
        return None
    return _envelope(row)


def record_history(uow: UnitOfWork, record_id: str) -> list[Event]:
    """Every event of a record's stream in version order; empty when the record is unknown."""
    return uow.ledger.read_stream(record_id)


SORTABLE_COLUMNS = frozenset(
    {"key", "title", "status", "type", "created_at", "updated_at", "version"}
)
_TEXT_COLUMNS = SORTABLE_COLUMNS - {"version"}  # '' sorts last like NULL
_MAX_LIMIT = 2**63 - 1  # portable "no limit" so OFFSET can be used on its own


def list_records(
    uow: UnitOfWork,
    scope: str,
    *,
    status: str | None = None,
    include_voided: bool = False,
    record_type: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    order_by: list[tuple[str, Literal["asc", "desc"]]] | None = None,
) -> list[dict[str, Any]]:
    """Records of ``scope``, ordered by ``order_by`` or else by ``created_at, id``.

    Voided rows are left out unless ``include_voided`` is true. ``status`` and ``record_type``,
    when given, filter on equality. ``limit`` and ``offset`` page the ordered result; ``limit``
    ``None`` means no limit. ``order_by`` lists ``(column, direction)`` pairs over
    ``SORTABLE_COLUMNS``; empty values (NULL, or '' for text columns) sort last in both
    directions and ``id`` always breaks ties.
    Raises ``ValueError`` for an unknown column or a negative ``limit`` or ``offset``.
    """
    if limit is not None and limit < 0:
        raise ValueError(f"limit must not be negative, got {limit}")
    if offset < 0:
        raise ValueError(f"offset must not be negative, got {offset}")
    clauses: list[str] = ["scope = :scope"]
    params: dict[str, Any] = {"scope": scope}
    if status is not None:
        clauses.append("status = :status")
        params["status"] = status
    if record_type is not None:
        clauses.append("type = :type")
        params["type"] = record_type
    if not include_voided:
        clauses.append("voided = :voided")
        params["voided"] = False
    terms: list[str] = []
    for column, direction in order_by or []:
        if column not in SORTABLE_COLUMNS:
            raise ValueError(f"cannot order by {column!r}; allowed: {sorted(SORTABLE_COLUMNS)}")
        if direction not in ("asc", "desc"):
            raise ValueError(f"direction must be 'asc' or 'desc', got {direction!r}")
        empty = (
            f"{column} IS NULL OR {column} = ''" if column in _TEXT_COLUMNS else f"{column} IS NULL"
        )
        terms.append(f"({empty}), {column} {direction.upper()}")
    order = ", ".join([*terms, "id"]) if terms else "created_at, id"
    paging = ""
    if limit is not None or offset:
        paging = " LIMIT :limit OFFSET :offset"
        params["limit"] = _MAX_LIMIT if limit is None else limit
        params["offset"] = offset
    sql = text(f"{_SELECT} WHERE {' AND '.join(clauses)} ORDER BY {order}{paging}")
    rows = uow.conn().execute(sql, params).mappings().all()
    return [_envelope(row) for row in rows]
