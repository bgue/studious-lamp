"""`tl punch ls|show`: the punch list reads (P2-PUNCH-T02).

None of these writes anything. Every verb first checks the access word `quality.view` on the
project for the invoking actor (`--actor`, default the dev actor), before any item is read; a
refusal is `error: forbidden: ...`. The reads then go through ``tl_mod_quality.views`` with the
session's viewer, so a hidden item is absent from a list, its total and a show, and answers the
same as a missing key. The CLI prints the fields the views return and queries nothing itself.
``register(app)`` adds the two commands to the ``punch`` group.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.confidentiality import Viewer
from tl_core.services.queries import get_record
from tl_core.uow import UnitOfWork
from tl_mod_quality import views
from tl_mod_quality.names import CATEGORIES, CLEARED, OPEN, VERIFIED, VOID

from tl_cli.derive_support import DEV_ACTOR, acting, cell, fail, scope_of, service_errors
from tl_cli.session import session_viewer

#: The access word of every punch read, and the module it is declared on.
VIEW_WORD = "quality.view"
ACCESS_MODULE = "quality"
STATES = (OPEN, CLEARED, VERIFIED, VOID)
#: The default and the most rows the list prints.
LIST_LIMIT = 200

Actor = Annotated[
    str,
    typer.Option("--actor", help="The actor whose access words gate the read (default dev)."),
]


def require_view(uow: UnitOfWork, scope: str, actor: str) -> None:
    """The entry check of every punch read: ``actor`` holds ``quality.view`` on the project.

    The word is a role gate, so a refusal is `error: forbidden: ...` and does not hide anything.
    """
    try:
        require_word(
            uow.conn(),
            holder_for_actor(uow.conn(), actor),
            scope=scope,
            module=ACCESS_MODULE,
            word=normalise_word(VIEW_WORD),
            what=VIEW_WORD,
        )
    except ForbiddenError as exc:
        fail(f"forbidden: {exc}")


def enter(db: DbTarget, scope: str, actor: str) -> Viewer:
    """Check the actor (``acting``) and the view word, then return the viewer the reads use."""
    checked = acting(db, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        require_view(uow, scope, checked)
    return session_viewer(db)


def source_key(uow: UnitOfWork, scope: str, key: str, viewer: Viewer) -> str:
    """``key`` when it names a record ``viewer`` may read (``--from``), else `error: no record`."""
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, key)
    if row is None:
        fail(f"no record {key}")
    return key


def punch_ls(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
    state: Annotated[
        str | None, typer.Option("--state", help="Open, Cleared, Verified or Void.")
    ] = None,
    area: Annotated[str | None, typer.Option("--area", help="Only this area.")] = None,
    system: Annotated[str | None, typer.Option("--system", help="Only this system.")] = None,
    assignee: Annotated[str | None, typer.Option("--assignee", help="Only this user:X.")] = None,
    category: Annotated[str | None, typer.Option("--category", help="A, B or C.")] = None,
    source: Annotated[
        str | None, typer.Option("--from", help="Only items raised from this record key.")
    ] = None,
    overdue: Annotated[
        bool, typer.Option("--overdue", help="Only open items past their due date.")
    ] = False,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows to list (default 200).")
    ] = LIST_LIMIT,
) -> None:
    """List the punch items of the project by key.

    `punch items: <total>`, then `<key>  <state>  <category>  <area>  <system>  <due>  <assignee>
    <subject>` for each, `-` for none, the subject cut to 50.
    """
    if state is not None and state not in STATES:
        raise typer.BadParameter(f"must be one of {', '.join(STATES)}", param_hint="'--state'")
    if category is not None and category not in CATEGORIES:
        raise typer.BadParameter(
            f"must be one of {', '.join(CATEGORIES)}", param_hint="'--category'"
        )
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        source_filter = None if source is None else source_key(uow, scope, source, viewer)
        page = views.punch_list(
            uow.conn(),
            scope,
            state=state,
            area=area,
            system=system,
            assignee=assignee,
            category=category,
            source_key=source_filter,
            overdue=overdue,
            today=date.today().isoformat(),
            limit=limit,
            viewer=viewer,
        )
    typer.echo(f"punch items: {page.total}")
    for r in page.rows:
        typer.echo(
            f"{r.key}  {r.state}  {r.category}  {cell(r.area, 64)}  {cell(r.system, 64)}  "
            f"{cell(r.due_on)}  {cell(r.assignee, 120)}  {cell(r.subject, 50)}"
        )


def punch_show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The punch item key, for example P123-PUN-0001.")],
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show one punch item. An absent or hidden item is `error: no punch item <key>`."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.punch_detail(uow.conn(), scope, key, viewer=viewer)
    if found is None:
        fail(f"no punch item {key}")
    r = found.row
    lines = [
        f"punch item {r.key}",
        f"state  {r.state}",
        f"subject  {cell(r.subject, 200)}",
        f"category  {r.category}",
        f"area  {cell(r.area, 64)}",
        f"system  {cell(r.system, 64)}",
        f"due  {cell(r.due_on)}",
        f"assignee  {cell(r.assignee, 120)}",
        f"raised by  {cell(r.raised_by, 120)}",
        f"raised from  {cell(r.source_key)}",
        f"cleared  {cell(found.cleared_by, 120)}  {cell(found.cleared_on)}  "
        f"{cell(found.clear_note, 300)}",
        f"verified  {cell(found.verified_by, 120)}  {cell(found.verified_on)}",
        f"reopened  {found.reopen_count}  {cell(found.last_reopen_reason, 300)}",
        f"void  {cell(found.void_reason, 300)}",
    ]
    for line in lines:
        typer.echo(line)


def register(app: typer.Typer) -> None:
    """Add the punch reads (`ls`, `show`) to the `punch` group."""
    for function, name in ((punch_ls, "ls"), (punch_show, "show")):
        app.command(name)(function)
