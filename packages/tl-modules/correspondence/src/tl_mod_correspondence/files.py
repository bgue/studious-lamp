"""The module writes the rendition of an issued letter into the file service.

A command handler has the signature ``(uow, command)`` and no object store. The process says which
file service to use once, at start-up (the API server, the CLI, the MCP server and the embedded TUI
configure the documents module's derivation store; this module reads the same one, so there is a
single place to configure). A process with none answers ``LetterRenderError`` the first time a
letter must be stored. Files written here go through the service's ``by_module`` path: the upload
guard of an item refuses the slot ``rendition`` to a person.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_core.uow import UnitOfWork
from tl_mod_documents.derivation import store

from tl_mod_correspondence.errors import InvalidItemError, LetterRenderError
from tl_mod_correspondence.names import SLOT_RENDITION

PDF_TYPE = "application/pdf"


@dataclass(frozen=True)
class StoredFile:
    file_id: str
    sha256: str
    size: int


def file_service() -> FileService:
    """The configured file service, or ``LetterRenderError``."""
    found = store.configured()
    if found is None:
        raise LetterRenderError(
            "this process has no file service, so the letter cannot be stored; the server or "
            "command that runs it must configure one (tl_mod_documents.derivation.store.configure)"
        )
    return found


def store_file(
    uow: UnitOfWork,
    *,
    actor: str,
    source: str,
    scope: str,
    record_id: str,
    slot: str,
    filename: str,
    content_type: str,
    data: bytes,
    correlation_id: str,
    by_module: bool,
) -> StoredFile:
    """Store ``data`` in a slot of the item and return its file id.

    ``by_module=True`` is the module writing a slot only it may fill (``rendition``, ``message``).
    ``by_module=False`` goes the way a person's upload goes, so the item's upload guard
    (``guards.item_upload``: the slot and the item's state) and the scan apply.
    """
    files = file_service()
    digest = hashlib.sha256(data).hexdigest()
    base = {"actor": actor, "source": source, "scope": scope, "correlation_id": correlation_id}
    ticket = files.register_upload(
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
        by_module=by_module,
    )
    done = files.complete_upload(
        uow,
        CompleteUpload(**base, upload_id=ticket.upload_id),
        io.BytesIO(data),
        by_module=by_module,
    )
    if done.status == "rejected":  # the scan said no: the whole command is undone
        raise InvalidItemError(f"the file {filename!r} was rejected by the scan")
    return StoredFile(file_id=done.file_id, sha256=digest, size=len(data))


def write_rendition(
    uow: UnitOfWork,
    *,
    actor: str,
    source: str,
    scope: str,
    record_id: str,
    filename: str,
    data: bytes,
    correlation_id: str,
) -> StoredFile:
    """Store ``data`` (a PDF) in the slot ``rendition`` of the item and return its file id."""
    return store_file(
        uow,
        actor=actor,
        source=source,
        scope=scope,
        record_id=record_id,
        slot=SLOT_RENDITION,
        filename=filename,
        content_type=PDF_TYPE,
        data=data,
        correlation_id=correlation_id,
        by_module=True,
    )
