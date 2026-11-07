"""What the readiness checks are told about one IWP.

``IwpFacts`` is frozen in ``tl_core.readiness.types``. One read, no write. Imports only ``tl_core``
and the awp tables; it never reads another module's tables.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from sqlalchemy import Connection, text
from tl_core.readiness.types import IwpFacts

from tl_mod_awp.names import CONTAINS_RELATION, SCOPE_ITEM, SCOPE_RELATION, TAG_TYPE

#: The most scope ids one IWP may hold in all (a bigger package must be split).
MAX_SCOPE_IDS: Final = 5000
SCOPE_TOO_LARGE: Final = "iwp scope exceeds 5000 records"
NOT_FOUND: Final = "iwp not found"
INITIAL_STATUS: Final = "Draft"

_IWP_SQL = text(
    "SELECT r.id, r.scope, r.key, i.discipline, i.planned_start, i.planned_finish, i.foreman, "
    "i.estimated_hours, s.state FROM cur_core_record r "
    "JOIN cur_awp_iwp i ON i.id = r.id "
    "LEFT JOIN cur_workflow_state s ON s.record_id = r.id WHERE r.id = :id"
)
_SCOPE_SQL = text(
    "SELECT t.type AS type, t.id AS member FROM cur_links l JOIN cur_core_record t "
    "ON t.id = l.to_id WHERE l.from_id = :id AND l.relation = :rel AND l.status = 'active' "
    "UNION ALL "
    "SELECT t.type AS type, t.id AS member FROM cur_links l JOIN cur_core_record t "
    "ON t.id = l.from_id WHERE l.to_id = :id AND l.relation = :scope_rel AND l.source = 'rule' "
    "AND l.status = 'active' AND t.type IN (:item_type, :tag_type) "
    "ORDER BY 1, 2 LIMIT :limit"
)
_PINNED_SQL = text(
    "SELECT link_id FROM cur_links WHERE from_id = :id AND status = 'active' "
    "AND pin IS NOT NULL ORDER BY link_id"
)


def _date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def iwp_facts(conn: Connection, iwp_id: str) -> IwpFacts:
    """The facts of one IWP.

    ``LookupError`` when there is no such IWP; ``ValueError`` when its scope holds more than
    ``MAX_SCOPE_IDS`` records.
    """
    row = conn.execute(_IWP_SQL, {"id": iwp_id}).mappings().first()
    if row is None:
        raise LookupError(NOT_FOUND)
    scope_ids: dict[str, list[str]] = {}
    scope_rows = conn.execute(
        _SCOPE_SQL,
        {
            "id": iwp_id,
            "rel": CONTAINS_RELATION,
            "scope_rel": SCOPE_RELATION,
            "item_type": SCOPE_ITEM,
            "tag_type": TAG_TYPE,
            "limit": MAX_SCOPE_IDS + 1,
        },
    ).all()
    if len(scope_rows) > MAX_SCOPE_IDS:
        raise ValueError(SCOPE_TOO_LARGE)
    for record_type, to_id in scope_rows:
        scope_ids.setdefault(str(record_type), []).append(str(to_id))
    pinned = [str(r[0]) for r in conn.execute(_PINNED_SQL, {"id": iwp_id}).all()]
    hours = row["estimated_hours"]
    return IwpFacts(
        record_id=str(row["id"]),
        scope=str(row["scope"]),
        key=str(row["key"] or ""),
        status=str(row["state"] or INITIAL_STATUS),
        discipline=row["discipline"],
        planned_start=_date(row["planned_start"]),
        planned_finish=_date(row["planned_finish"]),
        foreman=row["foreman"],
        estimated_hours=float(hours) if hours else None,
        scope_ids=scope_ids,
        pinned_document_links=pinned,
    )
