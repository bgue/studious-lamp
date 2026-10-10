"""Files over HTTP: the upload flow, listing and downloads (T48).

STUB (P0-I4-T48): function bodies below raise ``NotImplementedError``. Names, signatures and
docstrings are final; implement the bodies, then delete this paragraph.

The upload protocol (brief 20.2) is ``register_upload`` then either ``upload_content`` (bytes
needed) or ``complete_upload`` (the server already holds the bytes: ``ticket.exists``).
``upload_file`` does the whole flow for a local path. Failures raise the same exception classes as
the embedded services (``UploadVerificationError``, ``FileQuarantinedError`` ...).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from tl_core.files.queries import FileInfo
from tl_core.files.service import AttachFile, FileResult, RegisterUpload, UploadTicket

from tl_api.client.base import ApiClientBase

CHUNK = 1024 * 1024
DEFAULT_ACTOR = (
    "user:client"  # sent as `actor` in commands; the server replaces it with the token's
)


class FilesApi(ApiClientBase):
    def register_upload(self, cmd: RegisterUpload) -> UploadTicket:
        """Announce a file (``POST /uploads``): a dedupe hit or an upload id to send bytes to."""
        raise NotImplementedError("STUB (P0-I4-T48)")

    def upload_content(self, upload_id: str, scope: str, data: bytes | BinaryIO) -> FileResult:
        """Send the bytes of a registered upload and complete it (`PUT /uploads/{id}/content`)."""
        raise NotImplementedError("STUB (P0-I4-T48)")

    def complete_upload(self, upload_id: str, scope: str) -> FileResult:
        """Complete an upload that needs no bytes (``ticket.exists``)."""
        raise NotImplementedError("STUB (P0-I4-T48)")

    def attach_file(self, cmd: AttachFile) -> FileResult:
        """Attach bytes the scope already holds to another record or slot."""
        raise NotImplementedError("STUB (P0-I4-T48)")

    def list_files(
        self, scope: str, record_id: str, *, slot: str | None = None, current_only: bool = False
    ) -> list[FileInfo]:
        """The files of a record (metadata only)."""
        raise NotImplementedError("STUB (P0-I4-T48)")

    def get_file_info(self, scope: str, file_id: str) -> FileInfo:
        raise NotImplementedError("STUB (P0-I4-T48)")

    def download_file(self, scope: str, file_id: str) -> bytes:
        """The file's bytes. Checked against the SHA-256 the server sends; a mismatch raises."""
        raise NotImplementedError("STUB (P0-I4-T48)")

    def download_to(self, scope: str, file_id: str, out: BinaryIO) -> int:
        """Stream the file into ``out`` and return the byte count; verifies the SHA-256 header."""
        raise NotImplementedError("STUB (P0-I4-T48)")

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
        raise NotImplementedError("STUB (P0-I4-T48)")


def _check_digest(actual: str, headers: Mapping[str, str]) -> None:
    raise NotImplementedError("STUB (P0-I4-T48)")
