"""TransmittalProjector: the ``Transmittal.*`` events into the transmittal tables.

``Transmittal.Defined`` inserts the transmittal and one ``cur_documents_transmittal_item`` row per
revision it carries; ``Transmittal.Issued`` and ``Transmittal.ResponseRecorded`` fill in the dates
and the answer. The workflow state is the envelope ``status``, set by the core workflow projector.
Deterministic. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_documents.names import (
    TRANSMITTAL_DEFINED,
    TRANSMITTAL_ISSUED,
    TRANSMITTAL_ITEM_TABLE,
    TRANSMITTAL_RESPONSE,
    TRANSMITTAL_TABLE,
    TRANSMITTAL_VIEW,
)
from tl_mod_documents.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {TRANSMITTAL_TABLE} (id, scope, number, direction, purpose, due_date, "
    "recipients_json, item_count, last_seq) VALUES (:id, :scope, :number, :direction, :purpose, "
    ":due_date, :recipients_json, :item_count, :last_seq)"
)
_ITEM_SQL = text(
    f"INSERT INTO {TRANSMITTAL_ITEM_TABLE} (item_id, scope, transmittal_id, position, "
    "revision_id, document_id, document_number, revision_code, issue_status, last_seq) VALUES "
    "(:item_id, :scope, :transmittal_id, :position, :revision_id, :document_id, "
    ":document_number, :revision_code, :issue_status, :last_seq)"
)
_ISSUED_SQL = text(
    f"UPDATE {TRANSMITTAL_TABLE} SET issued_on = :issued_on, last_seq = :last_seq WHERE id = :id"
)
_RESPONSE_SQL = text(
    f"UPDATE {TRANSMITTAL_TABLE} SET response_code = :code, response_note = :note, "
    "responded_on = :responded_on, last_seq = :last_seq WHERE id = :id"
)


class TransmittalProjector:
    name = "documents_transmittal"
    handles = frozenset({TRANSMITTAL_DEFINED, TRANSMITTAL_ISSUED, TRANSMITTAL_RESPONSE})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(TRANSMITTAL_TABLE, dialect)
            + ddl_for(TRANSMITTAL_ITEM_TABLE, dialect)
            + ddl_for(TRANSMITTAL_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == TRANSMITTAL_DEFINED:
            items: list[dict[str, Any]] = payload.get("items") or []
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "number": payload["number"],
                    "direction": payload["direction"],
                    "purpose": payload["purpose"],
                    "due_date": payload.get("due_date"),
                    "recipients_json": json_text(payload.get("recipients") or []),
                    "item_count": len(items),
                    "last_seq": event.seq,
                },
            )
            for position, item in enumerate(items, start=1):
                conn.execute(
                    _ITEM_SQL,
                    {
                        "item_id": f"{event.stream_id}:{position:03d}",
                        "scope": event.scope,
                        "transmittal_id": event.stream_id,
                        "position": position,
                        "revision_id": item["revision_id"],
                        "document_id": item["document_id"],
                        "document_number": item["document_number"],
                        "revision_code": item["revision_code"],
                        "issue_status": item.get("issue_status"),
                        "last_seq": event.seq,
                    },
                )
        elif event.event_type == TRANSMITTAL_ISSUED:
            self._require(
                conn.execute(
                    _ISSUED_SQL,
                    {
                        "id": event.stream_id,
                        "issued_on": payload["issued_on"],
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
        elif event.event_type == TRANSMITTAL_RESPONSE:
            self._require(
                conn.execute(
                    _RESPONSE_SQL,
                    {
                        "id": event.stream_id,
                        "code": payload["response_code"],
                        "note": payload.get("response_note"),
                        "responded_on": payload["responded_on"],
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
        else:
            raise ValueError(f"TransmittalProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {TRANSMITTAL_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {TRANSMITTAL_ITEM_TABLE}"))
        conn.execute(text(f"DELETE FROM {TRANSMITTAL_TABLE}"))
