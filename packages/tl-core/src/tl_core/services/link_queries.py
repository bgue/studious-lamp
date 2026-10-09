"""Read queries over links: both directions of a record's links, counts, and picker search.

Links are read from ``cur_links`` (one row per link). A record sees a link from the ``from`` end as
``out`` (the relation label) and from the ``to`` end as ``in`` (the inverse label). Plain
dictionaries and models only: clients never write SQL (brief 16, "Web readiness").

STUB (P0-I3-T03b): the models, SQL constants and signatures are final; the bodies marked
``raise NotImplementedError`` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import bindparam, text

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


def links_of(uow: UnitOfWork, record_id: str, *, include_retracted: bool = False) -> list[LinkView]:
    """Every link of a record in both directions, each with the label as read from this record.

    Retracted links (declined suggestions included) are left out unless ``include_retracted``.
    Order: outbound before inbound, then the relation's place in the vocabulary (unknown codes
    last), then the other record's key, then ``link_id``. Raises ``RecordNotFoundError``.
    """
    raise NotImplementedError


def link_counts(uow: UnitOfWork, record_ids: Sequence[str]) -> dict[str, LinkCounts]:
    """Counts for each id (all zero for a record with no links), read from ``cur_link_counts``."""
    raise NotImplementedError


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
    raise NotImplementedError
