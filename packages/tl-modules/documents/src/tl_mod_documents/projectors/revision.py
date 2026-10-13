"""RevisionProjector: the ``Revision.*`` events into ``cur_documents_revision``.

``Revision.Defined`` inserts the draft; ``Revision.Issued`` sets the issue status, class and date
and makes the revision current for its class; ``Revision.Superseded`` ends that. Deterministic.
Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_documents.names import (
    REVISION_DEFINED,
    REVISION_ISSUED,
    REVISION_SUPERSEDED,
    REVISION_TABLE,
    REVISION_VIEW,
)
from tl_mod_documents.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {REVISION_TABLE} (id, scope, document_id, document_number, code, ordinal, "
    "previous_revision_id, purpose, change_note, revision_date, intended_status, is_current, "
    "last_seq) VALUES (:id, :scope, :document_id, :document_number, :code, :ordinal, "
    ":previous_revision_id, :purpose, :change_note, :revision_date, :intended_status, :is_current, "
    ":last_seq)"
)
_ISSUED_SQL = text(
    f"UPDATE {REVISION_TABLE} SET issue_status = :issue_status, status_class = :status_class, "
    "issued_on = :issued_on, is_current = :is_current, last_seq = :last_seq WHERE id = :id"
)
_SUPERSEDED_SQL = text(
    f"UPDATE {REVISION_TABLE} SET is_current = :is_current, superseded_by = :by, "
    "last_seq = :last_seq WHERE id = :id"
)


class RevisionProjector:
    name = "documents_revision"
    handles = frozenset({REVISION_DEFINED, REVISION_ISSUED, REVISION_SUPERSEDED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(REVISION_TABLE, dialect) + ddl_for(REVISION_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == REVISION_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "document_id": payload["document_id"],
                    "document_number": payload["document_number"],
                    "code": payload["code"],
                    "ordinal": int(payload["ordinal"]),
                    "previous_revision_id": payload.get("previous_revision_id"),
                    "purpose": payload.get("purpose"),
                    "change_note": payload.get("change_note"),
                    "revision_date": payload.get("revision_date"),
                    "intended_status": payload.get("intended_status"),
                    "is_current": False,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == REVISION_ISSUED:
            self._require(
                conn.execute(
                    _ISSUED_SQL,
                    {
                        "id": event.stream_id,
                        "issue_status": payload["issue_status"],
                        "status_class": payload["status_class"],
                        "issued_on": payload["issued_on"],
                        "is_current": True,
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
        elif event.event_type == REVISION_SUPERSEDED:
            self._require(
                conn.execute(
                    _SUPERSEDED_SQL,
                    {
                        "id": event.stream_id,
                        "is_current": False,
                        "by": payload["superseded_by"],
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
        else:
            raise ValueError(f"RevisionProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {REVISION_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {REVISION_TABLE}"))
