"""File read queries over ``cur_files`` (brief 20.1, 20.2). No store access, no writes.

``list_files`` shows every row of a record, including quarantined, rejected and superseded ones,
unless ``current_only`` is set; metadata is visible to anyone who can read the record, only the
bytes of a quarantined file are restricted (see ``FileService.open_file``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy import Row, text

from tl_core.files.lifecycle import FileStatus
from tl_core.services.errors import UnknownFileError
from tl_core.uow import UnitOfWork

_COLUMNS = (
    "file_id, scope, record_id, slot, revision, sha256, size, content_type, filename, status, "
    "deduplicated, superseded_by, reason, uploaded_by, uploaded_at, processed_at, version"
)
_ONE_SQL = text(f"SELECT {_COLUMNS} FROM cur_files WHERE file_id = :file_id")


class FileInfo(BaseModel):
    """One attachment, as ``cur_files`` holds it."""

    file_id: str
    scope: str
    record_id: str
    slot: str | None
    revision: int
    sha256: str
    size: int
    content_type: str
    filename: str
    status: FileStatus
    deduplicated: bool
    superseded_by: str | None
    reason: str | None
    uploaded_by: str
    uploaded_at: str
    processed_at: str | None
    version: int

    @property
    def current(self) -> bool:
        """True while this is a current file of its slot (available and not superseded)."""
        return self.status == "available" and self.superseded_by is None


def info_from_row(row: Row[Any]) -> FileInfo:
    return FileInfo(
        file_id=row.file_id,
        scope=row.scope,
        record_id=row.record_id,
        slot=row.slot,
        revision=row.revision,
        sha256=row.sha256,
        size=row.size,
        content_type=row.content_type,
        filename=row.filename,
        status=row.status,
        deduplicated=bool(row.deduplicated),
        superseded_by=row.superseded_by,
        reason=row.reason,
        uploaded_by=row.uploaded_by,
        uploaded_at=row.uploaded_at,
        processed_at=row.processed_at,
        version=row.version,
    )


def get_file(uow: UnitOfWork, scope: str, file_id: str) -> FileInfo:
    """One file. Raises ``UnknownFileError`` when it is unknown or belongs to another scope."""
    row = uow.conn().execute(_ONE_SQL, {"file_id": file_id}).first()
    if row is None or row.scope != scope:
        raise UnknownFileError(f"no file {file_id!r} in scope {scope!r}")
    return info_from_row(row)


def list_files(
    uow: UnitOfWork,
    scope: str,
    record_id: str,
    *,
    slot: str | None = None,
    current_only: bool = False,
) -> list[FileInfo]:
    """The files of a record, ordered by slot (generic attachments first), revision, then id.

    ``slot`` limits the list to one slot. ``current_only`` keeps only files that are
    available and not superseded (the current file per slot).
    """
    sql = f"SELECT {_COLUMNS} FROM cur_files WHERE scope = :scope AND record_id = :record_id"
    params: dict[str, Any] = {"scope": scope, "record_id": record_id}
    if slot is not None:
        sql += " AND slot = :slot"
        params["slot"] = slot
    if current_only:
        sql += " AND status = 'available' AND superseded_by IS NULL"
    sql += " ORDER BY COALESCE(slot, ''), revision, file_id"
    rows = uow.conn().execute(text(sql), params).all()
    return [info_from_row(row) for row in rows]
