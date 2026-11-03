"""`tl awp wbs define|revise|retire|map`, `tl awp cwa define|revise|retire` and `tl awp path
define|move`: the write verbs of the WBS, the construction work areas and the path of construction
(P2-I1-T04d).

Each verb builds one command model of ``tl_mod_awp.commands`` and runs the handler that
``AWP_COMMANDS`` names for it, after ``require_command`` has gated the command, on one unit of work.
The CLI parses options and prints one line; the handlers decide. A WBS node or a CWA is named by its
code and resolved to its id with the module's views. The CWP and package verbs are in
``awp_write``; the read verbs are in ``awp_read``.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget
from tl_core.services.commands import Command
from tl_core.uow import UnitOfWork
from tl_mod_awp import views
from tl_mod_awp.commands import (
    CostCodeLine,
    DefineCwa,
    DefinePathOfConstruction,
    DefineWbsNode,
    MapWbsToCostCodes,
    MoveCwaInPath,
    PathStepIn,
    RetireCwa,
    RetireWbsNode,
    ReviseCwa,
    ReviseWbsNode,
)

from tl_cli.awp_write import _execute, _group, _line, _parts
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

WBS_HELP = "The work breakdown structure (WBS)."
CWA_HELP = "Construction work areas (CWAs)."
PATH_HELP = "The path of construction."


def _wbs_id(uow: UnitOfWork, project: str, code: str) -> str:
    found = views.wbs_detail(uow.conn(), scope_of(project), code)
    if found is None:
        fail(f"no WBS node '{code}' in project {project}")
    return found.id


def _cwa_id(uow: UnitOfWork, project: str, code: str) -> str:
    found = [c for c in views.cwa_list(uow.conn(), scope_of(project)) if c.code == code]
    if not found:
        fail(f"no CWA '{code}' in project {project}")
    return found[0].id


def _cost_lines(values: list[str]) -> list[CostCodeLine]:
    """``--cost-code CODE:PERCENT`` values as allocation lines; the shape is checked first."""
    lines: list[CostCodeLine] = []
    with service_errors():
        for value in values:
            cost_code, percent = _parts(value, 2, "--cost-code", "CODE:PERCENT")
            lines.append(CostCodeLine(cost_code=cost_code, percent=percent))
    return lines


def _steps(values: list[str]) -> list[PathStepIn]:
    """``--step CWA[:REASON]`` values as path steps; the shape is checked before the ledger."""
    steps: list[PathStepIn] = []
    with service_errors():
        for value in values:
            if ":" in value:
                cwa_code, reason_code = _parts(value, 2, "--step", "CWA[:REASON]")
            else:
                cwa_code, reason_code = value, None
            steps.append(PathStepIn(cwa_code=cwa_code, reason_code=reason_code))
    return steps


# --- wbs ------------------------------------------------------------------------------------------


def wbs_define(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The WBS code of the new node.")],
    project: Project,
    title: Annotated[str, typer.Option("--title", help="The node's title.")],
    parent: Annotated[str | None, typer.Option("--parent", help="The parent's WBS code.")] = None,
    position: Annotated[
        int | None, typer.Option("--position", help="Its place among its siblings (1 first).")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Define a WBS node under a parent, or at the root. Prints `defined WBS <code>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        command = DefineWbsNode(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            code=code,
            title=title,
            parent_code=parent,
            position=position,
        )
    _execute(db, lambda _uow: command)
    typer.echo(f"defined WBS {code}")


def wbs_revise(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The WBS code of the node.")],
    project: Project,
    title: Annotated[str | None, typer.Option("--title", help="A new title.")] = None,
    parent: Annotated[str | None, typer.Option("--parent", help="A new parent's WBS code.")] = None,
    root: Annotated[bool, typer.Option("--root", help="Move the node to the root.")] = False,
    position: Annotated[
        int | None, typer.Option("--position", help="A new place among its siblings.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Change the options given; the others stay. Prints `revise <code>  version <n>`."""
    db: DbTarget = ctx.obj
    if root and parent is not None:
        fail("give --parent or --root, not both")
    # only the options given are passed: a field left out stays; --root sends a null parent
    given: dict[str, Any] = {}
    if title is not None:
        given["title"] = title
    if root:
        given["parent_code"] = None
    elif parent is not None:
        given["parent_code"] = parent
    if position is not None:
        given["position"] = position
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return ReviseWbsNode(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            node=_wbs_id(uow, project, code),
            **given,
        )

    _line("revise", code, _execute(db, build))


