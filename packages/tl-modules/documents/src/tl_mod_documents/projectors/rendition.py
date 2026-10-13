"""RenditionProjector: the ``Rendition.*`` events into ``cur_documents_rendition``.

``Rendition.Defined`` inserts the row as current; ``Rendition.Superseded`` (on the older rendition's
stream) makes it not current. Deterministic. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_documents.names import (
    RENDITION_DEFINED,
    RENDITION_SUPERSEDED,
    RENDITION_TABLE,
    RENDITION_VIEW,
)
from tl_mod_documents.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {RENDITION_TABLE} (id, scope, revision_id, document_id, kind, file_id, filename, "
    "content_type, size, sha256, page_count, is_current, last_seq) VALUES (:id, :scope, "
    ":revision_id, :document_id, :kind, :file_id, :filename, :content_type, :size, :sha256, "
    ":page_count, :is_current, :last_seq)"
)
_SUPERSEDED_SQL = text(
    f"UPDATE {RENDITION_TABLE} SET is_current = :is_current, superseded_by = :by, "
    "last_seq = :last_seq WHERE id = :id"
)


class RenditionProjector:
    name = "documents_rendition"
    handles = frozenset({RENDITION_DEFINED, RENDITION_SUPERSEDED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(RENDITION_TABLE, dialect) + ddl_for(RENDITION_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == RENDITION_DEFINED:
            pages = payload.get("page_count")
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "revision_id": payload["revision_id"],
                    "document_id": payload["document_id"],
                    "kind": payload["kind"],
                    "file_id": payload["file_id"],
                    "filename": payload["filename"],
                    "content_type": payload["content_type"],
                    "size": int(payload["size"]),
                    "sha256": payload["sha256"],
                    "page_count": None if pages is None else int(pages),
                    "is_current": True,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == RENDITION_SUPERSEDED:
            found = conn.execute(
                _SUPERSEDED_SQL,
                {
                    "id": event.stream_id,
                    "is_current": False,
                    "by": payload["superseded_by"],
                    "last_seq": event.seq,
                },
            ).rowcount
            if found == 0:
                raise LookupError(f"no {RENDITION_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"RenditionProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {RENDITION_TABLE}"))
