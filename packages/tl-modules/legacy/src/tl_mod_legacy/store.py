"""Reading and writing the files of a load run: the source, the extracted rows, the profile, the
report (brief 20.1). Every write goes through the file service's ``by_module`` path, so no client
can put a file into these slots with a command, and every read checks the digest the ledger holds.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any

from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_core.uow import UnitOfWork

from tl_mod_legacy.errors import SourceFileError
from tl_mod_legacy.model import Grid
from tl_mod_legacy.names import ACTOR, SLOT_EXTRACTED, SLOT_PROFILE, SLOT_REPORT, SLOT_SOURCE

JSON_TYPE = "application/json"


@dataclass(frozen=True)
class Stored:
    file_id: str
    sha256: str
    size: int


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


class RunFiles:
    def __init__(self, files: FileService) -> None:
        self._files = files

    def write(
        self,
        uow: UnitOfWork,
        *,
        scope: str,
        record_id: str,
        slot: str,
        filename: str,
        content_type: str,
        data: bytes,
        actor: str,
        source: str,
        correlation_id: str,
    ) -> Stored:
        digest = hashlib.sha256(data).hexdigest()
        base = {
            "actor": actor,
            "source": source,
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
                content_type=content_type,
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

    def read(self, uow: UnitOfWork, scope: str, file_id: str, sha256: str) -> bytes:
        """The bytes of a file; ``SourceFileError`` when they are not the ones the ledger holds."""
        opened = self._files.open_file(uow, scope, file_id, actor=ACTOR)
        try:
            data = opened.data.read()
        finally:
            opened.data.close()
        if hashlib.sha256(data).hexdigest() != sha256 or len(data) != opened.info.size:
            raise SourceFileError("a file of the run is not the one the ledger recorded")
        return data

    def read_grid(self, uow: UnitOfWork, scope: str, file_id: str, sha256: str) -> Grid:
        body = json.loads(self.read(uow, scope, file_id, sha256))
        return Grid(columns=list(body["columns"]), rows=[list(row) for row in body["rows"]])

    def read_json(self, uow: UnitOfWork, scope: str, file_id: str, sha256: str) -> Any:
        return json.loads(self.read(uow, scope, file_id, sha256))


def grid_bytes(grid: Grid) -> bytes:
    return canonical_bytes({"columns": grid.columns, "rows": grid.rows})


__all__ = [
    "JSON_TYPE",
    "SLOT_EXTRACTED",
    "SLOT_PROFILE",
    "SLOT_REPORT",
    "SLOT_SOURCE",
    "RunFiles",
    "Stored",
    "canonical_bytes",
    "grid_bytes",
]
