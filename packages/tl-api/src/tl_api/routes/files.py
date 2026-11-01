"""File routes: the upload flow, listing, and downloads over ``tl_core.files`` (brief 20).

The routes translate HTTP to ``FileService`` calls and nothing more; hash and size verification,
dedupe, quarantine and the uploader-only rule for quarantined files all live in the service.
What belongs here is the HTTP side of the security rules:

* A download is always ``application/octet-stream`` with ``Content-Disposition: attachment`` and
  ``X-Content-Type-Options: nosniff``. The declared content type is client-typed, so it is never
  reflected as a renderable type (it stays in the JSON metadata).
* A quarantined file is served to its uploader only: ``open_file`` is called with the token's
  actor, and its refusal becomes 403.
* Page 1 of a PDF (``page1.png``) opens the file under the viewer first; only then does it look at
  the size, the ``%PDF-`` header and the picture cache, and the bytes of a file the viewer may not
  see never reach the renderer (P2-WEB1-S3).
"""

from __future__ import annotations

import re
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, BinaryIO, cast
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse
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
from tl_api.errors import ApiError, ErrorBody
from tl_api.preview import cache, render

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


#: One text for every reason a page 1 cannot be drawn (not a PDF, too big, broken, timed out).
NO_PREVIEW_TEXT = "there is no preview for this file"
#: At most this many renders run at once in this process; a further request is told to retry.
RENDER_SLOT_COUNT = 2
#: Taken without waiting; a cache hit never takes one.
RENDER_SLOTS = threading.BoundedSemaphore(RENDER_SLOT_COUNT)


def _no_preview() -> ApiError:
    return ApiError(404, "no_preview", NO_PREVIEW_TEXT)


def _picture(path: Path) -> Response | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return Response(
        data,
        media_type="image/png",
        headers={
            "Cache-Control": "private",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


def _draw(opened_data: BinaryIO, head: bytes, sha256: str, root: Path) -> Response:
    """Copy the (already opened, already checked) bytes to a private temp file and render."""
    with tempfile.TemporaryDirectory(prefix="tl-page1-") as folder:
        target = Path(folder) / "document.pdf"
        with open(target, "wb") as out:
            out.write(head)
            left = render.MAX_BYTES - len(head) + 1  # one byte more than allowed shows an overrun
            while left > 0 and (chunk := opened_data.read(min(CHUNK, left))):
                out.write(chunk)
                left -= len(chunk)
        if left <= 0:
            raise _no_preview()
        done = render.render_first_page(target, sha256, root=root)
    picture = _picture(done.png) if done.state == "ok" and done.png is not None else None
    if picture is None:
        raise _no_preview()
    return picture


@router.get(
    "/files/{file_id}/page1.png",
    operation_id="get_file_page1",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
        404: {"model": ErrorBody, "description": "Unknown, hidden or not renderable."},
        503: {"model": ErrorBody, "description": "Too many renders at once; see `Retry-After`."},
    },
)
def get_file_page1(
    ctx: Ctx,
    file_id: str,
    scope: ScopeParam,
    actor: Annotated[str, Depends(guard("file.read"))],
) -> Response:
    """Page 1 of a PDF file as a PNG.

    The file is opened under the viewer first (hidden or unknown is the 404 of the download; a
    quarantined file is its uploader's only). Then the size and ``%PDF-`` checks and the cache
    lookup by content hash; a miss renders in a bounded child process, at most two at once.
    """
    service = _service(ctx)
    with ctx.backend(True) as uow:
        opened = service.open_file(uow, scope, file_id, actor=actor)
    try:
        info = opened.info
        if info.size > render.MAX_BYTES:
            raise _no_preview()
        head = opened.data.read(len(render.HEADER))
        if head != render.HEADER:
            raise _no_preview()
        root = cache.cache_dir()
        hit = cache.lookup(root, info.sha256)
        if hit is not None and (picture := _picture(hit)) is not None:
            return picture
        if not RENDER_SLOTS.acquire(blocking=False):
            body = ErrorBody(error="preview_busy", message="too many previews are being drawn")
            return JSONResponse(
                body.model_dump(mode="json", exclude_none=True),
                status_code=503,
                headers={"Retry-After": "2"},
            )
        try:
            return _draw(opened.data, head, info.sha256, root)
        finally:
            RENDER_SLOTS.release()
    finally:
        opened.data.close()
