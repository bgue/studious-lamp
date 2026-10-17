"""DocumentSchemaProjector: the ``DocumentSchema.*`` events into ``cur_documents_document_schema``.

``DocumentSchema.Defined`` inserts the version (active); ``DocumentSchema.Retired`` makes it not
active and keeps the reason. A version is never edited. Deterministic. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_documents.names import (
    DOCUMENT_SCHEMA_DEFINED,
    DOCUMENT_SCHEMA_RETIRED,
    DOCUMENT_SCHEMA_TABLE,
    DOCUMENT_SCHEMA_VIEW,
)
from tl_mod_documents.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {DOCUMENT_SCHEMA_TABLE} (id, scope, code, semver, ordinal, target_kind, "
    "key_column, json_schema_json, sample_json, mapping_json, mapping_notes, doc_types_json, "
    "content_hash, is_active, last_seq) VALUES (:id, :scope, :code, :semver, :ordinal, "
    ":target_kind, :key_column, :json_schema_json, :sample_json, :mapping_json, :mapping_notes, "
    ":doc_types_json, :content_hash, :is_active, :last_seq)"
)
_RETIRE_SQL = text(
    f"UPDATE {DOCUMENT_SCHEMA_TABLE} SET is_active = :is_active, retired_reason = :reason, "
    "last_seq = :last_seq WHERE id = :id"
)


def _optional_json(value: Any) -> str | None:
    return None if value is None else json_text(value)


class DocumentSchemaProjector:
    name = "documents_document_schema"
    handles = frozenset({DOCUMENT_SCHEMA_DEFINED, DOCUMENT_SCHEMA_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(DOCUMENT_SCHEMA_TABLE, dialect) + ddl_for(DOCUMENT_SCHEMA_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == DOCUMENT_SCHEMA_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "semver": payload["semver"],
                    "ordinal": int(payload["ordinal"]),
                    "target_kind": payload.get("target_kind"),
                    "key_column": payload.get("key_column"),
                    "json_schema_json": json_text(payload["json_schema"]),
                    "sample_json": _optional_json(payload.get("sample")),
                    "mapping_json": _optional_json(payload.get("mapping")),
                    "mapping_notes": payload.get("mapping_notes"),
                    "doc_types_json": json_text(payload.get("doc_types") or []),
                    "content_hash": payload["content_hash"],
                    "is_active": True,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == DOCUMENT_SCHEMA_RETIRED:
            found = conn.execute(
                _RETIRE_SQL,
                {
                    "id": event.stream_id,
                    "is_active": False,
                    "reason": payload["reason"],
                    "last_seq": event.seq,
                },
            ).rowcount
            if found == 0:
                raise LookupError(f"no {DOCUMENT_SCHEMA_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"DocumentSchemaProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {DOCUMENT_SCHEMA_TABLE}"))
