"""`tl req ls|show` and `tl wo ls|show`: the requisition and work order reads (P2-I4A-T04d).

None of these writes anything. Every verb first checks the access word `requisitions.view` on the
project for the invoking actor (`--actor`, default the dev actor), before any requisition is read;
a refusal is `error: forbidden: ...`. The reads are the module's (`tl_mod_requisitions.views`) and
run with the session's viewer, so a hidden requisition answers as a missing one. The CLI prints the
keys and fields the views return; the one extra lookup is the key of the record a requisition
serves (`for_record_id`), and a missing or unreadable one prints `-`. `register(req_app, wo_app)`
adds the four commands to the `req` and `wo` groups that `tl_cli.req` makes.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import holder_for_actor, normalise_word, require_word
from tl_core.confidentiality import Viewer
from tl_core.services.queries import get_record, get_record_by_id
from tl_core.uow import UnitOfWork
from tl_mod_requisitions import views
from tl_mod_requisitions.names import KINDS

from tl_cli.derive_support import DEV_ACTOR, Project, acting, cell, fail, scope_of, service_errors
from tl_cli.session import session_viewer

#: The access word every requisition read checks (``schema/settings/access-words.yaml``).
VIEW_WORD = "requisitions.view"
#: The module the role resolver is asked about for the word.
ACCESS_MODULE = "requisitions"
#: The default and the most rows the lists print (the view clamps to 1..500).
LIST_LIMIT = 200

Actor = Annotated[
    str,
    typer.Option("--actor", help="The actor whose access words gate the read (default dev)."),
]


def require_view(uow: UnitOfWork, scope: str, actor: str) -> None:
    """The entry check of every requisition read: ``actor`` holds ``requisitions.view``.

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


