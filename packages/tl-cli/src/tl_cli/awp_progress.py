"""`tl awp iwp start-work|complete-field|item-move|step|progress`: the field progress verbs
(P2-I5-T04b).

Each write verb builds one S2 command of ``tl_mod_awp.commands``, gates it and runs its handler
(``awp_write._execute``); the handlers check the state, the word and the stale version, so this
module repeats none of those checks. ``--expected-version`` defaults to the version the terminal
shows: the current version of the IWP, or of the scope item, read in the same unit of work. An IWP
is named by its number and a scope item by its record key. ``progress`` is a read: it prints the
earned figure the engine states for the viewer of this invocation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_awp import iwp_views
from tl_mod_awp.commands import (
    CompleteIwpField,
    InstallScopeItem,
    ManualStep,
    RecordManualProgress,
    ReturnScopeItem,
    StartIwpWork,
    VerifyScopeItem,
)
from tl_mod_awp.progress import engine

from tl_cli.awp_iwp_write import _iwp_id, _record_id
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
from tl_cli.session import session_viewer

#: The actions of `item-move`, each with its command model.
ITEM_MOVES: dict[str, Callable[..., Command]] = {
    "install": InstallScopeItem,
    "verify": VerifyScopeItem,
    "return": ReturnScopeItem,
}


def _iwp_version(uow: UnitOfWork, project: str, number: str) -> tuple[str, int]:
    """The id and the current version of the IWP with this number (a missing one is refused)."""
    iwp = _iwp_id(uow, project, number)
    row = get_record(uow, scope_of(project), number)
    if row is None:
        fail(f"no IWP {number}")
    return iwp, int(row["version"])


def _item_version(uow: UnitOfWork, project: str, key: str) -> tuple[str, int]:
    """The id and the current version of the scope item with this record key."""
    item = _record_id(uow, project, key, "scope item")
    row = get_record(uow, scope_of(project), key)
    if row is None:
        fail(f"no scope item with key {key!r} in project {project}")
    return item, int(row["version"])


def iwp_start_work(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    date_: Annotated[
        str | None, typer.Option("--date", help="The day work starts, YYYY-MM-DD. Default today.")
    ] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The IWP version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Start the field work of an issued IWP. Prints `start-work <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    at = _day(date_)

    def build(uow: UnitOfWork) -> Command:
        iwp, current = _iwp_version(uow, project, number)
        return StartIwpWork(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp_id=iwp,
            expected_version=expected_version or current,
            at=at,
        )

    _line("start-work", number, _execute(db, build))


def iwp_complete_field(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    date_: Annotated[
        str | None, typer.Option("--date", help="The day the field work ends, YYYY-MM-DD.")
    ] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The IWP version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Complete the field work of an IWP in progress. Prints
    `complete-field <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    at = _day(date_)

    def build(uow: UnitOfWork) -> Command:
        iwp, current = _iwp_version(uow, project, number)
        return CompleteIwpField(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp_id=iwp,
            expected_version=expected_version or current,
            at=at,
        )

    _line("complete-field", number, _execute(db, build))


def item_move(
    ctx: typer.Context,
    item_key: Annotated[str, typer.Argument(help="The scope item's record key.")],
    action: Annotated[str, typer.Argument(help="install, verify or return.")],
    project: Project,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The item version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Move a scope item: `install` (planned to installed), `verify` (installed to verified) or
    `return` (installed back to planned). Prints `<action> <item key>  version <n>`."""
    if action not in ITEM_MOVES:
        raise typer.BadParameter(
            f"{action!r} is not install, verify or return", param_hint="ACTION"
        )
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    model = ITEM_MOVES[action]

    def build(uow: UnitOfWork) -> Command:
        item, current = _item_version(uow, project, item_key)
        return model(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            record_id=item,
            expected_version=expected_version or current,
        )

    _line(action, item_key, _execute(db, build))


def iwp_step(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    item_key: Annotated[str, typer.Argument(help="The scope item's record key.")],
    step: Annotated[str, typer.Argument(help="The step's name, as the item's rules state it.")],
    project: Project,
    undo: Annotated[bool, typer.Option("--undo", help="Mark the step not done.")] = False,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The IWP version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Mark one step of a scope item done by hand (`--undo` to unmark it). Prints
    `step <number>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)

    def build(uow: UnitOfWork) -> Command:
        iwp, current = _iwp_version(uow, project, number)
        item = _record_id(uow, project, item_key, "scope item")
        return RecordManualProgress(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            iwp_id=iwp,
            steps=[ManualStep(scope_item_id=item, step=step, done=not undo)],
            expected_version=expected_version or current,
        )

    _line("step", number, _execute(db, build))


def iwp_progress(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
) -> None:
    """Read the earned figure of an IWP: `iwp <number>`, `earned <pct>  edition <edition>`,
    `items: <n>`, then `<key>  <pct>  <steps earned or ->` for each item and `note: <text>` for
    each note. A missing or hidden IWP is `error: no IWP <number>`."""
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = iwp_views.iwp_detail(uow.conn(), scope_of(project), number)
        if found is None:
            fail(f"no IWP {number}")
        try:
            earned = engine.earned_fraction(uow.conn(), found.id, viewer=session_viewer(db))
        except RecordNotFoundError:
            fail(f"no IWP {number}")
    typer.echo(f"iwp {number}")
    typer.echo(f"earned {earned.pct}  edition {earned.edition}")
    typer.echo(f"items: {len(earned.items)}")
    for item in earned.items:
        steps = ", ".join(item.steps) if item.steps else "-"
        typer.echo(f"{item.key}  {item.pct}  {steps}")
    for note in earned.notes:
        typer.echo(f"note: {note}")


def _day(text: str | None) -> date | None:
    """``--date`` as a day; None when it is not given (the handler then uses now)."""
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        fail(f"--date must be YYYY-MM-DD, not {text!r}")


def register(iwp_app: typer.Typer) -> None:
    """Add the progress verbs to the ``iwp`` group of ``tl awp``."""
    verbs: tuple[tuple[str, Callable[..., None]], ...] = (
        ("start-work", iwp_start_work),
        ("complete-field", iwp_complete_field),
        ("item-move", item_move),
        ("step", iwp_step),
        ("progress", iwp_progress),
    )
    for name, function in verbs:
        iwp_app.command(name)(function)
