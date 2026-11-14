"""`tl punch` write verbs: raise, edit, clear, verify, reopen, void (P2-PUNCH-T02).

Each verb builds one command model of ``tl_mod_quality.commands``, gates it with ``require_command``
and runs the handler that ``PUNCH_COMMANDS`` names, on one unit of work. A punch item is named by
the key a read prints and resolved to its record id with ``get_record``, as the actor's viewer
reads it (a hidden item answers as one that does not exist). A source key of ``--from`` resolves the
same way. The CLI parses options and prints one line; the handlers decide.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.services.commands import Command, CommandResult
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_quality.commands import (
    ClearPunchItem,
    EditPunchItem,
    RaisePunchItem,
    ReopenPunchItem,
    VerifyPunchItem,
    VoidPunchItem,
)
from tl_mod_quality.module import PUNCH_COMMANDS
from tl_mod_quality.names import PUNCH_ITEM

from tl_cli.awp_write import _line
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_command

#: The category help text of the write verbs.
CATEGORY_HELP = "The category: A, B or C."


def _handler(model: type[Command]) -> Callable[[UnitOfWork, Any], CommandResult]:
    """The handler ``PUNCH_COMMANDS`` names for this command model."""
    return next(c.handler for c in PUNCH_COMMANDS if c.model is model)


def _execute(db: DbTarget, build: Callable[[UnitOfWork], Command]) -> CommandResult:
    """Build the command on the ledger, gate it with the module role, run its handler; one write."""
    with service_errors(), open_uow(db) as uow:
        command = build(uow)
        require_command(uow, command)
        return _handler(type(command))(uow, command)


def _model(model: type[Command], **fields: Any) -> Command:
    """The command model with ``fields``; a value the model refuses is a usage error (exit 2)."""
    try:
        return model(**fields)
    except ValidationError as exc:
        raise typer.BadParameter(str(exc.errors()[0]["msg"])) from None


def _given(**options: Any) -> dict[str, Any]:
    """The options the user gave (a None is not given: the field is left out of the command)."""
    return {name: value for name, value in options.items() if value is not None}


def _source_id(uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer) -> str:
    """The id of the record ``key`` names, as ``viewer`` may read it (``--from``)."""
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None:
        fail(f"no record {key}")
    return str(row["id"])


def _item(uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer) -> dict[str, Any]:
    """The punch item ``key`` names (its envelope row), as ``viewer`` may read it.

    An absent item, one in another project and a hidden one all answer `error: no punch item <key>`.
    A void item is still found: its handler refuses the change.
    """
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None or row.get("type") != PUNCH_ITEM:
        fail(f"no punch item {key}")
    return row


# --- raise, edit ----------------------------------------------------------------------------------


def punch_raise(
    ctx: typer.Context,
    project: Project,
    subject: Annotated[str, typer.Option("--subject", help="The subject of the item.")],
    description: Annotated[str | None, typer.Option("--description", help="The detail.")] = None,
    area: Annotated[str | None, typer.Option("--area", help="The area.")] = None,
    system: Annotated[str | None, typer.Option("--system", help="The system.")] = None,
    due: Annotated[str | None, typer.Option("--due", help="The due date, YYYY-MM-DD.")] = None,
    category: Annotated[str | None, typer.Option("--category", help=CATEGORY_HELP)] = None,
    assignee: Annotated[str | None, typer.Option("--assignee", help="user:X.")] = None,
    source: Annotated[
        str | None, typer.Option("--from", help="The key of the record it was raised from.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Raise a punch item; the actor is the raiser. Prints `raised <key>  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        fields = _given(
            subject=subject,
            description=description,
            area=area,
            system=system,
            due_on=due,
            category=category,
            assignee=assignee,
        )
        if source is not None:
            fields["from_record_id"] = _source_id(uow, scope, source, viewer)
        return _model(RaisePunchItem, actor=who, source=SOURCE, scope=scope, **fields)

    result = _execute(db, build)
    _line("raised", str(result.key), result)


def punch_edit(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The punch item key, for example P123-PUN-0001.")],
    project: Project,
    subject: Annotated[str | None, typer.Option("--subject", help="The subject.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="The detail.")] = None,
    area: Annotated[str | None, typer.Option("--area", help="The area.")] = None,
    system: Annotated[str | None, typer.Option("--system", help="The system.")] = None,
    due: Annotated[str | None, typer.Option("--due", help="The due date, YYYY-MM-DD.")] = None,
    category: Annotated[str | None, typer.Option("--category", help=CATEGORY_HELP)] = None,
    assignee: Annotated[str | None, typer.Option("--assignee", help="user:X.")] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The version read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Change fields of an open punch item; at least one is needed.

    Prints `edited <key>  version <v>`.
    """
    fields = _given(
        subject=subject,
        description=description,
        area=area,
        system=system,
        due_on=due,
        category=category,
        assignee=assignee,
    )
    if not fields:
        raise typer.BadParameter("name at least one field to change")
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _item(uow, scope, key, viewer)
        version = expected_version if expected_version is not None else int(row["version"])
        return _model(
            EditPunchItem,
            actor=who,
            source=SOURCE,
            scope=scope,
            punch_item=str(row["id"]),
            expected_version=version,
            **fields,
        )

    _line("edited", key, _execute(db, build))


# --- state verbs ----------------------------------------------------------------------------------


_EXPECTED = typer.Option(
    "--expected-version", min=1, help="The version the change is made on (default: the one read)."
)


def punch_clear(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The punch item key, for example P123-PUN-0001.")],
    project: Project,
    note: Annotated[str, typer.Option("--note", help="What was done.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Clear an open punch item. Prints `cleared <key>  version <v>`."""
    _run(ctx, "cleared", ClearPunchItem, key, project, actor, expected_version, note=note)


def punch_verify(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The punch item key, for example P123-PUN-0001.")],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Verify a cleared punch item. Prints `verified <key>  version <v>`."""
    _run(ctx, "verified", VerifyPunchItem, key, project, actor, expected_version)


def punch_reopen(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The punch item key, for example P123-PUN-0001.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is reopened.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Reopen a cleared or verified punch item. Prints `reopened <key>  version <v>`."""
    _run(ctx, "reopened", ReopenPunchItem, key, project, actor, expected_version, reason=reason)


def punch_void(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The punch item key, for example P123-PUN-0001.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why it is void.")],
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Void an open or cleared punch item. Prints `voided <key>  version <v>`."""
    _run(ctx, "voided", VoidPunchItem, key, project, actor, expected_version, reason=reason)


def _run(
    ctx: typer.Context,
    verb: str,
    model: type[Command],
    key: str,
    project: str,
    actor: str,
    expected_version: int | None,
    **fields: Any,
) -> None:
    """The one body of the state verbs: the database target comes from the root context."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Command:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _item(uow, scope, key, viewer)
        version = expected_version if expected_version is not None else int(row["version"])
        return _model(
            model,
            actor=who,
            source=SOURCE,
            scope=scope,
            punch_item=str(row["id"]),
            expected_version=version,
            **fields,
        )

    _line(verb, key, _execute(db, build))


# --- registration ---------------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
    """Add the write verbs to the ``punch`` group."""
    verbs: tuple[tuple[str, Callable[..., None]], ...] = (
        ("raise", punch_raise),
        ("edit", punch_edit),
        ("clear", punch_clear),
        ("verify", punch_verify),
        ("reopen", punch_reopen),
        ("void", punch_void),
    )
    for name, function in verbs:
        app.command(name)(function)
