"""StandardProjector: ``Standard.Defined`` and ``Standard.Closed`` into the standards table.

The row belongs to a code list, a mnemonic or a numbering pattern; its ``kind`` comes from the
event payload. Deterministic: the row depends only on the events of the stream. Register it after
``RecordProjector`` (it moves the envelope row's version).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_engineering.names import STANDARD_CLOSED, STANDARD_DEFINED, STANDARD_TABLE
from tl_mod_engineering.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {STANDARD_TABLE} (id, scope, kind, code, label, definition, edition, owner, "
    "adoption, value_list_policy, effective_from, effective_to, lifecycle, superseded_by, "
    "data_json, last_seq) VALUES (:id, :scope, :kind, :code, :label, :definition, :edition, "
    ":owner, :adoption, :value_list_policy, :effective_from, :effective_to, 'active', NULL, "
    ":data_json, :last_seq)"
)
_CLOSE_SQL = text(
    f"UPDATE {STANDARD_TABLE} SET lifecycle = :lifecycle, superseded_by = :superseded_by, "
    "effective_to = COALESCE(:effective_to, effective_to), last_seq = :last_seq WHERE id = :id"
)


class StandardProjector:
    name = "engineering_standard"
    handles = frozenset({STANDARD_DEFINED, STANDARD_CLOSED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(STANDARD_TABLE, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == STANDARD_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "kind": payload["kind"],
                    "code": payload["code"],
                    "label": payload["label"],
                    "definition": payload.get("definition"),
                    "edition": payload["edition"],
                    "owner": payload.get("owner"),
                    "adoption": payload.get("adoption") or "default",
                    "value_list_policy": payload.get("value_list_policy"),
                    "effective_from": payload.get("effective_from"),
                    "effective_to": payload.get("effective_to"),
                    "data_json": json_text(payload.get("data") or {}),
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == STANDARD_CLOSED:
            updated = conn.execute(
                _CLOSE_SQL,
                {
                    "id": event.stream_id,
                    "lifecycle": payload["lifecycle"],
                    "superseded_by": payload.get("superseded_by"),
                    "effective_to": payload.get("effective_to"),
                    "last_seq": event.seq,
                },
            )
            if updated.rowcount == 0:
                raise LookupError(f"no {STANDARD_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"StandardProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {STANDARD_TABLE}"))
