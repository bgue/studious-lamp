"""Trace: the n-hop tree of records reachable through links (brief 7.5, sketch 12 "Trace").

Breadth-first from a record along links in the chosen direction(s). Each record appears once, at the
depth where it is first reached, so cycles and diamonds do not repeat. The result is plain models
for a tree widget, the API (``/trace``) and MCP (``trace``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import bindparam, text

from tl_core.links.provider import get_vocabulary
from tl_core.services.errors import RecordNotFoundError, UnknownRelationError
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
    root_row = uow.conn().execute(_RECORD_SQL, {"id": record_id}).mappings().first()
    if root_row is None:
        raise RecordNotFoundError(f"no record {record_id!r}")
    vocabulary = get_vocabulary()
    order = {code: index for index, code in enumerate(vocabulary.codes())}
    want_out = direction in ("out", "both")
    want_in = direction in ("in", "both")

    def neighbours(rid: str) -> list[dict[str, Any]]:
        rows = (
            uow.conn()
            .execute(
                _NEIGHBOURS_SQL,
                {
                    "id": rid,
                    "want_out": want_out,
                    "want_in": want_in,
                    "yes": True,
                    "statuses": list(statuses),
                },
            )
            .mappings()
            .all()
        )
        found = [dict(row) for row in rows]
        found.sort(
            key=lambda row: (
                row["direction"] != "out",
                order.get(str(row["relation"]), len(order)),
                str(row["key"] or ""),
                str(row["link_id"]),
            )
        )
        return found

    root = TraceNode(
        record_id=str(root_row["id"]),
        key=root_row["key"],
        title=str(root_row["title"]),
        type=str(root_row["type"]),
        status=root_row["status"],
        voided=bool(root_row["voided"]),
        depth=0,
    )
    nodes: dict[str, TraceNode] = {root.record_id: root}
    frontier = [root]
    for level in range(1, depth + 1):
        next_frontier: list[TraceNode] = []
        for parent in frontier:
            for row in neighbours(parent.record_id):
                rid = str(row["id"])
                if rid in nodes or len(nodes) >= max_nodes:
                    continue
                relation = str(row["relation"])
                reached: Literal["out", "in"] = "out" if row["direction"] == "out" else "in"
                try:
                    label = vocabulary.label(relation, reached)
                except UnknownRelationError:
                    label = relation.replace("_", " ")
                child = TraceNode(
                    record_id=rid,
                    key=row["key"],
                    title=str(row["title"]),
                    type=str(row["type"]),
                    status=row["status"],
                    voided=bool(row["voided"]),
                    depth=level,
                    link_id=str(row["link_id"]),
                    link_status=str(row["link_status"]),
                    relation=relation,
                    direction=reached,
                    label=label,
                )
                parent.children.append(child)
                nodes[rid] = child
                next_frontier.append(child)
        frontier = next_frontier
    for node in nodes.values():
        linked = {str(row["id"]) for row in neighbours(node.record_id)}
        node.more = len(linked - set(nodes))
    return root
