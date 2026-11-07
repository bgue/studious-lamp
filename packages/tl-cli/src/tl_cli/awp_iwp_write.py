"""`tl awp iwp` write verbs: create, scope, pins, split, moves, cancel, sign-off, issue, hold
(P2-I2-T04e1).

Each verb builds one command model of ``tl_mod_awp.commands``, gates it with ``require_command``
and runs the handler that ``AWP_COMMANDS`` names (``awp_write._execute``), on one unit of work.
An IWP is named by its number and resolved to its id with ``iwp_views.iwp_detail``; a scope item,
a CWP or a document is named by its record key. The CLI parses options and prints one line; the
handlers decide. ``hash`` is a read: it prints the record hash a sign-off must carry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import Command, CommandResult
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_awp import iwp_views, views
from tl_mod_awp.commands import (
    AddIwpScope,
    CancelIwp,
    CreateIwp,
    CreateScopeItem,
    HoldIwp,
    IssueIwp,
    PinIwpDocument,
    ReleaseHold,
    RemoveIwpScope,
    ReturnIwpToDevelopment,
    SendIwpToConstraintCheck,
    SignOffIwp,
    SplitIwp,
    StartIwpDevelopment,
)
from tl_mod_awp.handlers.signoff import iwp_record_hash

from tl_cli.awp_write import _execute, _line
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

#: The actions of `tl awp iwp move`, each with its command model.
IWP_MOVES: dict[str, Callable[..., Command]] = {
    "start-development": StartIwpDevelopment,
    "constraint-check": SendIwpToConstraintCheck,
    "return-to-development": ReturnIwpToDevelopment,
}


def _iwp_id(uow: UnitOfWork, project: str, number: str) -> str:
    found = iwp_views.iwp_detail(uow.conn(), scope_of(project), number)
    if found is None:
        fail(f"no IWP {number}")
    return found.id


def _cwp_id(uow: UnitOfWork, project: str, number: str) -> str:
    found = views.cwp_detail(uow.conn(), scope_of(project), number)
    if found is None:
        fail(f"no CWP '{number}' in project {project}")
    return found.id


def _record_id(uow: UnitOfWork, project: str, key: str, what: str) -> str:
    """The id of the record with this key in the project (the key lookup of ``tl_cli.link``)."""
    row = get_record(uow, scope_of(project), key)
    if row is None:
        fail(f"no {what} with key {key!r} in project {project}")
    return str(row["id"])


def _items(uow: UnitOfWork, project: str, keys: list[str]) -> list[str]:
    return [_record_id(uow, project, key, "scope item") for key in keys]


def _group_keys(value: str) -> list[str]:
    """One ``--group`` value, ``KEY,KEY``: the keys, none empty."""
    keys = [key.strip() for key in value.split(",")]
    if not all(keys):
        fail(f"--group {value}: expected KEY,KEY")
    return keys


def _scope_line(verb: str, number: str, count: int, result: CommandResult) -> None:
    typer.echo(f"{verb} {number}  {count} items  version {result.version}")


# --- create and scope items -----------------------------------------------------------------------


def iwp_create(
    ctx: typer.Context,
    project: Project,
    discipline: Annotated[str, typer.Option("--discipline", help="The discipline code.")],
    title: Annotated[str, typer.Option("--title", help="The IWP's title.")],
    cwp: Annotated[str | None, typer.Option("--cwp", help="The CWP number.")] = None,
    planned_start: Annotated[
        str | None, typer.Option("--planned-start", help="YYYY-MM-DD.")
    ] = None,
    planned_finish: Annotated[
        str | None, typer.Option("--planned-finish", help="YYYY-MM-DD.")
    ] = None,
    foreman: Annotated[str | None, typer.Option("--foreman", help="user:X.")] = None,
    hours: Annotated[str | None, typer.Option("--hours", help="Estimated hours.")] = None,
    crew: Annotated[str | None, typer.Option("--crew", help="Crew text.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Create an IWP in the project; prints `created IWP <number>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return CreateIwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            discipline=discipline,
            title=title,
            cwp_id=None if cwp is None else _cwp_id(uow, project, cwp),
            planned_start=planned_start,
            planned_finish=planned_finish,
            foreman=foreman,
            estimated_hours=hours,
            crew_text=crew,
        )

    result = _execute(db, build)
    typer.echo(f"created IWP {result.key}")


def iwp_item_create(
    ctx: typer.Context,
    project: Project,
    commodity: Annotated[str, typer.Option("--commodity", help="The commodity code.")],
    description: Annotated[str, typer.Option("--description", help="The description.")],
    qty: Annotated[str, typer.Option("--qty", help="The quantity.")],
    uom: Annotated[str, typer.Option("--uom", help="The unit of measure.")],
    hours: Annotated[str, typer.Option("--hours", help="Estimated hours.")],
    cwp: Annotated[str | None, typer.Option("--cwp", help="The CWP number.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Create a scope item; prints `created scope item <key>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return CreateScopeItem(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            commodity=commodity,
            description=description,
            qty=qty,
            uom=uom,
            est_hours=hours,
            cwp_id=None if cwp is None else _cwp_id(uow, project, cwp),
        )

    result = _execute(db, build)
    typer.echo(f"created scope item {result.key}")


def iwp_add_scope(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    items: Annotated[list[str], typer.Argument(help="Scope item keys (at most 200).")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Add scope items to the IWP. Prints `add-scope <number>  <n> items  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return AddIwpScope(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            items=_items(uow, project, items),
        )

    result = _execute(db, build)
    _scope_line("add-scope", number, len(items), result)


def iwp_remove_scope(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    items: Annotated[list[str], typer.Argument(help="Scope item keys (at most 200).")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Remove scope items from the IWP. Prints `remove-scope <number>  <n> items  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return RemoveIwpScope(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            items=_items(uow, project, items),
        )

    result = _execute(db, build)
    _scope_line("remove-scope", number, len(items), result)


def iwp_pin(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    document: Annotated[str, typer.Argument(help="The document key.")],
    project: Project,
    pin: Annotated[
        str | None, typer.Option("--pin", help="A revision code; none pins the current one.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Pin a document to the IWP. Prints `pin <number>  version <v>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return PinIwpDocument(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            document=_record_id(uow, project, document, "document"),
            pin=pin,
        )

    _line("pin", number, _execute(db, build))


def iwp_split(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the IWP is split.")],
    by_hours: Annotated[
        bool, typer.Option("--by-hours", help="Cut the scope in key order by hours.")
    ] = False,
    group: Annotated[
        list[str] | None,
        typer.Option("--group", help="KEY,KEY ... one new IWP; repeatable."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Split the IWP, by hours or by the given groups of scope. Prints `split <number>`."""
    db: DbTarget = ctx.obj
    if by_hours and group:
        raise typer.BadParameter("give --by-hours or --group, not both")
    if not by_hours and not group:
        raise typer.BadParameter("give --by-hours or --group KEY,KEY ...")
    who = acting(db, actor)
    mode = "by_hours" if by_hours else "by_scope"

    def build(uow: UnitOfWork) -> Command:
        groups = None if group is None else [_items(uow, project, _group_keys(g)) for g in group]
        return SplitIwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            mode=mode,
            groups=groups,
            reason=reason,
        )

    _execute(db, build)
    typer.echo(f"split {number}")


