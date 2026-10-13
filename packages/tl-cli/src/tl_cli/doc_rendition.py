"""The `tl doc rendition` group: add a file to a revision as a controlled rendition, and list them.

A rendition is a file of a revision in one of its four kinds: `native`, `pdf`, `markup`, `signed`.
Adding one is two steps that the module keeps apart: the upload (the file service hashes, scans and
stores the bytes in the revision's slot of that name) and `AttachRendition` (the module registers
the available file as the revision's rendition and supersedes an older native or PDF). The commands
here do both. What a revision accepts depends on its state; the module says so. Replacing a signed
copy is an admin's act (ADR-0011).
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_adapters.objectstore import make_object_store, object_secret
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_mod_documents import registry
from tl_mod_documents.handlers.renditions import (
    AttachRendition,
    ReplaceSignedRendition,
    handle_attach_rendition,
    handle_replace_signed_rendition,
)

from tl_cli.doc import (
    _DEFAULT_ACTOR,
    _Actor,
    _fail,
    _Project,
    _Reason,
    _service_errors,
)
from tl_cli.doc_rev import _Code, _Number, _revision
from tl_cli.session import require_admin

app = typer.Typer(help="Add, replace and list the renditions of a revision.", no_args_is_help=True)

KINDS = ("native", "pdf", "markup", "signed")
_CHUNK = 1024 * 1024
_File = Annotated[Path, typer.Argument(help="The file to add.", exists=True, dir_okay=False)]
_Pages = Annotated[int | None, typer.Option("--pages", min=0, help="Page count, if known.")]
_ContentType = Annotated[
    str | None, typer.Option("--content-type", help="Default: guessed from the file name.")
]


def _upload(
    db: DbTarget,
    scope: str,
    actor: str,
    record_id: str,
    slot: str,
    path: Path,
    content_type: str | None,
) -> str:
    """Upload ``path`` into the ``slot`` of the revision record; returns the file id.

    The bytes are hashed first, registered (a file the store already holds is not sent again) and
    completed. A storage setup problem exits `error: ...`.
    """
    media = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    try:
        service = FileService(make_object_store(), secret=object_secret())
    except ValueError as exc:
        _fail(str(exc))
    with _service_errors(), open_uow(db) as uow:
        ticket = service.register_upload(
            uow,
            RegisterUpload(
                actor=actor,
                source="cli",
                scope=scope,
                record_id=record_id,
                slot=slot,
                filename=path.name,
                content_type=media,
                size=path.stat().st_size,
                sha256=digest.hexdigest(),
            ),
        )
        complete = CompleteUpload(
            actor=actor, source="cli", scope=scope, upload_id=ticket.upload_id
        )
        if ticket.exists:
            done = service.complete_upload(uow, complete)
        else:
            with path.open("rb") as source_file:
                done = service.complete_upload(uow, complete, source_file)
    return done.file_id


@app.command("add")
def add(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    path: _File,
    project: _Project,
    kind: Annotated[str, typer.Option("--kind", help="native, pdf, markup or signed.")],
    pages: _Pages = None,
    content_type: _ContentType = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Upload a file into a revision and register it as a rendition of that kind."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    if kind not in KINDS:
        _fail(f"kind must be one of {', '.join(KINDS)}")
    with _service_errors(), open_uow(db, readonly=True) as uow:
        rev = _revision(uow, scope, project, number, code)
    file_id = _upload(db, scope, actor, rev.id, kind, path, content_type)
    with _service_errors(), open_uow(db) as uow:
        made = handle_attach_rendition(
            uow,
            AttachRendition(
                actor=actor,
                source="cli",
                scope=scope,
                revision_id=rev.id,
                file_id=file_id,
                page_count=pages,
            ),
        )
    typer.echo(f"attached {kind} {path.name} to {number}@{code}")
    typer.echo(f"rendition {made.stream_id}")


@app.command("replace-signed")
def replace_signed(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    path: _File,
    project: _Project,
    reason: _Reason,
    pages: _Pages = None,
    content_type: _ContentType = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Replace the signed copy of a revision by another file (admin). The reason is kept."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_admin(db)
    with _service_errors(), open_uow(db, readonly=True) as uow:
        rev = _revision(uow, scope, project, number, code)
    file_id = _upload(db, scope, actor, rev.id, "signed", path, content_type)
    with _service_errors(), open_uow(db) as uow:
        made = handle_replace_signed_rendition(
            uow,
            ReplaceSignedRendition(
                actor=actor,
                source="cli",
                scope=scope,
                revision_id=rev.id,
                file_id=file_id,
                page_count=pages,
                reason=reason,
            ),
        )
    typer.echo(f"replaced the signed copy of {number}@{code} with {path.name}")
    typer.echo(f"rendition {made.stream_id}")


@app.command("ls")
def ls(
    ctx: typer.Context,
    number: _Number,
    code: _Code,
    project: _Project,
    all_: Annotated[
        bool, typer.Option("--all", help="Include renditions that were replaced.")
    ] = False,
) -> None:
    """List a revision's renditions: kind, file name, size, pages, sha256 (first 12), state."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        rev = _revision(uow, scope, project, number, code)
        rows = registry.renditions_of(uow.conn(), rev.id, current_only=not all_)
    for row in rows:
        pages = "-p" if row.page_count is None else f"{row.page_count}p"
        state = "current" if row.is_current else "replaced"
        fields = [row.kind, row.filename, f"{row.size}B", pages, row.sha256[:12], state]
        typer.echo("  ".join(fields))
