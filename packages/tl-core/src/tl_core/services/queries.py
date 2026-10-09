"""Read queries over the current-state record table (brief 5.4, 6.2).

Both functions return plain envelope dictionaries. Clients (CLI now; TUI and API later) call these
instead of writing SQL. All values are bound parameters; the SQL text is fixed.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from tl_core.uow import UnitOfWork

_SELECT = (
    "SELECT id, key, type, scope, title, description, status, psets_json, voided, "
    "version, last_seq, effective_schema_hash, conformance, created_at, updated_at "
    "FROM cur_core_record"
)

_GET_SQL = text(_SELECT + " WHERE scope = :scope AND key = :key")


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


def get_record(uow: UnitOfWork, scope: str, key: str) -> dict[str, Any] | None:
    """The record with this ``(scope, key)``, voided or not; ``None`` when no row matches."""
    row = uow.conn().execute(_GET_SQL, {"scope": scope, "key": key}).mappings().first()
    if row is None:
        return None
    return _envelope(row)


def list_records(
    uow: UnitOfWork, scope: str, *, status: str | None = None, include_voided: bool = False
) -> list[dict[str, Any]]:
    """Records of ``scope`` ordered by ``created_at, id``.

    Voided rows are left out unless ``include_voided`` is true. ``status``, when given, filters on
    equality.
    """
    clauses: list[str] = ["scope = :scope"]
    params: dict[str, Any] = {"scope": scope}
    if status is not None:
        clauses.append("status = :status")
        params["status"] = status
    if not include_voided:
        clauses.append("voided = :voided")
        params["voided"] = False
    sql = text(f"{_SELECT} WHERE {' AND '.join(clauses)} ORDER BY created_at, id")
    rows = uow.conn().execute(sql, params).mappings().all()
    return [_envelope(row) for row in rows]
