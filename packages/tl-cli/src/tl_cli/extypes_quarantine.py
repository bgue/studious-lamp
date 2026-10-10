"""The `tl types quarantine` group: what the extension type registry refused (P0-I8-T26).

`ls` is the quarantine report: package versions that failed validation, registered versions whose
files were edited (a conflict), and records whose stored body failed verification on read.
`recheck` verifies a quarantined body again and lifts the quarantine when the object is sound.
Each subcommand makes one call into `tl_core.extypes` and prints.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from tl_adapters.objectstore import make_object_store
from tl_adapters.sqlite.uow import open_uow
from tl_core.extypes import body, registry
from tl_core.extypes.body import BodyQuarantineEntry
from tl_core.extypes.registry import QuarantineEntry
from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork

app = typer.Typer(
    help="What the registry refused: list it, recheck a damaged body.", no_args_is_help=True
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service or concurrency failure into `error:` on stderr, exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))


def _factory(db: Path) -> registry.UowFactory:
    def open_one(readonly: bool = False) -> AbstractContextManager[UnitOfWork]:
        return open_uow(db, readonly=readonly)

    return open_one


def type_lines(entry: QuarantineEntry) -> list[str]:
    """The lines for one refused package version.

    First ``type <type_ref> quarantined`` or, when ``entry.registered_hash`` is not ``None`` (a
    registered version whose files changed), ``type <type_ref> conflict (registered
    <registered_hash[:12]>, files <content_hash[:12]>)``. Then one line per issue of
    ``entry.report``: two spaces, ``issue.kind``, a space, ``issue.path`` (``-`` when ``None``), a
    colon, a space, ``issue.detail``.
    """
    if entry.registered_hash is None:
        lines = [f"type {entry.type_ref} quarantined"]
    else:
        kept = entry.registered_hash[:12]
        files = entry.content_hash[:12]
        lines = [f"type {entry.type_ref} conflict (registered {kept}, files {files})"]
    for issue in entry.report:
        path = "-" if issue.path is None else issue.path
        lines.append(f"  {issue.kind} {path}: {issue.detail}")
    return lines


def body_line(entry: BodyQuarantineEntry) -> str:
    """``body <record_id> <type_name> <reason>`` (single spaces)."""
    return f"body {entry.record_id} {entry.type_name} {entry.reason}"


@app.command("ls")
def ls(ctx: typer.Context) -> None:
    """Print the quarantine report; `nothing quarantined` when it is empty."""
    db: Path = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        types = registry.list_quarantined(uow.conn())
        bodies = body.list_body_quarantine(uow.conn())
    if not types and not bodies:
        typer.echo("nothing quarantined")
        return
    for entry in types:
        for line in type_lines(entry):
            typer.echo(line)
    for body_entry in bodies:
        typer.echo(body_line(body_entry))


@app.command("recheck")
def recheck(
    ctx: typer.Context,
    record_id: Annotated[str, typer.Argument(help="Id of the record whose body to verify.")],
) -> None:
    """Verify a record's stored body again; lift its quarantine when the object is sound."""
    db: Path = ctx.obj
    try:
        store = make_object_store()
    except ValueError as exc:
        _fail(str(exc))
    with _service_errors():
        sound = body.recheck_body(_factory(db), store, stream_id=record_id)
    if sound:
        typer.echo(f"restored {record_id}")
        return
    typer.echo(f"still failing {record_id}")
    raise typer.Exit(code=1)
