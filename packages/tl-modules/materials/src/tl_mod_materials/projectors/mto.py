"""MtoProjector: ``MTO.Defined``, ``MTOLine.Defined`` and ``MTOLine.Assigned``.

A line starts with ``reserved_qty`` and ``issued_qty`` at zero; the movement projector moves them.
Publishing take-offs is S4's: the events already project, so S4 only appends them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_materials.common import ZERO, num, parse_qty
from tl_mod_materials.names import (
    MTO_DEFINED,
    MTO_LINE_ASSIGNED,
    MTO_LINE_DEFINED,
    MTO_LINE_TABLE,
    MTO_LINE_VIEW,
    MTO_TABLE,
    MTO_VIEW,
)
from tl_mod_materials.projectors._common import ddl_for, require_row, touch_record

_INSERT = text(
    f"INSERT INTO {MTO_TABLE} (id, scope, derived_document_id, revision_id, line_count, "
    "last_seq) VALUES (:id, :scope, :derived_document_id, :revision_id, :line_count, :last_seq)"
)
_INSERT_LINE = text(
    f"INSERT INTO {MTO_LINE_TABLE} (id, scope, mto_id, line_no, project_item_id, qty, uom, "
    "tag_id, work_package_id, reserved_qty, issued_qty, last_seq) VALUES (:id, :scope, :mto_id, "
    ":line_no, :project_item_id, :qty, :uom, :tag_id, :work_package_id, :reserved_qty, "
    ":issued_qty, :last_seq)"
)
_ASSIGN = text(
    f"UPDATE {MTO_LINE_TABLE} SET work_package_id = :work_package_id, last_seq = :last_seq "
    "WHERE id = :id"
)


class MtoProjector:
    name = "materials_mto"
    handles = frozenset({MTO_DEFINED, MTO_LINE_DEFINED, MTO_LINE_ASSIGNED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(MTO_TABLE, dialect)
            + ddl_for(MTO_LINE_TABLE, dialect)
            + ddl_for(MTO_VIEW, dialect)
            + ddl_for(MTO_LINE_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == MTO_DEFINED:
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "derived_document_id": payload["derived_document_id"],
                    "revision_id": payload["revision_id"],
                    "line_count": int(payload["line_count"]),
                    "last_seq": event.seq,
                },
            )
        elif kind == MTO_LINE_DEFINED:
            conn.execute(
                _INSERT_LINE,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "mto_id": payload["mto_id"],
                    "line_no": int(payload["line_no"]),
                    "project_item_id": payload["project_item_id"],
                    "qty": num(parse_qty(payload["qty"])),
                    "uom": payload["uom"],
                    "tag_id": payload.get("tag_id"),
                    "work_package_id": payload.get("work_package_id"),
                    "reserved_qty": num(ZERO),
                    "issued_qty": num(ZERO),
                    "last_seq": event.seq,
                },
            )
        elif kind == MTO_LINE_ASSIGNED:
            done = conn.execute(
                _ASSIGN,
                {
                    "id": event.stream_id,
                    "work_package_id": payload["work_package_id"],
                    "last_seq": event.seq,
                },
            )
            require_row(done.rowcount, MTO_LINE_TABLE, event)
        else:
            raise ValueError(f"MtoProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {MTO_LINE_TABLE}"))
        conn.execute(text(f"DELETE FROM {MTO_TABLE}"))
