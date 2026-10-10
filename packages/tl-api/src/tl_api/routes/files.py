"""File routes: the upload flow, listing, and downloads over ``tl_core.files`` (brief 20).

The routes translate HTTP to ``FileService`` calls and nothing more; hash and size verification,
dedupe, quarantine and the uploader-only rule for quarantined files all live in the service.
What belongs here is the HTTP side of the security rules:

* A download is always ``application/octet-stream`` with ``Content-Disposition: attachment`` and
  ``X-Content-Type-Options: nosniff``. The declared content type is client-typed, so it is never
  reflected as a renderable type (it stays in the JSON metadata).
* A quarantined file is served to its uploader only: ``open_file`` is called with the token's
  actor, and its refusal becomes 403.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Iterator
from typing import Annotated, BinaryIO, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from tl_core.files.queries import FileInfo, get_file, list_files
from tl_core.files.service import (
    AttachFile,
    CompleteUpload,
    FileResult,
    FileService,
    RegisterUpload,
    UploadTicket,
)
from tl_core.services.errors import FileTooLargeError

from tl_api.auth import guard
from tl_api.commands import request_model
from tl_api.context import ApiContext, get_ctx
from tl_api.errors import ApiError

router = APIRouter(tags=["files"])

Ctx = Annotated[ApiContext, Depends(get_ctx)]
ScopeParam = Annotated[str, Query(description="`company` or `project:<id>`.")]

CHUNK = 1024 * 1024
SPOOL_IN_MEMORY = 8 * 1024 * 1024  # an upload larger than this waits on disk while it arrives

RegisterUploadBody = request_model(RegisterUpload, "RegisterUpload")
AttachFileBody = request_model(AttachFile, "AttachFile")

_BINARY = {"type": "string", "format": "binary"}
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")


def content_disposition(filename: str) -> str:
    """``attachment`` with an ASCII fallback name and the real name in ``filename*`` (RFC 6266)."""
    fallback = _UNSAFE.sub("_", filename).strip(" .") or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def download_headers(info: FileInfo) -> dict[str, str]:
    """Headers every download carries (O2). The body type is always octet-stream."""
    return {
        "Content-Disposition": content_disposition(info.filename),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, no-store",
        "Content-Length": str(info.size),
        "X-Content-SHA256": info.sha256,
    }


def _service(ctx: ApiContext) -> FileService:
    if ctx.files is None:
        raise ApiError(503, "unavailable", "file storage is not configured on this server")
    return ctx.files


@router.post("/uploads", operation_id="register_upload", status_code=200)
def register_upload(
    ctx: Ctx,
    body: RegisterUploadBody,  # pyright: ignore[reportInvalidTypeForm]
    actor: Annotated[str, Depends(guard("file.upload", changes_records=True))],
) -> UploadTicket:
    """Announce a file: the answer is a dedupe hit (`exists`) or an upload id to send bytes to."""
    service = _service(ctx)
    command = RegisterUpload(**body.model_dump(), actor=actor)  # pyright: ignore[reportAttributeAccessIssue]
    with ctx.backend(False) as uow:
        return service.register_upload(uow, command)


@router.put("/uploads/{upload_id}/content", operation_id="upload_content")
async def upload_content(
    request: Request,
    ctx: Ctx,
    upload_id: str,
    scope: ScopeParam,
    actor: Annotated[str, Depends(guard("file.upload", changes_records=True))],
) -> FileResult:
    """Send the bytes (the request body) and complete the upload in one call.

    The server verifies size and SHA-256 against what was registered, stores the object, and
    attaches the file. Bodies over the server's upload limit are refused with 413.
    """
    service = _service(ctx)
    limit = ctx.settings.max_upload_bytes
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_IN_MEMORY)  # noqa: SIM115
    try:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > limit:
                raise FileTooLargeError(
                    f"the upload is larger than the server limit of {limit} bytes"
                )
            await run_in_threadpool(spool.write, chunk)
        spool.seek(0)

        def complete() -> FileResult:
            command = CompleteUpload(actor=actor, source="api", scope=scope, upload_id=upload_id)
            with ctx.backend(False) as uow:
                return service.complete_upload(uow, command, cast(BinaryIO, spool))

        return await run_in_threadpool(complete)
    finally:
        spool.close()


@router.post("/uploads/{upload_id}/complete", operation_id="complete_upload")
def complete_upload(
    ctx: Ctx,
    upload_id: str,
    scope: ScopeParam,
    actor: Annotated[str, Depends(guard("file.upload", changes_records=True))],
) -> FileResult:
    """Complete an upload whose bytes need no sending: a dedupe hit, or bytes already staged."""
    service = _service(ctx)
    command = CompleteUpload(actor=actor, source="api", scope=scope, upload_id=upload_id)
    with ctx.backend(False) as uow:
        return service.complete_upload(uow, command)


@router.post("/files/attach", operation_id="attach_file")
def attach_file(
    ctx: Ctx,
    body: AttachFileBody,  # pyright: ignore[reportInvalidTypeForm]
    actor: Annotated[str, Depends(guard("file.upload", changes_records=True))],
) -> FileResult:
    """Attach bytes this scope already holds to another record or slot, without an upload."""
    service = _service(ctx)
    command = AttachFile(**body.model_dump(), actor=actor)  # pyright: ignore[reportAttributeAccessIssue]
    with ctx.backend(False) as uow:
        return service.attach_file(uow, command)


@router.get("/records/{record_id}/files", operation_id="list_record_files")
def list_record_files(
    ctx: Ctx,
    record_id: str,
    scope: ScopeParam,
    actor: Annotated[str, Depends(guard("file.read"))],
    slot: Annotated[str | None, Query()] = None,
    current_only: Annotated[bool, Query(description="Only the current file of each slot.")] = False,
) -> list[FileInfo]:
    """The files of a record (metadata only), including quarantined and superseded ones."""
    with ctx.backend(True) as uow:
        return list_files(uow, scope, record_id, slot=slot, current_only=current_only)


@router.get("/files/{file_id}", operation_id="get_file_info")
def get_file_info(
    ctx: Ctx,
    file_id: str,
    scope: ScopeParam,
    actor: Annotated[str, Depends(guard("file.read"))],
) -> FileInfo:
    """One file's metadata."""
    with ctx.backend(True) as uow:
        return get_file(uow, scope, file_id)


def _chunks(data: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := data.read(CHUNK):
            yield chunk
    finally:
        data.close()


@router.get(
    "/files/{file_id}/content",
    operation_id="download_file",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        }
    },
)
def download_file(
    ctx: Ctx,
    file_id: str,
    scope: ScopeParam,
    actor: Annotated[str, Depends(guard("file.read"))],
) -> StreamingResponse:
    """The file's bytes, as an attachment. A quarantined file is served to its uploader only."""
    service = _service(ctx)
    with ctx.backend(True) as uow:
        opened = service.open_file(uow, scope, file_id, actor=actor)
    return StreamingResponse(
        _chunks(opened.data),
        media_type="application/octet-stream",
        headers=download_headers(opened.info),
    )
