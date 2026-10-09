"""Trace: the n-hop tree of records reachable through links (brief 7.5, sketch 12 "Trace").

Breadth-first from a record along links in the chosen direction(s). Each record appears once, at the
depth where it is first reached, so cycles and diamonds do not repeat. The result is plain models
for a tree widget, the API (``/trace``) and MCP (``trace``).

STUB (P0-I3-T14a): the models, SQL constants and the signature are final; the body marked
``raise NotImplementedError`` is the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import bindparam, text

from tl_core.uow import UnitOfWork

TraceDirection = Literal["out", "in", "both"]
DEFAULT_STATUSES: tuple[str, ...] = ("active", "stale", "broken")


class TraceNode(BaseModel):
    record_id: str
    key: str | None
    title: str
    type: str
    status: str | None
    voided: bool
    depth: int  # 0 for the root
    # How this node was reached from its parent (None on the root):
    link_id: str | None = None
    link_status: str | None = None
    relation: str | None = None
    direction: Literal["out", "in"] | None = None  # out: the parent is the `from` end
    label: str | None = None  # the relation as read from the parent, e.g. "has raised"
    children: list[TraceNode] = []
    # Linked records that are not in the tree below this node (depth limit or node cap).
    more: int = 0


_RECORD_SQL = text(
    "SELECT id, key, title, type, status, voided FROM cur_core_record WHERE id = :id"
)
_NEIGHBOURS_SQL = text(
    "SELECT l.link_id, l.relation, l.status AS link_status, "
    "CASE WHEN l.from_id = :id THEN 'out' ELSE 'in' END AS direction, "
    "r.id, r.key, r.title, r.type, r.status, r.voided "
    "FROM cur_links l JOIN cur_core_record r "
    "ON r.id = CASE WHEN l.from_id = :id THEN l.to_id ELSE l.from_id END "
    "WHERE (l.from_id = :id AND :want_out = :yes OR l.to_id = :id AND :want_in = :yes) "
    "AND l.status IN :statuses"
).bindparams(bindparam("statuses", expanding=True))


def trace(
    uow: UnitOfWork,
    record_id: str,
    *,
    depth: int = 2,
    direction: TraceDirection = "both",
    statuses: Sequence[str] = DEFAULT_STATUSES,
    max_nodes: int = 200,
) -> TraceNode:
    """The tree of records within ``depth`` hops of ``record_id``.

    ``direction`` follows outbound links, inbound links, or both. Only links whose status is in
    ``statuses`` are followed (default: active, stale, broken). Children of a node are ordered
    outbound first, then by the relation's place in the vocabulary, then by key. At most
    ``max_nodes`` records are included (breadth-first); ``more`` on a node counts linked records
    that are missing below it. Raises ``RecordNotFoundError``.
    """
    raise NotImplementedError
