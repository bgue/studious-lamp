"""Files over HTTP: the upload flow, listing and downloads (T48).

The upload protocol (brief 20.2) is ``register_upload`` then either ``upload_content`` (bytes
needed) or ``complete_upload`` (the server already holds the bytes: ``ticket.exists``).
``upload_file`` does the whole flow for a local path. Failures raise the same exception classes as
the embedded services (``UploadVerificationError``, ``FileQuarantinedError`` ...).
"""

from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from tl_core.files.queries import FileInfo
from tl_core.files.service import AttachFile, FileResult, RegisterUpload, UploadTicket

from tl_api.client.base import ApiClientBase, quote

CHUNK = 1024 * 1024
DEFAULT_ACTOR = (
    "user:client"  # sent as `actor` in commands; the server replaces it with the token's
)


class FilesApi(ApiClientBase):
    def register_upload(self, cmd: RegisterUpload) -> UploadTicket:
        """Announce a file (``POST /uploads``): a dedupe hit or an upload id to send bytes to."""
        body = cmd.model_dump(mode="json", exclude={"actor"})
        return self._model(UploadTicket, self._post_json("/uploads", body))

    def upload_content(self, upload_id: str, scope: str, data: bytes | BinaryIO) -> FileResult:
        """Send the bytes of a registered upload and complete it (`PUT /uploads/{id}/content`)."""
        response = self._send(
            "PUT",
            f"/uploads/{quote(upload_id)}/content",
            params={"scope": scope},
            content=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        return self._model(FileResult, response.json())

    def complete_upload(self, upload_id: str, scope: str) -> FileResult:
        """Complete an upload that needs no bytes (``ticket.exists``)."""
        data = self._post_json(f"/uploads/{quote(upload_id)}/complete", None, {"scope": scope})
        return self._model(FileResult, data)

    def attach_file(self, cmd: AttachFile) -> FileResult:
        """Attach bytes the scope already holds to another record or slot."""
        body = cmd.model_dump(mode="json", exclude={"actor"})
        return self._model(FileResult, self._post_json("/files/attach", body))

    def list_files(
        self, scope: str, record_id: str, *, slot: str | None = None, current_only: bool = False
    ) -> list[FileInfo]:
        """The files of a record (metadata only)."""
        data = self._get_json(
            f"/records/{quote(record_id)}/files",
            {"scope": scope, "slot": slot, "current_only": current_only},
        )
        return self._models(FileInfo, data)

    def get_file_info(self, scope: str, file_id: str) -> FileInfo:
        data = self._get_json(f"/files/{quote(file_id)}", {"scope": scope})
        return self._model(FileInfo, data)

    def download_file(self, scope: str, file_id: str) -> bytes:
        """The file's bytes. Checked against the SHA-256 the server sends; a mismatch raises."""
        response = self._send("GET", f"/files/{quote(file_id)}/content", params={"scope": scope})
        _check_digest(hashlib.sha256(response.content).hexdigest(), response.headers)
        return response.content

    def download_to(self, scope: str, file_id: str, out: BinaryIO) -> int:
        """Stream the file into ``out`` and return the byte count; verifies the SHA-256 header."""
        path = f"/files/{quote(file_id)}/content"
        digest = hashlib.sha256()
        count = 0
        with self._http.stream(
            "GET", path, params={"scope": scope}, headers=self._auth
        ) as response:
            if response.status_code >= 400:
                response.read()
                raise self.error_from(response)
            for block in response.iter_bytes(CHUNK):
                out.write(block)
                digest.update(block)
                count += len(block)
            _check_digest(digest.hexdigest(), response.headers)
        return count

    def upload_file(
        self,
        scope: str,
        record_id: str,
        path: Path,
        *,
        slot: str | None = None,
        content_type: str | None = None,
    ) -> FileResult:
        """Hash ``path``, register it, send the bytes unless the server has them, and complete."""
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(CHUNK), b""):
                digest.update(block)
                size += len(block)
        media = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        ticket = self.register_upload(
            RegisterUpload(
                actor=DEFAULT_ACTOR,
                source="client",
                scope=scope,
                record_id=record_id,
                slot=slot,
                filename=path.name,
                content_type=media,
                size=size,
                sha256=digest.hexdigest(),
            )
        )
        if ticket.exists:
            return self.complete_upload(ticket.upload_id, scope)
        with path.open("rb") as handle:
            return self.upload_content(ticket.upload_id, scope, handle)


def _check_digest(actual: str, headers: Mapping[str, str]) -> None:
    expected = headers.get("x-content-sha256")
    if expected is not None and expected != actual:
        raise ValueError(f"the downloaded bytes do not match the server's SHA-256 ({expected})")
