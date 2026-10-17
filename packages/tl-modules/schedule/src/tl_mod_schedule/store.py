"""Reading the XER file and writing the report and the raw tables of a snapshot (ADR-0015).

The build is given its file service directly (the worker owns one); nothing here is global, and a
command handler never reads or writes bytes. Files written here go through the service's
``by_module`` path: the snapshot's upload guard refuses the slots ``report`` and ``raw`` to
a person.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_core.uow import UnitOfWork

from tl_mod_schedule.errors import SourceFileError
from tl_mod_schedule.names import SLOT_RAW, SLOT_REPORT

ACTOR = "svc:schedule"
SOURCE = "svc:schedule"
JSON_TYPE = "application/json"
GZIP_TYPE = "application/gzip"
_TYPES = {SLOT_REPORT: JSON_TYPE, SLOT_RAW: GZIP_TYPE}


@dataclass(frozen=True)
class Stored:
    file_id: str
    sha256: str
    size: int


class SnapshotFiles:
    def __init__(self, files: FileService) -> None:
        self._files = files

    def read_source(self, uow: UnitOfWork, scope: str, file_id: str, sha256: str) -> bytes:
        """The bytes of the XER file; ``SourceFileError`` when they are not the ones recorded."""
        opened = self._files.open_file(uow, scope, file_id, actor=ACTOR)
        try:
            data = opened.data.read()
        finally:
            opened.data.close()
        if hashlib.sha256(data).hexdigest() != sha256 or len(data) != opened.info.size:
            raise SourceFileError("the XER file is not the one the ledger recorded")
        return data

    def write(
        self,
        uow: UnitOfWork,
        *,
        scope: str,
        record_id: str,
        slot: str,
        filename: str,
        data: bytes,
        correlation_id: str,
    ) -> Stored:
        """Store ``data`` in a module-written slot (``report`` or ``raw``) of the snapshot."""
        if slot not in _TYPES:
            raise ValueError(f"the module writes only {SLOT_REPORT} and {SLOT_RAW}")
        digest = hashlib.sha256(data).hexdigest()
        base = {
            "actor": ACTOR,
            "source": SOURCE,
            "scope": scope,
            "correlation_id": correlation_id,
        }
        ticket = self._files.register_upload(
            uow,
            RegisterUpload(
                **base,
                record_id=record_id,
                slot=slot,
                filename=filename,
                content_type=_TYPES[slot],
                size=len(data),
                sha256=digest,
            ),
            by_module=True,
        )
        done = self._files.complete_upload(
            uow,
            CompleteUpload(**base, upload_id=ticket.upload_id),
            io.BytesIO(data),
            by_module=True,
        )
        return Stored(file_id=done.file_id, sha256=digest, size=len(data))
