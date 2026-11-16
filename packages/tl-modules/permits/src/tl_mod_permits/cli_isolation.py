"""`tl isolation apply|verify|remove|link|unlink|ls|show|export`: the isolation commands and reads
(P2-PTW-T06a).

The writes follow ``cli_permit_write``: parse the options, build one command model of
``tl_mod_permits.iso_commands``, gate it with ``require_command`` and run the handler that
``COMMANDS`` names, on one unit of work; the handler decides, and its refusals print as every
service error prints. A key is resolved to its record id with ``get_record`` as the actor's
viewer reads it, so a hidden record answers as one that does not exist. The reads check
``permits.view`` before any read (``cli_permit_read.enter``) and call ``iso_views`` under the
session's viewer. Nothing here prints a record id, runs SQL, or reads the clock.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_cli.awp_write import _line
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import require_command
from tl_core import confidentiality as cf
from tl_core.services.commands import Command, CommandResult
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork

from tl_mod_permits import iso_views
from tl_mod_permits.cli import isolation_app
from tl_mod_permits.cli_permit_read import LABEL_WIDTH, LIST_LIMIT, _choice, _when, enter
from tl_mod_permits.cli_permit_read import Actor as ReadActor
from tl_mod_permits.cli_permit_write import _for_id, _handler, _model, _permit
from tl_mod_permits.iso_commands import (
    ApplyIsolation,
    LinkIsolation,
    RemoveIsolation,
    UnlinkIsolation,
    VerifyIsolation,
)
from tl_mod_permits.names import ENERGY_KINDS, ISOLATION, ISOLATION_STATES
from tl_mod_permits.views import EXPORT_FORMATS

_KEY_HELP = "The isolation key a read prints, for example P123-ISL-0001."
_PERMIT_HELP = "The permit key a read prints, for example P123-PTW-0001."
_EXPECTED = typer.Option(
    "--expected-version", min=1, help="The version the change is made on (default: the one read)."
)


def _execute(db: DbTarget, who: str, build: Callable[[UnitOfWork], Command]) -> CommandResult:
    """``cli_permit_write._execute``, with the build, the gate and the handler reading as ``who``.

    The process's own viewer on a dev ledger is the file's owner, who reads restricted records, so
    a refusal that names only what the viewer may read would name a permit ``who`` cannot see. The
    actor's viewer is the one the reads use, and the one the handler's refusals must follow.
    """
    with service_errors(), open_uow(db) as uow, cf.use_viewer(cf.viewer_for_actor(uow.conn(), who)):
        command = build(uow)
        require_command(uow, command)
        return _handler(type(command))(uow, command)


def _isolation(uow: UnitOfWork, scope: str, key: str, viewer: cf.Viewer) -> dict[str, Any]:
    """The isolation ``key`` names (its envelope row), as ``viewer`` may read it.

    An absent isolation, one in another project, a hidden one and a record of another type all
    answer `error: no isolation <key>`.
    """
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None or row.get("type") != ISOLATION:
        fail(f"no isolation {key}")
    return row


# --- the writes -----------------------------------------------------------------------------------


@isolation_app.command("apply")
def isolation_apply(
    ctx: typer.Context,
    project: Project,
    point: Annotated[str, typer.Option("--point", help="The point of isolation, as text.")],
    energy: Annotated[str, typer.Option("--energy", help=f"One of {', '.join(ENERGY_KINDS)}.")],
    method: Annotated[str, typer.Option("--method", help="How the energy is isolated.")],
    lock: Annotated[str, typer.Option("--lock", help="The lock number.")],
    tag: Annotated[str, typer.Option("--tag", help="The tag number.")],
    point_record: Annotated[
        str | None,
        typer.Option("--point-record", help="The key of the tag or equipment record, if any."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Apply an isolation (state Applied); the actor is the person who applied it.

    Prints `applied <key>  version <v>`.
    """
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Any:
        fields: dict[str, Any] = {
            "point_text": point,
            "energy": energy,
            "method": method,
            "lock_number": lock,
            "tag_number": tag,
        }
        if point_record is not None:
            viewer = cf.viewer_for_actor(uow.conn(), who)
            fields["point_record_id"] = _for_id(uow, scope, point_record, viewer)
        return _model(ApplyIsolation, actor=who, source=SOURCE, scope=scope, **fields)

    result = _execute(db, who, build)
    _line("applied", str(result.key), result)


def _on_isolation(
    ctx: typer.Context,
    verb: str,
    model: type[Any],
    key: str,
    project: str,
    actor: str,
    expected_version: int | None,
) -> None:
    """The one body of verify and remove: the isolation is named by its key, the version is read."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Any:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _isolation(uow, scope, key, viewer)
        version = expected_version if expected_version is not None else int(row["version"])
        return _model(
            model,
            actor=who,
            source=SOURCE,
            scope=scope,
            isolation=str(row["id"]),
            expected_version=version,
        )

    result = _execute(db, who, build)
    _line(verb, key, result)


@isolation_app.command("verify")
def isolation_verify(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Verify an applied isolation, by a controller other than the person who applied it.

    Prints `verified <key>  version <v>`.
    """
    _on_isolation(ctx, "verified", VerifyIsolation, key, project, actor, expected_version)