def enter(db: DbTarget, project: str, actor: str) -> tuple[str, Viewer]:
    """Check the actor, check the view word on the project, and return the scope and the viewer."""
    scope = scope_of(project)
    checked = acting(db, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        require_view(uow, scope, checked)
    return scope, session_viewer(db)


def record_id_of(uow: UnitOfWork, scope: str, number: str, viewer: Viewer) -> str:
    """The id of the record ``number`` names, as ``viewer`` may read it (``--for``).

    A hidden record answers as one that does not exist: `error: no record <number>`.
    """
    with cf.use_viewer(viewer):
        row = get_record(uow, scope, number)
    if row is None:
        fail(f"no record {number}")
    return str(row["id"])


def serves_key(uow: UnitOfWork, record_id: str | None, viewer: Viewer) -> str | None:
    """The key of the record a requisition serves; None when it serves none or is unreadable."""
    if record_id is None:
        return None
    with cf.use_viewer(viewer):
        row: dict[str, Any] | None = get_record_by_id(uow, record_id)
    return None if row is None else str(row["key"])


def _kind_check(kind: str | None) -> None:
    if kind is not None and kind not in KINDS:
        raise typer.BadParameter(f"must be one of {', '.join(KINDS)}", param_hint="'--kind'")


# --- requisitions ---------------------------------------------------------------------------------


def req_ls(
    ctx: typer.Context,
    project: Project,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="Only this kind: labor, material, general, scaffold."),
    ] = None,
    state: Annotated[str | None, typer.Option("--state", help="Only this state.")] = None,
    requester: Annotated[
        str | None, typer.Option("--requester", help="Only this requester (user:X).")
    ] = None,
    for_number: Annotated[
        str | None, typer.Option("--for", help="Only requisitions that serve this IWP number.")
    ] = None,
    actor: Actor = DEV_ACTOR,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows to list (default 200).")
    ] = LIST_LIMIT,
) -> None:
    """List the requisitions of the project by key.

    `requisitions: <n>`, then `<key>  <kind>  <state>  <priority>  <need by or ->  <requester>
    <subject>` for each, the subject cut to 50 characters. An unknown or hidden `--for` record is
    `error: no record <number>`.
    """
    _kind_check(kind)
    db: DbTarget = ctx.obj
    scope, viewer = enter(db, project, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        for_id = None if for_number is None else record_id_of(uow, scope, for_number, viewer)
        found = views.requisition_list(
            uow.conn(),
            scope,
            kind=kind,
            state=state,
            requester=requester,
            for_record=for_id,
            limit=limit,
            viewer=viewer,
        )
    typer.echo(f"requisitions: {len(found)}")
    for r in found:
        typer.echo(
            f"{r.key}  {cell(r.kind)}  {cell(r.state)}  {cell(r.priority)}  {cell(r.need_by)}  "
            f"{cell(r.requester)}  {cell(r.subject, 50)}"
        )


def req_show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The requisition key.")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show one requisition with its kind fields and its work order.

    Lines: `requisition <key>`, `kind`, `state`, `subject`, `priority`, `need by`, `requester`,
    `approved by`, `serves <IWP key or ->`, then `  <name>  <value>` for each kind field in
    name order, then `work order <key or ->`. A missing or hidden requisition is
    `error: no requisition <key>`.
    """
    db: DbTarget = ctx.obj
    scope, viewer = enter(db, project, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.requisition_detail(uow.conn(), scope, number, viewer=viewer)
        serves = None if d is None else serves_key(uow, d.row.for_record_id, viewer)
    if d is None:
        fail(f"no requisition {number}")
    lines = [
        f"requisition {d.row.key}",
        f"kind {cell(d.row.kind)}",
        f"state {cell(d.row.state)}",
        f"subject {cell(d.row.subject, 1000)}",
        f"priority {cell(d.row.priority)}",
        f"need by {cell(d.row.need_by)}",
        f"requester {cell(d.row.requester)}",
        f"approved by {cell(d.row.approved_by)}",
        f"serves {cell(serves)}",
    ]
    lines.extend(f"  {name}  {cell(d.fields[name], 1000)}" for name in sorted(d.fields))
    lines.append(f"work order {cell(None if d.work_order is None else d.work_order.key)}")
    for line in lines:
        typer.echo(line)


# --- work orders ----------------------------------------------------------------------------------


def wo_ls(
    ctx: typer.Context,
    project: Project,
    state: Annotated[str | None, typer.Option("--state", help="Only this state.")] = None,
    assigned: Annotated[
        str | None, typer.Option("--assigned", help="Only work orders assigned to this (user:X).")
    ] = None,
    actor: Actor = DEV_ACTOR,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows to list (default 200).")
    ] = LIST_LIMIT,
) -> None:
    """List the work orders of the project by key.

    `work orders: <n>`, then `<key>  <work kind>  <state>  <assigned or ->  <planned start or ->
    <planned finish or ->  <hours planned or ->` for each.
    """
    db: DbTarget = ctx.obj
    scope, viewer = enter(db, project, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.work_order_list(
            uow.conn(), scope, state=state, assigned_to=assigned, limit=limit, viewer=viewer
        )
    typer.echo(f"work orders: {len(found)}")
    for w in found:
        typer.echo(
            f"{w.key}  {cell(w.work_kind)}  {cell(w.state)}  {cell(w.assigned_to)}  "
            f"{cell(w.planned_start)}  {cell(w.planned_finish)}  {cell(w.hours_planned)}"
        )


def wo_show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The work order key.")],
    project: Project,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show one work order with the requisition it belongs to.

    Lines: `work order <key>`, `requisition <key>`, `kind`, `state`, `assigned`,
    `planned <start> to <finish>`, `actual <start> to <finish>`, and
    `hours <planned> planned  <actual> actual`. A missing or hidden work order is
    `error: no work order <key>`.
    """
    db: DbTarget = ctx.obj
    scope, viewer = enter(db, project, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.work_order_detail(uow.conn(), scope, number, viewer=viewer)
    if d is None:
        fail(f"no work order {number}")
    w = d.row
    lines = [
        f"work order {w.key}",
        f"requisition {cell(d.requisition_key)}",
        f"kind {cell(w.work_kind)}",
        f"state {cell(w.state)}",
        f"assigned {cell(w.assigned_to)}",
        f"planned {cell(w.planned_start)} to {cell(w.planned_finish)}",
        f"actual {cell(w.actual_start)} to {cell(w.actual_finish)}",
        f"hours {cell(w.hours_planned)} planned  {cell(w.hours_actual)} actual",
    ]
    for line in lines:
        typer.echo(line)


def register(req_app: typer.Typer, wo_app: typer.Typer) -> None:
    """Add the reads (`ls`, `show`) to the ``req`` and ``wo`` groups."""
    for function, name in ((req_ls, "ls"), (req_show, "show")):
        req_app.command(name)(function)
    for function, name in ((wo_ls, "ls"), (wo_show, "show")):
        wo_app.command(name)(function)