def wbs_retire(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The WBS code of the node.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the node is retired.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Retire the WBS node. Prints `retire <code>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return RetireWbsNode(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            node=_wbs_id(uow, project, code),
            reason=reason,
        )

    _line("retire", code, _execute(db, build))


def wbs_map(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The WBS code of a leaf node.")],
    project: Project,
    cost_code: Annotated[
        list[str] | None,
        typer.Option(
            "--cost-code",
            help="CODE:PERCENT of a cost code; repeatable; replaces the allocation.",
        ),
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Clear the allocation.")] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Replace the node's cost code allocation, or clear it. Prints `map <code>  version <n>`."""
    db: DbTarget = ctx.obj
    if not cost_code and not clear:
        fail("give --cost-code or --clear")
    if cost_code and clear:
        fail("give --cost-code or --clear, not both")
    lines = _cost_lines(cost_code or [])
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return MapWbsToCostCodes(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            node=_wbs_id(uow, project, code),
            allocations=lines,
        )

    _line("map", code, _execute(db, build))


# --- cwa ------------------------------------------------------------------------------------------


def cwa_define(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The CWA code of the new area.")],
    project: Project,
    title: Annotated[str, typer.Option("--title", help="The area's title.")],
    location: Annotated[str | None, typer.Option("--location", help="Where it is.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Define a construction work area. Prints `defined CWA <code>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    with service_errors():
        command = DefineCwa(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            code=code,
            title=title,
            location_text=location,
        )
    _execute(db, lambda _uow: command)
    typer.echo(f"defined CWA {code}")


def cwa_revise(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The CWA code.")],
    project: Project,
    title: Annotated[str | None, typer.Option("--title", help="A new title.")] = None,
    location: Annotated[str | None, typer.Option("--location", help="A new location.")] = None,
    clear_location: Annotated[
        bool, typer.Option("--clear-location", help="Clear the location.")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Change the fields given; the others stay. Prints `revise <code>  version <n>`."""
    db: DbTarget = ctx.obj
    if location is not None and clear_location:
        fail("give --location or --clear-location, not both")
    # only the options given are passed: a field left out stays; --clear-location sends a null
    given: dict[str, Any] = {}
    if title is not None:
        given["title"] = title
    if clear_location:
        given["location_text"] = None
    elif location is not None:
        given["location_text"] = location
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return ReviseCwa(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            cwa=_cwa_id(uow, project, code),
            **given,
        )

    _line("revise", code, _execute(db, build))


def cwa_retire(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The CWA code.")],
    project: Project,
    reason: Annotated[str, typer.Option("--reason", help="Why the area is retired.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Retire the construction work area. Prints `retire <code>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        return RetireCwa(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            cwa=_cwa_id(uow, project, code),
            reason=reason,
        )

    _line("retire", code, _execute(db, build))


# --- path -----------------------------------------------------------------------------------------


def path_define(
    ctx: typer.Context,
    project: Project,
    step: Annotated[
        list[str] | None,
        typer.Option("--step", help="CWA[:REASON]; repeatable, at least one, in order."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Define the path of construction (version 1). Prints `defined path  version <n>`."""
    db: DbTarget = ctx.obj
    if not step:
        fail("give at least one --step CWA[:REASON]")
    steps = _steps(step)
    who = acting(db, actor)
    with service_errors():
        command = DefinePathOfConstruction(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            steps=steps,
        )
    _line("defined", "path", _execute(db, lambda _uow: command))


def path_move(
    ctx: typer.Context,
    cwa: Annotated[str, typer.Argument(help="The CWA code to move.")],
    project: Project,
    to: Annotated[int, typer.Option("--to", help="The new place in the path (1 first).")],
    reason: Annotated[str, typer.Option("--reason", help="The PathReason code.")],
    note: Annotated[str | None, typer.Option("--note", help="A note.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Move an area to another place in the path. Prints `move <cwa>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        current = views.path(uow.conn(), scope_of(project))
        if current is None:
            fail(f"no path in project {project}")
        return MoveCwaInPath(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            cwa_code=cwa,
            to_position=to,
            reason_code=reason,
            note=note,
            expected_version=current.current_version,
        )

    _line("move", cwa, _execute(db, build))


# --- registration ---------------------------------------------------------------------------------


def register(app: typer.Typer) -> None:
    """Add the write verbs to the `wbs`, `cwa` and `path` groups of the ``tl awp`` group.

    Call it after ``tl_cli.awp_read.register`` so the read verbs stay in the same groups.
    """
    wbs = _group(app, "wbs", WBS_HELP)
    cwa = _group(app, "cwa", CWA_HELP)
    path = _group(app, "path", PATH_HELP)
    for group, name, function in (
        (wbs, "define", wbs_define),
        (wbs, "revise", wbs_revise),
        (wbs, "retire", wbs_retire),
        (wbs, "map", wbs_map),
        (cwa, "define", cwa_define),
        (cwa, "revise", cwa_revise),
        (cwa, "retire", cwa_retire),
        (path, "define", path_define),
        (path, "move", path_move),
    ):
        group.command(name)(function)
