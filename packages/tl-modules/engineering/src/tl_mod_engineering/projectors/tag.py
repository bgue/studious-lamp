"""TagProjector: the ``Tag.*`` events into ``cur_engineering_tag``, and the envelope's conformance.

``Tag.Defined`` and ``Tag.Reclassified`` carry the conformance and effective schema hash computed
when the command ran (the way ``Pset.ValuesSet`` does); the projector copies them into
``cur_core_record`` so the tag register and the generic record grid agree. ``Tag.Superseded``
changes no typed column: the old tag leaves service through its workflow state. Deterministic: the
row depends only on the events of the stream. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_engineering.names import (
    TAG_DEFINED,
    TAG_RECLASSIFIED,
    TAG_SUPERSEDED,
    TAG_TABLE,
)
from tl_mod_engineering.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {TAG_TABLE} (id, scope, number, class_code, area, mnemonic, sequence, "
    "segments_json, pattern_code, number_status, violations_json, origin, last_seq) VALUES "
    "(:id, :scope, :number, :class_code, :area, :mnemonic, :sequence, :segments_json, "
    ":pattern_code, :number_status, :violations_json, :origin, :last_seq)"
)
_RECLASSIFY_SQL = text(
    f"UPDATE {TAG_TABLE} SET class_code = :class_code, last_seq = :last_seq WHERE id = :id"
)
_BUMP_SQL = text(f"UPDATE {TAG_TABLE} SET last_seq = :last_seq WHERE id = :id")


class TagProjector:
    name = "engineering_tag"
    handles = frozenset({TAG_DEFINED, TAG_RECLASSIFIED, TAG_SUPERSEDED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(TAG_TABLE, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == TAG_DEFINED:
            sequence = payload.get("sequence")
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "number": payload["number"],
                    "class_code": payload.get("class_code"),
                    "area": payload.get("area"),
                    "mnemonic": payload.get("mnemonic"),
                    "sequence": None if sequence is None else int(sequence),
                    "segments_json": json_text(payload.get("segments") or {}),
                    "pattern_code": payload.get("pattern_code"),
                    "number_status": payload["number_status"],
                    "violations_json": json_text(payload.get("violations") or []),
                    "origin": payload["origin"],
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == TAG_RECLASSIFIED:
            self._require(
                conn.execute(
                    _RECLASSIFY_SQL,
                    {
                        "id": event.stream_id,
                        "class_code": payload["to_class"],
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
        elif event.event_type == TAG_SUPERSEDED:
            self._require(
                conn.execute(_BUMP_SQL, {"id": event.stream_id, "last_seq": event.seq}).rowcount,
                event,
            )
        else:
            raise ValueError(f"TagProjector cannot apply event type: {event.event_type}")
        touch_record(
            conn,
            event,
            conformance=payload.get("conformance"),
            schema_hash=payload.get("effective_schema_hash"),
        )

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {TAG_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {TAG_TABLE}"))