@isolation_app.command("remove")
def isolation_remove(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    expected_version: Annotated[int | None, _EXPECTED] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Remove an applied or verified isolation, while no live permit needs it.

    Prints `removed <key>  version <v>`.
    """
    _on_isolation(ctx, "removed", RemoveIsolation, key, project, actor, expected_version)


def _on_link(
    ctx: typer.Context,
    verb: str,
    model: type[Any],
    permit: str,
    isolation: str,
    project: str,
    actor: str,
) -> None:
    """The one body of link and unlink: the permit and the isolation are named by their keys."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)

    def build(uow: UnitOfWork) -> Any:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        permit_row = _permit(uow, scope, permit, viewer)
        isolation_row = _isolation(uow, scope, isolation, viewer)
        return _model(
            model,
            actor=who,
            source=SOURCE,
            scope=scope,
            permit=str(permit_row["id"]),
            isolation=str(isolation_row["id"]),
        )

    result = _execute(db, who, build)
    _line(verb, f"{permit} {isolation}", result)


@isolation_app.command("link")
def isolation_link(
    ctx: typer.Context,
    permit: Annotated[str, typer.Argument(help=_PERMIT_HELP)],
    isolation: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Make a permit depend on an isolation. Prints `linked <permit> <isolation>  version <v>`."""
    _on_link(ctx, "linked", LinkIsolation, permit, isolation, project, actor)


@isolation_app.command("unlink")
def isolation_unlink(
    ctx: typer.Context,
    permit: Annotated[str, typer.Argument(help=_PERMIT_HELP)],
    isolation: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Stop a permit depending on an isolation.

    Prints `unlinked <permit> <isolation>  version <v>`.
    """
    _on_link(ctx, "unlinked", UnlinkIsolation, permit, isolation, project, actor)


# --- the reads ------------------------------------------------------------------------------------


def isolation_ls(
    ctx: typer.Context,
    project: Project,
    actor: ReadActor = DEV_ACTOR,
    state: Annotated[
        str | None, typer.Option("--state", help="A state: Applied, Verified or Removed.")
    ] = None,
    energy: Annotated[
        str | None, typer.Option("--energy", help="An energy kind, for example electrical.")
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=iso_views.MAX_LIMIT, help="The most rows to list."),
    ] = LIST_LIMIT,
) -> None:
    """List the isolations of the project by key, then `n of total`.

    Columns: key, point, energy, state, lock, tag, applied by, depends. `-` for none.
    """
    _choice(state, ISOLATION_STATES, "--state")
    _choice(energy, ENERGY_KINDS, "--energy")
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = iso_views.isolation_list(
            uow.conn(), scope, state=state, energy=energy, limit=limit, viewer=viewer
        )
    typer.echo("key  point  energy  state  lock  tag  applied by  depends")
    for r in page.rows:
        typer.echo(
            f"{r.key}  {cell(r.point_text, 50)}  {r.energy}  {r.state}  "
            f"{cell(r.lock_number)}  {cell(r.tag_number)}  {cell(r.applied_by)}  {r.depends}"
        )
    typer.echo(f"{len(page.rows)} of {page.total}")


def _detail_lines(found: iso_views.IsolationDetail) -> list[tuple[str, str | None]]:
    """The labelled values of a `show`; the caller leaves out the None and empty ones."""
    r = found.row
    return [
        ("Point", r.point_text),
        ("Energy", r.energy),
        ("State", r.state),
        ("Method", r.method),
        ("Lock", r.lock_number),
        ("Tag", r.tag_number),
        ("Applied by", r.applied_by),
        ("Applied", _when(r.applied_at)),
        ("Verified by", r.verified_by),
        ("Verified", _when(r.verified_at)),
        ("Removed by", found.removed_by),
        ("Removed", _when(found.removed_at)),
        ("Linked permits", ", ".join(found.permits) or None),
        ("Version", str(found.version)),
    ]


def isolation_show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    actor: ReadActor = DEV_ACTOR,
) -> None:
    """Show one isolation. An absent, hidden or other-project isolation is `error: no isolation`."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = iso_views.isolation_detail(uow.conn(), scope, key, viewer=viewer)
    if found is None:
        fail(f"no isolation {key}")
    shown = [(label, value) for label, value in _detail_lines(found) if value not in (None, "")]
    width = min(max(len(label) for label, _ in shown) + 2, LABEL_WIDTH)
    typer.echo(f"isolation {found.row.key}")
    for label, value in shown:
        typer.echo(f"{label.ljust(width)}{cell(value, 300)}")


def isolation_export(
    ctx: typer.Context,
    project: Project,
    fmt: Annotated[str, typer.Option("--format", help="csv or jsonl.")],
    actor: ReadActor = DEV_ACTOR,
    state: Annotated[
        str | None, typer.Option("--state", help="A state: Applied, Verified or Removed.")
    ] = None,
    energy: Annotated[
        str | None, typer.Option("--energy", help="An energy kind, for example electrical.")
    ] = None,
) -> None:
    """Export the isolations of the project, with the filters of `ls`, as csv or jsonl."""
    if fmt not in EXPORT_FORMATS:
        raise typer.BadParameter("must be csv or jsonl", param_hint="'--format'")
    _choice(state, ISOLATION_STATES, "--state")
    _choice(energy, ENERGY_KINDS, "--energy")
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = iso_views.isolation_list(
            uow.conn(),
            scope,
            state=state,
            energy=energy,
            limit=iso_views.MAX_LIMIT,
            viewer=viewer,
        )
    typer.echo(iso_views.isolation_export_rows(page.rows, fmt), nl=False)


isolation_app.command("ls")(isolation_ls)
isolation_app.command("show")(isolation_show)
isolation_app.command("export")(isolation_export)
