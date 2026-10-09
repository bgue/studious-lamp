"""The `tl file` group: put, get, list and reconcile files (brief 20).

Each subcommand parses options, makes one call into `tl_core.files` and prints. No rules live here.
Storage comes from the environment (`make_object_store`: TL_OBJECT_STORE, TL_OBJECT_ROOT,
TL_OBJECT_SECRET or TL_ENV=dev); the ledger from `--db` / TL_DB like every other group.

STUB (P0-I4-T24): the helpers, options and registration are final; the three command bodies
(`put`, `get`, `ls`) marked `raise NotImplementedError` are the ticket. `reconcile` is T25's, in
`file_reconcile.py`. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.objectstore import make_object_store, object_secret
from tl_core.files.service import FileService
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError

from tl_cli import file_reconcile

app = typer.Typer(help="Attach, fetch, list and reconcile files.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"


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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError
