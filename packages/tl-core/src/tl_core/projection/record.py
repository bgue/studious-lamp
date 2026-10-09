"""RecordProjector: core.Record events into cur_core_record (brief §5.4, build spec 03 §7).

Deterministic: rows depend only on the event's own fields (payload, seq, stream_version,
recorded_at, scope, stream_id). Rows are never deleted; a void sets the ``voided`` flag.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, canonical_json, iso_utc

# Fixed whitelist: changes-field name -> column name. Column names never come from event data.
_CHANGEABLE_COLUMNS: dict[str, str] = {
    "title": "title",
    "description": "description",
    "status": "status",
    "key": "key",
    "psets": "psets_json",
}

_INSERT_SQL = text(
    "INSERT INTO cur_core_record ("
    "id, key, type, scope, title, description, status, psets_json, voided, "
    "version, last_seq, effective_schema_hash, conformance, created_at, updated_at"
    ") VALUES ("
    ":id, :key, :type, :scope, :title, :description, :status, :psets_json, :voided, "
    ":version, :last_seq, :effective_schema_hash, :conformance, :created_at, :updated_at"
    ")"
)

_VOID_SQL = text(
    "UPDATE cur_core_record SET voided = :voided, version = :version, "
    "last_seq = :last_seq, updated_at = :updated_at WHERE id = :id"
)


class RecordProjector:
    name = "core_record"
    handles = frozenset({"Record.Created", "Record.Updated", "Record.Voided", "Record.Corrected"})

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite":
            return statements("cur_core_record", "sqlite")
        if dialect == "postgres":
            return statements("cur_core_record", "postgres")
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == "Record.Created":
            self._create(conn, event)
        elif event.event_type in ("Record.Updated", "Record.Corrected"):
            self._change(conn, event)
        elif event.event_type == "Record.Voided":
            self._void(conn, event)
        else:
            raise ValueError(f"RecordProjector cannot apply event type: {event.event_type}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_core_record"))

    def _create(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        conn.execute(
            _INSERT_SQL,
            {
                "id": event.stream_id,
                "key": payload.get("key"),
                "type": payload["record_type"],
                "scope": event.scope,
                "title": payload["title"],
                "description": payload.get("description"),
                "status": None,
                "psets_json": canonical_json(payload.get("psets") or {}),
                "voided": False,
                "version": event.stream_version,
                "last_seq": event.seq,
                "effective_schema_hash": None,
                "conformance": "ok",
                "created_at": stamp,
                "updated_at": stamp,
            },
        )

    def _change(self, conn: Connection, event: Event) -> None:
        changes: dict[str, Any] = event.payload["changes"]
        # Validate every field before touching the database, so a bad field writes nothing.
        assignments: list[str] = []
        params: dict[str, Any] = {}
        for index, (field, pair) in enumerate(changes.items()):
            column = _CHANGEABLE_COLUMNS.get(field)
            if column is None:
                raise ValueError(f"unsupported field in changes: {field}")
            new_value: Any = pair[1]
            if field == "psets":
                new_value = canonical_json(new_value)
            param = f"v{index}"
            assignments.append(f"{column} = :{param}")
            params[param] = new_value
        assignments += ["version = :version", "last_seq = :last_seq", "updated_at = :updated_at"]
        params.update(
            {
                "id": event.stream_id,
                "version": event.stream_version,
                "last_seq": event.seq,
                "updated_at": iso_utc(event.recorded_at),
            }
        )
        sql = text(f"UPDATE cur_core_record SET {', '.join(assignments)} WHERE id = :id")
        result = conn.execute(sql, params)
        self._require_row(result.rowcount, event)

    def _void(self, conn: Connection, event: Event) -> None:
        result = conn.execute(
            _VOID_SQL,
            {
                "voided": True,
                "version": event.stream_version,
                "last_seq": event.seq,
                "updated_at": iso_utc(event.recorded_at),
                "id": event.stream_id,
            },
        )
        self._require_row(result.rowcount, event)

    @staticmethod
    def _require_row(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no cur_core_record row for stream {event.stream_id}")
