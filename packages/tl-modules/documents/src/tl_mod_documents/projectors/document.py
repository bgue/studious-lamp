"""DocumentProjector: the ``Document.*`` events into ``cur_documents_document``.

``Document.Defined`` inserts the row; ``Document.Updated`` applies the changed register fields;
``Document.CurrentRevisionChanged`` rewrites the denormalised ``current_revision_*`` columns (all
null when no revision is current); ``Document.Superseded`` records the replacing document.
Deterministic: the row depends only on the events of the stream. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_documents.names import (
    DOCUMENT_CURRENT_CHANGED,
    DOCUMENT_DEFINED,
    DOCUMENT_SUPERSEDED,
    DOCUMENT_TABLE,
    DOCUMENT_UPDATED,
    DOCUMENT_VIEW,
)
from tl_mod_documents.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {DOCUMENT_TABLE} (id, scope, number, doc_type, discipline, originator, "
    "confidentiality, revision_scheme, pattern_code, last_seq) VALUES "
    "(:id, :scope, :number, :doc_type, :discipline, :originator, :confidentiality, "
    ":revision_scheme, :pattern_code, :last_seq)"
)
_CURRENT_SQL = text(
    f"UPDATE {DOCUMENT_TABLE} SET current_revision_id = :rid, current_revision_code = :code, "
    "current_revision_status = :status, current_revision_class = :cls, "
    "current_revision_issued_on = :issued_on, last_seq = :last_seq WHERE id = :id"
)
_SUPERSEDED_SQL = text(
    f"UPDATE {DOCUMENT_TABLE} SET superseded_by = :by, last_seq = :last_seq WHERE id = :id"
)
_UPDATABLE = ("doc_type", "discipline", "originator", "confidentiality")


class DocumentProjector:
    name = "documents_document"
    handles = frozenset(
        {DOCUMENT_DEFINED, DOCUMENT_UPDATED, DOCUMENT_CURRENT_CHANGED, DOCUMENT_SUPERSEDED}
    )

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(DOCUMENT_TABLE, dialect) + ddl_for(DOCUMENT_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == DOCUMENT_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "number": payload["number"],
                    "doc_type": payload.get("doc_type"),
                    "discipline": payload.get("discipline"),
                    "originator": payload.get("originator"),
                    "confidentiality": payload.get("confidentiality"),
                    "revision_scheme": payload["revision_scheme"],
                    "pattern_code": payload.get("pattern_code"),
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == DOCUMENT_UPDATED:
            changes: dict[str, list[Any]] = payload.get("changes") or {}
            fields = [name for name in _UPDATABLE if name in changes]
            params: dict[str, Any] = {name: changes[name][1] for name in fields}
            sets = ", ".join(f"{name} = :{name}" for name in fields)
            assignments = f"{sets + ', ' if sets else ''}last_seq = :last_seq"
            statement = f"UPDATE {DOCUMENT_TABLE} SET {assignments} WHERE id = :id"
            self._require(
                conn.execute(
                    text(statement), {**params, "id": event.stream_id, "last_seq": event.seq}
                ).rowcount,
                event,
            )
        elif event.event_type == DOCUMENT_CURRENT_CHANGED:
            self._require(
                conn.execute(
                    _CURRENT_SQL,
                    {
                        "id": event.stream_id,
                        "rid": payload.get("current_revision_id"),
                        "code": payload.get("current_revision_code"),
                        "status": payload.get("current_revision_status"),
                        "cls": payload.get("current_revision_class"),
                        "issued_on": payload.get("current_revision_issued_on"),
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
        elif event.event_type == DOCUMENT_SUPERSEDED:
            self._require(
                conn.execute(
                    _SUPERSEDED_SQL,
                    {"id": event.stream_id, "by": payload["superseded_by"], "last_seq": event.seq},
                ).rowcount,
                event,
            )
        else:
            raise ValueError(f"DocumentProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {DOCUMENT_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {DOCUMENT_TABLE}"))
