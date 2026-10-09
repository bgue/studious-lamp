"""The `tl record` group: create, show, and void core.Record rows in a project scope (brief 5.1)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import ConcurrencyError, canonical_json
from tl_core.services.commands import CreateRecord, VoidRecord
from tl_core.services.errors import ServiceError
from tl_core.services.queries import get_record
from tl_core.services.records import handle_create_record, handle_void_record

app = typer.Typer(help="Create, show, and void records.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_SHOWN_FIELDS = (
    "id",
    "key",
    "type",
    "scope",
    "title",
    "description",
    "status",
    "version",
    "voided",
    "conformance",
    "created_at",
    "updated_at",
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service or concurrency failure into `error: <message>` on stderr and exit 1."""
    try:
        yield
    except (ServiceError, ConcurrencyError) as exc:
        _fail(str(exc))


def _show_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@app.command("create")
def create(
    ctx: typer.Context,
    project: Annotated[
        str,
        typer.Option("--project", help="Project ID; the record goes in scope project:<ID>."),
    ],
    key: Annotated[
        str,
        typer.Option("--key", help="Record key, unique in the project. Required until numbering."),
    ],
    title: Annotated[str, typer.Option("--title", help="Record title.")],
    description: Annotated[
        str | None, typer.Option("--description", help="Optional description.")
    ] = None,
    record_type: Annotated[
        str, typer.Option("--type", help="Record type; only core.Record exists.")
    ] = "core.Record",
    actor: Annotated[str, typer.Option("--actor", help="Actor recorded on events.")] = (
        _DEFAULT_ACTOR
    ),
) -> None:
    """Create a record."""
    db: Path = ctx.obj
    with _service_errors(), open_uow(db) as uow:
        result = handle_create_record(
            uow,
            CreateRecord(
                actor=actor,
                source="cli",
                scope=f"project:{project}",
                record_type=record_type,
                title=title,
                description=description,
                key=key,
            ),
        )
    typer.echo(f"created {result.stream_id}")
    typer.echo(f"key {result.key}")
    typer.echo(f"version {result.version}")


@app.command("show")
def show(
    ctx: typer.Context,
    project: Annotated[
        str,
        typer.Option("--project", help="Project ID; reads scope project:<ID>."),
    ],
    key: Annotated[str, typer.Argument(help="Record key.")],
) -> None:
    """Show the current state of a record."""
    db: Path = ctx.obj
    with open_uow(db, readonly=True) as uow:
        row = get_record(uow, f"project:{project}", key)
    if row is None:
        _fail(f"no record with key {key!r} in project {project!r}")
    for name in _SHOWN_FIELDS:
        typer.echo(f"{name}: {_show_value(row[name])}")
    typer.echo(f"psets: {canonical_json(row['psets'])}")


@app.command("void")
def void(
    ctx: typer.Context,
    project: Annotated[
        str,
        typer.Option("--project", help="Project ID; the record is in scope project:<ID>."),
    ],
    key: Annotated[str, typer.Argument(help="Record key.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the record is voided.")],
    actor: Annotated[str, typer.Option("--actor", help="Actor recorded on events.")] = (
        _DEFAULT_ACTOR
    ),
) -> None:
    """Void a record. Its history stays in the ledger."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        current = get_record(uow, scope, key)
        if current is None:
            _fail(f"no record with key {key!r} in project {project!r}")
        result = handle_void_record(
            uow,
            VoidRecord(
                actor=actor,
                source="cli",
                scope=scope,
                stream_id=current["id"],
                expected_version=current["version"],
                reason=reason,
            ),
        )
    typer.echo(f"voided {result.stream_id}")
    typer.echo(f"version {result.version}")