# --- moves, cancel --------------------------------------------------------------------------------


def iwp_move(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    action: Annotated[
        str,
        typer.Argument(help="start-development, constraint-check or return-to-development."),
    ],
    project: Project,
    reason: Annotated[str | None, typer.Option("--reason", help="Why.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Move the IWP along its life cycle. Prints `move <number>  version <n>`."""
    db: DbTarget = ctx.obj
    model = IWP_MOVES.get(action)
    if model is None:
        fail(f"unknown ACTION {action!r}; the actions are {', '.join(IWP_MOVES)}")
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return model(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            reason=reason,
        )

    _line("move", number, _execute(db, build))


def iwp_cancel(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the IWP is cancelled.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Cancel the IWP. Prints `cancel <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return CancelIwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            reason=reason,
        )

    _line("cancel", number, _execute(db, build))


# --- hash, sign-off, issue, hold ------------------------------------------------------------------


def iwp_hash(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
) -> None:
    """Print the record hash of the IWP, the value a sign-off carries: `record hash <sha256>`."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        digest = iwp_record_hash(uow.conn(), _iwp_id(uow, project, number))
    typer.echo(f"record hash {digest}")


def iwp_sign_off(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    record_hash: Annotated[str, typer.Option("--hash", help="The record hash (iwp hash).")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Sign off the IWP that is Ready. Prints `sign-off <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return SignOffIwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            record_hash=record_hash,
        )

    _line("sign-off", number, _execute(db, build))


def iwp_issue(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    record_hash: Annotated[str, typer.Option("--hash", help="The record hash (iwp hash).")],
    foreman: Annotated[str | None, typer.Option("--foreman", help="user:X.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Issue the signed-off IWP to its foreman. Prints `issue <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return IssueIwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            foreman=foreman,
            record_hash=record_hash,
        )

    _line("issue", number, _execute(db, build))


def iwp_hold(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the IWP is held.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Put the IWP on hold. Prints `hold <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return HoldIwp(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            reason=reason,
        )

    _line("hold", number, _execute(db, build))


def iwp_release_hold(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    reason: Annotated[str | None, typer.Option("--reason", help="Why.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Lift the hold of the IWP. Prints `release-hold <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return ReleaseHold(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp=_iwp_id(uow, project, number),
            reason=reason,
        )

    _line("release-hold", number, _execute(db, build))


# --- registration ---------------------------------------------------------------------------------


def register(iwp_app: typer.Typer) -> None:
    """Add the write verbs to the ``iwp`` group of ``tl awp`` (the glue ticket makes the group)."""
    verbs: tuple[tuple[str, Callable[..., None]], ...] = (
        ("create", iwp_create),
        ("item-create", iwp_item_create),
        ("add-scope", iwp_add_scope),
        ("remove-scope", iwp_remove_scope),
        ("pin", iwp_pin),
        ("split", iwp_split),
        ("move", iwp_move),
        ("cancel", iwp_cancel),
        ("hash", iwp_hash),
        ("sign-off", iwp_sign_off),
        ("issue", iwp_issue),
        ("hold", iwp_hold),
        ("release-hold", iwp_release_hold),
    )
    for name, function in verbs:
        iwp_app.command(name)(function)
