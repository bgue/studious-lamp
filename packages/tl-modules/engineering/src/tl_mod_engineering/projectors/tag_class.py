"""TagClassProjector: the ``TagClass.*`` events into ``cur_engineering_tag_class``.

``TagClass.Revised`` carries ``changes`` as ``{field: [old, new]}``; only the fields in
``REVISABLE`` may appear, and a list field is stored as canonical JSON. Deterministic: the row
depends only on the events of the stream. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_engineering.names import (
    TAG_CLASS_CLOSED,
    TAG_CLASS_DEFINED,
    TAG_CLASS_REVISED,
    TAG_CLASS_TABLE,
    TAG_CLASS_VIEW,
)
from tl_mod_engineering.projectors._common import ddl_for, json_text, touch_record

#: Revisable field name to its column. Column names never come from event data.
REVISABLE: Final = {
    "label": "label",
    "family": "family",
    "required_psets": "required_psets_json",
    "itr_templates": "itr_templates_json",
    "mnemonics": "mnemonics_json",
}
_JSON_FIELDS: Final = frozenset({"required_psets", "itr_templates", "mnemonics"})

_INSERT_SQL = text(
    f"INSERT INTO {TAG_CLASS_TABLE} (id, scope, code, label, family, required_psets_json, "
    "itr_templates_json, mnemonics_json, lifecycle, superseded_by, edition, last_seq) VALUES "
    "(:id, :scope, :code, :label, :family, :required_psets_json, :itr_templates_json, "
    ":mnemonics_json, 'active', NULL, :edition, :last_seq)"
)
_CLOSE_SQL = text(
    f"UPDATE {TAG_CLASS_TABLE} SET lifecycle = :lifecycle, superseded_by = :superseded_by, "
    "last_seq = :last_seq WHERE id = :id"
)


class TagClassProjector:
    name = "engineering_tag_class"
    handles = frozenset({TAG_CLASS_DEFINED, TAG_CLASS_REVISED, TAG_CLASS_CLOSED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(TAG_CLASS_TABLE, dialect) + ddl_for(TAG_CLASS_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        if event.event_type == TAG_CLASS_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": payload["code"],
                    "label": payload["label"],
                    "family": payload["family"],
                    "required_psets_json": json_text(payload.get("required_psets") or []),
                    "itr_templates_json": json_text(payload.get("itr_templates") or []),
                    "mnemonics_json": json_text(payload.get("mnemonics") or []),
                    "edition": payload["edition"],
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == TAG_CLASS_REVISED:
            self._revise(conn, event)
        elif event.event_type == TAG_CLASS_CLOSED:
            self._require(
                conn.execute(
                    _CLOSE_SQL,
                    {
                        "id": event.stream_id,
                        "lifecycle": payload["lifecycle"],
                        "superseded_by": payload.get("superseded_by"),
                        "last_seq": event.seq,
                    },
                ).rowcount,
                event,
            )
        else:
            raise ValueError(f"TagClassProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def _revise(self, conn: Connection, event: Event) -> None:
        changes: dict[str, Any] = event.payload["changes"]
        # Validate every field before touching the database, so a bad field writes nothing.
        unknown = sorted(set(changes) - set(REVISABLE))
        if unknown:
            raise ValueError(f"unsupported field in changes: {', '.join(unknown)}")
        assignments: list[str] = []
        params: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        for index, (field, pair) in enumerate(changes.items()):
            value: Any = pair[1]
            param = f"v{index}"
            assignments.append(f"{REVISABLE[field]} = :{param}")
            params[param] = json_text(value) if field in _JSON_FIELDS else value
        assignments.append("last_seq = :last_seq")
        sql = text(f"UPDATE {TAG_CLASS_TABLE} SET {', '.join(assignments)} WHERE id = :id")
        self._require(conn.execute(sql, params).rowcount, event)

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {TAG_CLASS_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {TAG_CLASS_TABLE}"))
