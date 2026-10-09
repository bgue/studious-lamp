"""Read queries over links: both directions of a record's links, counts, and picker search.

Links are read from ``cur_links`` (one row per link). A record sees a link from the ``from`` end as
``out`` (the relation label) and from the ``to`` end as ``in`` (the inverse label). Plain
dictionaries and models only: clients never write SQL (brief 16, "Web readiness").
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import bindparam, text

from tl_core.links.provider import get_vocabulary
from tl_core.services.errors import RecordNotFoundError, UnknownRelationError
from tl_core.uow import UnitOfWork

Direction = Literal["out", "in"]


class LinkView(BaseModel):
    """One link as seen from one record."""

    link_id: str
    direction: Direction  # out: this record is the `from` end
    relation: str  # the stored forward code, e.g. "raised_against"
    label: str  # how it reads from this record: "raised against" (out) or "has raised" (in)
    other_id: str
    other_key: str | None
    other_title: str
    other_type: str
    other_status: str | None  # workflow state of the record at the other end
    other_voided: bool
    status: str  # suggested | active | stale | broken | retracted
    pin: str | None
    note: str | None
    source: str
    confidence: float | None
    reason: str | None
    declined: bool
    verified_by: str | None
    verified_at: str | None
    created_at: str
    version: int


class LinkCounts(BaseModel):
    record_id: str
    active_out: int = 0
    active_in: int = 0
    stale: int = 0
    broken: int = 0
    suggested: int = 0

    @property
    def active(self) -> int:
        return self.active_out + self.active_in


class LinkTarget(BaseModel):
    """A record offered by the link picker."""

    id: str
    key: str | None
    type: str
    title: str
    status: str | None
    scope: str
    link_total: int  # active links in either direction, for the preview line


_LINKS_SQL = (
    "SELECT l.link_id, l.relation, l.status, l.pin, l.note, l.source, l.confidence, l.reason, "
    "l.declined, l.verified_by, l.verified_at, l.created_at, l.version, "
    "CASE WHEN l.from_id = :id THEN 'out' ELSE 'in' END AS direction, "
    "r.id AS other_id, r.key AS other_key, r.title AS other_title, r.type AS other_type, "
    "r.status AS other_status, r.voided AS other_voided "
    "FROM cur_links l JOIN cur_core_record r "
    "ON r.id = CASE WHEN l.from_id = :id THEN l.to_id ELSE l.from_id END "
    "WHERE (l.from_id = :id OR l.to_id = :id)"
)
_COUNTS_SQL = text(
    "SELECT record_id, active_out, active_in, stale, broken, suggested "
    "FROM cur_link_counts WHERE record_id IN :ids"
).bindparams(bindparam("ids", expanding=True))


def _label(relation: str, direction: Direction) -> str:
    """The label read from one end; a code that left the vocabulary reads as its name."""
    try:
        return get_vocabulary().label(relation, direction)
    except UnknownRelationError:
        return relation.replace("_", " ")


def _like(word: str) -> str:
    """A LIKE pattern for ``word`` anywhere in a value, case-insensitive, wildcards literal."""
    escaped = word.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def links_of(uow: UnitOfWork, record_id: str, *, include_retracted: bool = False) -> list[LinkView]:
    """Every link of a record in both directions, each with the label as read from this record.

    Retracted links (declined suggestions included) are left out unless ``include_retracted``.
    Order: outbound before inbound, then the relation's place in the vocabulary (unknown codes
    last), then the other record's key, then ``link_id``. Raises ``RecordNotFoundError``.
    """
    conn = uow.conn()
    exists = conn.execute(text("SELECT 1 FROM cur_core_record WHERE id = :id"), {"id": record_id})
    if exists.first() is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    sql = _LINKS_SQL if include_retracted else _LINKS_SQL + " AND l.status <> 'retracted'"
    rows = conn.execute(text(sql), {"id": record_id}).mappings().all()
    views = [
        LinkView(
            link_id=row["link_id"],
            direction=row["direction"],
            relation=row["relation"],
            label=_label(row["relation"], row["direction"]),
            other_id=row["other_id"],
            other_key=row["other_key"],
            other_title=row["other_title"],
            other_type=row["other_type"],
            other_status=row["other_status"],
            other_voided=bool(row["other_voided"]),
            status=row["status"],
            pin=row["pin"],
            note=row["note"],
            source=row["source"],
            confidence=row["confidence"],
            reason=row["reason"],
            declined=bool(row["declined"]),
            verified_by=row["verified_by"],
            verified_at=row["verified_at"],
            created_at=row["created_at"],
            version=row["version"],
        )
        for row in rows
    ]
    codes = get_vocabulary().codes()
    rank = {code: index for index, code in enumerate(codes)}
    views.sort(
        key=lambda v: (
            v.direction != "out",
            rank.get(v.relation, len(codes)),
            v.other_key or "",
            v.link_id,
        )
    )
    return views


def link_counts(uow: UnitOfWork, record_ids: Sequence[str]) -> dict[str, LinkCounts]:
    """Counts for each id (all zero for a record with no links), read from ``cur_link_counts``."""
    if not record_ids:
        return {}
    found: dict[str, LinkCounts] = {rid: LinkCounts(record_id=rid) for rid in record_ids}
    rows = uow.conn().execute(_COUNTS_SQL, {"ids": list(found)}).mappings().all()
    for row in rows:
        found[row["record_id"]] = LinkCounts(**dict(row))
    return found


def search_linkable(
    uow: UnitOfWork,
    scope: str,
    query: str,
    *,
    record_type: str | None = None,
    exclude_id: str | None = None,
    limit: int = 20,
) -> list[LinkTarget]:
    """Records a user may link to from ``scope``: that scope's and the company's, never voided.

    Every word of ``query`` must occur (case-insensitive) in the key or the title; an empty query
    lists everything. Keys that start with the first word come first, then by key. Optional filters
    on ``record_type`` and ``exclude_id`` (the record being linked from).
    """
    words = query.split()
    params: dict[str, Any] = {"no": False, "scope": scope, "limit": limit}
    clauses = ["r.voided = :no", "r.scope IN (:scope, 'company')"]
    if record_type is not None:
        clauses.append("r.type = :record_type")
        params["record_type"] = record_type
    if exclude_id is not None:
        clauses.append("r.id <> :exclude_id")
        params["exclude_id"] = exclude_id
    for index, word in enumerate(words):
        clauses.append(
            f"(LOWER(COALESCE(r.key, '')) LIKE :w{index} ESCAPE '\\' "
            f"OR LOWER(r.title) LIKE :w{index} ESCAPE '\\')"
        )
        params[f"w{index}"] = _like(word)
    # The first word as a prefix pattern: _like gives "%word%", so drop the leading "%".
    params["prefix"] = _like(words[0])[1:] if words else "%"
    sql = (
        "SELECT r.id, r.key, r.type, r.title, r.status, r.scope, "
        "COALESCE(c.active_out, 0) + COALESCE(c.active_in, 0) AS link_total "
        "FROM cur_core_record r LEFT JOIN cur_link_counts c ON c.record_id = r.id "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY CASE WHEN LOWER(COALESCE(r.key, '')) LIKE :prefix ESCAPE '\\' THEN 0 ELSE 1 END, "
        "r.key, r.id LIMIT :limit"
    )
    rows = uow.conn().execute(text(sql), params).mappings().all()
    return [LinkTarget(**dict(row)) for row in rows]
