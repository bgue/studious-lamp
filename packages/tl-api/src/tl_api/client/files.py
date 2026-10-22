"""Files over HTTP: the upload flow, listing and downloads (T48).

The upload protocol (brief 20.2) is ``register_upload`` then either ``upload_content`` (bytes
needed) or ``complete_upload`` (the server already holds the bytes: ``ticket.exists``).
``upload_file`` does the whole flow for a local path. Failures raise the same exception classes as
the embedded services (``UploadVerificationError``, ``FileQuarantinedError`` ...).
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import BinaryIO, cast

from tl_core.files.queries import FileInfo
from tl_core.files.service import AttachFile, FileResult, RegisterUpload, UploadTicket
from tl_core.services.errors import RecordNotFoundError, UnknownFileError, UploadVerificationError

from tl_api.client.base import ApiClientBase, quote

CHUNK = 1024 * 1024
DEFAULT_ACTOR = (
    "user:client"  # sent as `actor` in commands; the server replaces it with the token's
)


_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]")
MAX_NAME = 120


def safe_filename(name: str) -> str:
    """A name that is safe to create in a directory of ours, whatever the uploader called the file.

    Only the last path part is kept (``../x`` and ``/etc/x`` give ``x``); every character outside
    letters, digits, ``._ -`` becomes ``_`` (a NUL, a control character, a separator); leading
    dots, dashes and spaces go (no hidden file, no option-looking name); the length is bounded and
    the extension kept. A name with nothing left is ``download``.
    """
    last = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _UNSAFE_NAME.sub("_", last).lstrip(".- ").rstrip(" .")
    if not cleaned:
        return "download"
    if len(cleaned) > MAX_NAME:
        stem, dot, ext = cleaned.rpartition(".")
        keep = ext[:16] if dot else ""
        cleaned = (stem if dot else cleaned)[: MAX_NAME - len(keep) - 1] + (
            f".{keep}" if keep else ""
        )
    return cleaned


class _Counting:
    """A write-only file that hashes and counts what passes through it."""

    def __init__(self, out: BinaryIO) -> None:
        self._out = out
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> int:
        self._out.write(data)
        self.digest.update(data)
        self.size += len(data)
        return len(data)


def _create_new(directory: Path, name: str) -> tuple[Path, int]:
    """Create ``name`` in ``directory`` (mode 0600), or ``stem-1.ext``, ``stem-2.ext``... when it
    exists: an earlier download is never overwritten, and a link planted at the name is not
    followed."""
    stem, dot, ext = name.rpartition(".")
    base, suffix = (stem, f".{ext}") if dot and stem else (name, "")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for n in range(0, 10_000):
        candidate = directory / (f"{base}{suffix}" if n == 0 else f"{base}-{n}{suffix}")
        try:
            return candidate, os.open(candidate, flags, 0o600)
        except FileExistsError:
            continue
    raise FileExistsError(f"no free name for {name!r} in {directory}")


def save_download(dest_dir: Path, info: FileInfo, fill: Callable[[BinaryIO], object]) -> Path:
    """Write a file's bytes into ``dest_dir`` and return the path; verified before it returns.

    The name is ``safe_filename(info.filename)`` in ``dest_dir`` itself, mode 0600, never an
    existing file (a numeric suffix is added). ``fill`` writes the bytes into the file it is given.
    The size and SHA-256 of what was written must be those of ``info``: otherwise the partial file
    is deleted and ``UploadVerificationError`` is raised, so a caller never holds bytes that are not
    the ones the ledger recorded.
    """
    directory = dest_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path, fd = _create_new(directory, safe_filename(info.filename))
    assert path.parent == directory  # the name has no separator left
    try:
        with os.fdopen(fd, "wb") as handle:
            counted = _Counting(handle)
            fill(cast(BinaryIO, counted))  # the fill only writes
        if counted.size != info.size or counted.digest.hexdigest() != info.sha256:
            raise UploadVerificationError(
                f"the downloaded bytes of file {info.file_id!r} do not match its recorded size "
                "and SHA-256"
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


class FilesApi(ApiClientBase):
    #: Scope of each file seen through :meth:`list_record_files` (a file id alone names no scope).
    _file_scopes: dict[str, str]

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

    def list_record_files(self, record_id: str) -> list[FileInfo]:
        """The current files of a record the caller may read: available, not superseded.

        A record that is missing or hidden has none (``[]``), as the embedded client answers. The
        scope of each file is kept for :meth:`fetch_file`.
        """
        try:
            scope = str(self._get_json(f"/records/{quote(record_id)}")["scope"])
        except RecordNotFoundError:
            return []
        found = self.list_files(scope, record_id, current_only=True)
        scopes = self.__dict__.setdefault("_file_scopes", {})
        scopes.update({info.file_id: info.scope for info in found})
        return found

    def fetch_file(self, file_id: str, dest_dir: Path) -> Path:
        """Download a file listed by :meth:`list_record_files` into ``dest_dir``; see
        ``save_download`` for the name, the mode and the check made before it returns.

        The bytes come through the existing file route (``GET /files/{id}/content``). A file the
        caller may not read, one that does not exist and one never listed raise the same
        ``UnknownFileError``.
        """
        missing = UnknownFileError(f"no file {file_id!r}")
        scope = self.__dict__.get("_file_scopes", {}).get(file_id)
        if scope is None:
            raise missing
        try:
            info = self.get_file_info(scope, file_id)
            return save_download(dest_dir, info, lambda out: self.download_to(scope, file_id, out))
        except (UnknownFileError, RecordNotFoundError):
            raise missing from None
        except ValueError as exc:  # the server's own digest header disagreed with the bytes
            raise UploadVerificationError(str(exc)) from exc

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
