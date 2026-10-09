"""The `tl file` group: put, get, list and reconcile files (brief 20).

Each subcommand parses options, makes one call into `tl_core.files` and prints. No rules live here.
Storage comes from the environment (`make_object_store`: TL_OBJECT_STORE, TL_OBJECT_ROOT,
TL_OBJECT_SECRET or TL_ENV=dev); the ledger from `--db` / TL_DB like every other group.
"""

from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.objectstore import make_object_store, object_secret
from tl_adapters.sqlite.uow import open_uow
from tl_core.files.queries import list_files
from tl_core.files.service import CompleteUpload, FileService, RegisterUpload
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.services.queries import get_record

from tl_cli import file_reconcile

app = typer.Typer(help="Attach, fetch, list and reconcile files.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_CHUNK = 1024 * 1024


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency, validation or storage-setup failure into `error:`, exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _service() -> FileService:
    """The upload service on the configured store (fails with `error:` when unconfigured)."""
    try:
        return FileService(make_object_store(), secret=object_secret())
    except ValueError as exc:
        _fail(str(exc))


app.command("reconcile")(file_reconcile.reconcile)


@app.command("put")
def put(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="File to attach.", exists=True, dir_okay=False)],
    project: Annotated[str, typer.Option("--project", help="Project ID (scope project:<ID>).")],
    record: Annotated[str, typer.Option("--record", help="Key of the record to attach to.")],
    slot: Annotated[
        str | None, typer.Option("--slot", help="Record file slot; omit for a generic attachment.")
    ] = None,
    content_type: Annotated[
        str | None,
        typer.Option("--content-type", help="Media type. Default: guessed from the file name."),
    ] = None,
    actor: Annotated[str, typer.Option("--actor", help="Actor recorded on events.")] = (
        _DEFAULT_ACTOR
    ),
) -> None:
    """Attach a file to a record: hash it, upload it (or dedupe) and print the result."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    media = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    size = path.stat().st_size
    service = _service()
    with _service_errors(), open_uow(db) as uow:
        found = get_record(uow, scope, record)
        if found is None:
            _fail(f"no record with key {record!r} in project {project!r}")
        ticket = service.register_upload(
            uow,
            RegisterUpload(
                actor=actor,
                source="cli",
                scope=scope,
                record_id=found["id"],
                slot=slot,
                filename=path.name,
                content_type=media,
                size=size,
                sha256=digest.hexdigest(),
            ),
        )
        complete = CompleteUpload(
            actor=actor, source="cli", scope=scope, upload_id=ticket.upload_id
        )
        if ticket.exists:
            result = service.complete_upload(uow, complete)
        else:
            with path.open("rb") as source_file:
                result = service.complete_upload(uow, complete, source_file)
    typer.echo(f"file {result.file_id}")
    typer.echo(f"slot {result.slot or '-'}")
    typer.echo(f"revision {result.revision}")
    typer.echo(f"status {result.status}")
    typer.echo(f"size {result.size}")
    typer.echo(f"sha256 {result.sha256}")
    typer.echo(f"deduplicated {'true' if result.deduplicated else 'false'}")
    if result.already_attached:
        typer.echo("already attached")


@app.command("get")
def get(
    ctx: typer.Context,
    file_id: Annotated[str, typer.Argument(help="File ID (from `tl file ls`).")],
    project: Annotated[str, typer.Option("--project", help="Project ID (scope project:<ID>).")],
    out: Annotated[Path, typer.Option("--out", help="Where to write the bytes.")],
    force: Annotated[bool, typer.Option("--force", help="Overwrite --out if it exists.")] = False,
    actor: Annotated[str, typer.Option("--actor", help="Actor reading the file.")] = (
        _DEFAULT_ACTOR
    ),
) -> None:
    """Write a file's bytes to a path, checking them against the recorded SHA-256."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    if out.exists() and not force:
        _fail(f"{out} already exists; use --force to overwrite it")
    service = _service()
    with _service_errors(), open_uow(db, readonly=True) as uow:
        opened = service.open_file(uow, scope, file_id, actor=actor)
    digest = hashlib.sha256()
    count = 0
    try:
        with out.open("wb") as sink:
            while chunk := opened.data.read(_CHUNK):
                digest.update(chunk)
                count += len(chunk)
                sink.write(chunk)
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    finally:
        opened.data.close()
    if digest.hexdigest() != opened.info.sha256 or count != opened.info.size:
        out.unlink(missing_ok=True)
        _fail(
            f"the stored object for {file_id} does not match its recorded SHA-256; "
            "see the object-store reconciliation runbook"
        )
    typer.echo(f"wrote {out}")
    typer.echo(f"size {count}")
    typer.echo(f"sha256 {digest.hexdigest()}")


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID (scope project:<ID>).")],
    record: Annotated[str, typer.Option("--record", help="Key of the record.")],
    slot: Annotated[str | None, typer.Option("--slot", help="Only this slot.")] = None,
    all_files: Annotated[
        bool,
        typer.Option("--all", help="Include superseded, quarantined and rejected files."),
    ] = False,
) -> None:
    """List a record's files: the current file per slot, or every file with --all."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = get_record(uow, scope, record)
        if found is None:
            _fail(f"no record with key {record!r} in project {project!r}")
        files = list_files(uow, scope, found["id"], slot=slot, current_only=not all_files)
    for info in files:
        status = "superseded" if info.superseded_by else info.status
        fields = (info.file_id, info.slot or "-", str(info.revision), status, str(info.size))
        typer.echo("\t".join((*fields, info.filename)))
