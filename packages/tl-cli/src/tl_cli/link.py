"""The `tl link` group: create, maintain and read links between records (brief 7).

Each subcommand parses options, makes one call into `tl_core.services`, and prints. Rules (relation
vocabulary, lifecycle, scope) live in the services. Records are named by key; links by the id that
`add`, `suggest` and `list` print.

STUB (P0-I3-T02b): the helpers, the options and `add`, `suggest` are final; the functions marked
`raise NotImplementedError` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.links.expected import ExpectedLinkError
from tl_core.services.commands import CommandResult
from tl_core.services.errors import ServiceError
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_schema.compile import SchemaCompileError
from tl_schema.registry import PackageError

app = typer.Typer(help="Create, maintain and show links.", no_args_is_help=True)

_DEFAULT_ACTOR = "user:dev"
_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Actor = Annotated[str, typer.Option("--actor", help="Actor recorded on events.")]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn a service, concurrency or input-validation failure into `error:` on stderr, exit 1."""
    try:
        yield
    except (
        ServiceError,
        ConcurrencyError,
        PackageError,
        SchemaCompileError,
        ExpectedLinkError,
    ) as exc:
        _fail(str(exc))
    except ValidationError as exc:
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))


def _record(uow: UnitOfWork, scope: str, project: str, key: str) -> dict[str, object]:
    row = get_record(uow, scope, key)
    if row is None:
        _fail(f"no record with key {key!r} in project {project!r}")
    return row


def _create(
    ctx: typer.Context,
    project: str,
    from_key: str,
    to_key: str,
    relation: str | None,
    pin: str | None,
    note: str | None,
    actor: str,
    confidence: float | None,
) -> None:
    raise NotImplementedError


@app.command("add")
def add(
    ctx: typer.Context,
    project: _Project,
    from_key: Annotated[str, typer.Argument(help="Key of the record the link starts at.")],
    to_key: Annotated[str, typer.Argument(help="Key of the record it points to.")],
    relation: Annotated[
        str | None, typer.Option("--relation", help="Relation code; default by record types.")
    ] = None,
    pin: Annotated[
        str | None, typer.Option("--pin", help="Revision to pin; default floats.")
    ] = None,
    note: Annotated[str | None, typer.Option("--note", help="Optional note.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Link FROM_KEY to TO_KEY (an active link)."""
    _create(ctx, project, from_key, to_key, relation, pin, note, actor, None)


@app.command("suggest")
def suggest(
    ctx: typer.Context,
    project: _Project,
    from_key: Annotated[str, typer.Argument(help="Key of the record the link starts at.")],
    to_key: Annotated[str, typer.Argument(help="Key of the record it points to.")],
    confidence: Annotated[
        float, typer.Option("--confidence", min=0, max=1, help="Confidence from 0 to 1.")
    ] = 0.5,
    relation: Annotated[
        str | None, typer.Option("--relation", help="Relation code; default by record types.")
    ] = None,
    pin: Annotated[
        str | None, typer.Option("--pin", help="Revision to pin; default floats.")
    ] = None,
    note: Annotated[str | None, typer.Option("--note", help="Optional note.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Suggest a link; it waits for `accept` or `decline`."""
    _create(ctx, project, from_key, to_key, relation, pin, note, actor, confidence)


@app.command("list")
def list_links(
    ctx: typer.Context,
    project: _Project,
    key: Annotated[str, typer.Argument(help="Record key.")],
    all_links: Annotated[
        bool, typer.Option("--all", help="Include retracted and declined links.")
    ] = False,
) -> None:
    """Show a record's links in both directions and the expected links it still lacks."""
    raise NotImplementedError


def _act(
    ctx: typer.Context,
    project: str,
    verb: str,
    link_id: str,
    run: Callable[[UnitOfWork, str], CommandResult],
) -> None:
    db: Path = ctx.obj
    with _service_errors(), open_uow(db) as uow:
        result = run(uow, f"project:{project}")
    typer.echo(f"{verb} {link_id}")
    typer.echo(f"version {result.version}")


@app.command("accept")
def accept(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    note: Annotated[str | None, typer.Option("--note", help="Optional note.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Accept a suggested link."""
    raise NotImplementedError


@app.command("decline")
def decline(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    reason: Annotated[str | None, typer.Option("--reason", help="Optional reason.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Decline a suggested link. The same suggestion is not made again."""
    raise NotImplementedError


@app.command("verify")
def verify(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    note: Annotated[str | None, typer.Option("--note", help="Optional note.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Mark an active link verified by the actor."""
    raise NotImplementedError


@app.command("repin")
def repin(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    pin: Annotated[
        str | None, typer.Option("--pin", help="New revision; omit to float to the current one.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Re-pin a link; a stale link becomes active again."""
    raise NotImplementedError


@app.command("retract")
def retract(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the link is retracted.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Retract a link. Its history stays; links are never deleted."""
    raise NotImplementedError


@app.command("flag")
def flag(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    status: Annotated[str, typer.Option("--status", help="stale or broken.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the link is flagged.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Flag a link stale or broken."""
    raise NotImplementedError
