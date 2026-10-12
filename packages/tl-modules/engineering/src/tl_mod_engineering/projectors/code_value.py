"""CodeValueProjector: ``CodeValue.Defined`` and ``CodeValue.Closed`` into the values table.

Deterministic: the row depends only on the events of the stream. Register it after
``RecordProjector`` (it moves the envelope row's version).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_engineering.names import CODE_VALUE_CLOSED, CODE_VALUE_DEFINED, CODE_VALUE_TABLE
from tl_mod_engineering.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {CODE_VALUE_TABLE} (id, scope, code_list, code, label, meaning, crosswalk, "
    "origin, sort_order, effective_from, effective_to, lifecycle, superseded_by, attributes_json, "
    "edition, last_seq) VALUES (:id, :scope, :code_list, :code, :label, :meaning, :crosswalk, "
    ":origin, :sort_order, :effective_from, :effective_to, 'active', NULL, :attributes_json, "
    ":edition, :last_seq)"
)
_CLOSE_SQL = text(
    f"UPDATE {CODE_VALUE_TABLE} SET lifecycle = :lifecycle, superseded_by = :superseded_by, "
    "effective_to = COALESCE(:effective_to, effective_to), last_seq = :last_seq WHERE id = :id"
)


class CodeValueProjector:
    name = "engineering_code_value"
    handles = frozenset({CODE_VALUE_DEFINED, CODE_VALUE_CLOSED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CODE_VALUE_TABLE, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == CODE_VALUE_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code_list": payload["code_list"],
                    "code": payload["code"],
                    "label": payload["label"],
                    "meaning": payload.get("meaning"),
                    "crosswalk": payload.get("crosswalk"),
                    "origin": payload["origin"],
                    "sort_order": int(payload.get("sort_order") or 0),
                    "effective_from": payload.get("effective_from"),
                    "effective_to": payload.get("effective_to"),
                    "attributes_json": json_text(payload.get("attributes") or {}),
                    "edition": payload["edition"],
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == CODE_VALUE_CLOSED:
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
                raise LookupError(f"no {CODE_VALUE_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"CodeValueProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CODE_VALUE_TABLE}"))
