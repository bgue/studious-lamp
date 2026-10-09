"""The `tl link` group: create, maintain and read links between records (brief 7).

Each subcommand parses options, makes one call into `tl_core.services`, and prints. Rules (relation
vocabulary, lifecycle, scope) live in the services. Records are named by key; links by the id that
`add`, `suggest` and `list` print.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal, NoReturn, cast

import typer
from pydantic import ValidationError
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import ConcurrencyError
from tl_core.links.expected import ExpectedLinkError, missing_expected_links
from tl_core.services.commands import CommandResult
from tl_core.services.errors import ServiceError
from tl_core.services.link_queries import links_of
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    RepinLink,
    RetractLink,
    SuggestLink,
    VerifyLink,
    handle_accept_link,
    handle_add_link,
    handle_decline_link,
    handle_flag_link,
    handle_repin_link,
    handle_retract_link,
    handle_suggest_link,
    handle_verify_link,
)
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
    db: Path = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        source = _record(uow, scope, project, from_key)
        target = _record(uow, scope, project, to_key)
        fields = {
            "actor": actor,
            "source": "cli",
            "scope": scope,
            "from_id": str(source["id"]),
            "to_id": str(target["id"]),
            "relation": relation,
            "pin": pin,
            "note": note,
        }
        if confidence is None:
            result = handle_add_link(uow, AddLink(**fields))
        else:
            result = handle_suggest_link(uow, SuggestLink(**fields, confidence=confidence))
    event = result.events[0]
    if confidence is None:
        typer.echo(f"added {result.stream_id}")
        typer.echo(f"relation {event.payload['relation']}")
        typer.echo("status active")
    else:
        typer.echo(f"suggested {result.stream_id}")
        typer.echo(f"relation {event.payload['relation']}")
        typer.echo("status suggested")


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
    db: Path = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db, readonly=True) as uow:
        row = _record(uow, scope, project, key)
        views = links_of(uow, str(row["id"]), include_retracted=all_links)
        missing = missing_expected_links(uow, str(row["id"]))
    typer.echo(f"key: {key}")
    for view in views:
        status = "declined" if view.declined else view.status
        typer.echo(
            "  ".join(
                [
                    view.direction,
                    view.label,
                    view.other_key or "—",
                    status,
                    view.pin or "floating",
                    view.link_id,
                ]
            )
        )
    for item in missing:
        expectation = item.expectation
        rule = expectation.relation
        if expectation.by_state:
            rule = f"{rule}@{expectation.by_state}"
        typer.echo(f"missing {expectation.display} (rule: {rule})")


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
    _act(
        ctx,
        project,
        "accepted",
        link_id,
        lambda uow, scope: handle_accept_link(
            uow,
            AcceptLink(actor=actor, source="cli", scope=scope, link_id=link_id, note=note),
        ),
    )


@app.command("decline")
def decline(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    reason: Annotated[str | None, typer.Option("--reason", help="Optional reason.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Decline a suggested link. The same suggestion is not made again."""
    _act(
        ctx,
        project,
        "declined",
        link_id,
        lambda uow, scope: handle_decline_link(
            uow,
            DeclineLink(actor=actor, source="cli", scope=scope, link_id=link_id, reason=reason),
        ),
    )


@app.command("verify")
def verify(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    note: Annotated[str | None, typer.Option("--note", help="Optional note.")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Mark an active link verified by the actor."""
    _act(
        ctx,
        project,
        "verified",
        link_id,
        lambda uow, scope: handle_verify_link(
            uow,
            VerifyLink(actor=actor, source="cli", scope=scope, link_id=link_id, note=note),
        ),
    )


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
    _act(
        ctx,
        project,
        "repinned",
        link_id,
        lambda uow, scope: handle_repin_link(
            uow,
            RepinLink(actor=actor, source="cli", scope=scope, link_id=link_id, pin=pin),
        ),
    )


@app.command("retract")
def retract(
    ctx: typer.Context,
    project: _Project,
    link_id: Annotated[str, typer.Argument(help="Link id from `tl link list`.")],
    reason: Annotated[str, typer.Option("--reason", help="Why the link is retracted.")],
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Retract a link. Its history stays; links are never deleted."""
    _act(
        ctx,
        project,
        "retracted",
        link_id,
        lambda uow, scope: handle_retract_link(
            uow,
            RetractLink(actor=actor, source="cli", scope=scope, link_id=link_id, reason=reason),
        ),
    )


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
    _act(
        ctx,
        project,
        "flagged",
        link_id,
        lambda uow, scope: handle_flag_link(
            uow,
            FlagLink(
                actor=actor,
                source="cli",
                scope=scope,
                link_id=link_id,
                status=cast(Literal["stale", "broken"], status),
                reason=reason,
            ),
        ),
    )
