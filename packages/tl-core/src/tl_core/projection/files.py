"""FileProjector: file events into ``cur_files`` (brief 20.2, 5.4).

One row per attachment, keyed by the file stream. ``File.Uploaded`` inserts the row as
``quarantined``; ``File.Processed`` makes it ``available`` and, for a cardinality-one slot, marks
the files it replaces (``supersedes`` in the payload) as superseded; ``File.Rejected`` makes it
``rejected``. Rows are never deleted. Deterministic: the new row depends only on the event and on
the rows already in the database; the status that follows an event comes from
``tl_core.files.lifecycle.next_file_status``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.files.lifecycle import FILE_EVENT_TYPES, FileStatus, next_file_status
from tl_core.ledger import Event, canonical_json, iso_utc

_INSERT_SQL = text(
    "INSERT INTO cur_files (file_id, scope, record_id, slot, revision, sha256, size, "
    "content_type, filename, status, deduplicated, superseded_by, report_json, reason, "
    "uploaded_by, uploaded_at, processed_at, updated_at, version, last_seq) VALUES "
    "(:file_id, :scope, :record_id, :slot, :revision, :sha256, :size, :content_type, :filename, "
    ":status, :deduplicated, NULL, NULL, NULL, :uploaded_by, :uploaded_at, NULL, :updated_at, "
    ":version, :last_seq)"
)
_STATUS_SQL = text("SELECT status FROM cur_files WHERE file_id = :file_id")
_SUPERSEDE_SQL = text(
    "UPDATE cur_files SET superseded_by = :file_id "
    "WHERE file_id = :old_id AND superseded_by IS NULL"
)


class FileProjector:
    name = "files"
    handles = FILE_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_files", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == "File.Uploaded":
            self._insert(conn, event)
        else:
            self._change(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_files"))

    @staticmethod
    def _insert(conn: Connection, event: Event) -> None:
        payload = event.payload
        stamp = iso_utc(event.recorded_at)
        conn.execute(
            _INSERT_SQL,
            {
                "file_id": event.stream_id,
                "scope": event.scope,
                "record_id": payload["record_id"],
                "slot": payload.get("slot"),
                "revision": payload.get("revision", 1),
                "sha256": payload["sha256"],
                "size": payload["size"],
                "content_type": payload["content_type"],
                "filename": payload["filename"],
                "status": next_file_status(None, event.event_type),
                "deduplicated": bool(payload.get("deduplicated", False)),
                "uploaded_by": event.actor,
                "uploaded_at": stamp,
                "updated_at": stamp,
                "version": event.stream_version,
                "last_seq": event.seq,
            },
        )

    @staticmethod
    def _change(conn: Connection, event: Event) -> None:
        payload = event.payload
        row = conn.execute(_STATUS_SQL, {"file_id": event.stream_id}).first()
        if row is None:
            raise LookupError(f"no cur_files row for stream {event.stream_id}")
        current: FileStatus = row.status
        stamp = iso_utc(event.recorded_at)
        changes: dict[str, Any] = {
            "status": next_file_status(current, event.event_type),
            "version": event.stream_version,
            "last_seq": event.seq,
            "updated_at": stamp,
            "processed_at": stamp,
        }
        report = payload.get("report")
        if report is not None:
            changes["report_json"] = canonical_json(report)
        if event.event_type == "File.Rejected":
            changes["reason"] = payload.get("reason")
        # Column names are fixed literals chosen above; only values come from the event.
        assignments = ", ".join(f"{column} = :{column}" for column in changes)
        conn.execute(
            text(f"UPDATE cur_files SET {assignments} WHERE file_id = :file_id"),
            {**changes, "file_id": event.stream_id},
        )
        if event.event_type == "File.Processed":
            superseded: list[str] = payload.get("supersedes") or []
            for old_id in superseded:
                conn.execute(_SUPERSEDE_SQL, {"file_id": event.stream_id, "old_id": old_id})
