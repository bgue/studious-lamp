"""`tl insp ls|show|export`: the inspection reads (P2-INSP-T04).

None of these writes anything. Every verb first checks the access word `quality.view` on the
project for the invoking actor (``punch_read.enter``), before any inspection is read; a refusal is
`error: forbidden: ...`. The reads go through ``tl_mod_quality.insp_views`` with the session's
viewer, so a hidden inspection (through its subject) is absent from a list, its total and a show,
and answers the same as a missing key. The CLI prints the fields the views return and queries
nothing itself. ``register(app)`` adds the three commands to the ``insp`` group.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_mod_quality import insp_views
from tl_mod_quality.names import POINTS

from tl_cli.derive_support import DEV_ACTOR, cell, fail, scope_of, service_errors
from tl_cli.punch_read import Actor, enter

#: The default and the most rows the list prints.
LIST_LIMIT = 200
#: The label column of the property lines (the longest label plus two spaces).
LABEL_WIDTH = 16
EMPTY = "—"


def _val(value: object) -> str:
    """A value of a property line or a table cell: ``—`` for none (tui-layout: never ``-``)."""
    if value is None or value == "":
        return EMPTY
    return " ".join(str(value).split())


def _states(state: str | None) -> None:
    if state is not None and state not in insp_views.INSPECTION_STATES:
        raise typer.BadParameter(
            f"must be one of {', '.join(insp_views.INSPECTION_STATES)}", param_hint="'--state'"
        )


def _points(point: str | None) -> None:
    if point is not None and point not in POINTS:
        raise typer.BadParameter(f"must be one of {', '.join(POINTS)}", param_hint="'--point'")


def insp_ls(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
    state: Annotated[
        str | None,
        typer.Option("--state", help="Planned, Scheduled, Done, Verified or Cancelled."),
    ] = None,
    point: Annotated[
        str | None, typer.Option("--point", help="hold, witness, review or surveillance.")
    ] = None,
    area: Annotated[str | None, typer.Option("--area", help="Only this area.")] = None,
    inspector: Annotated[str | None, typer.Option("--inspector", help="Only this user:X.")] = None,
    subject: Annotated[
        str | None, typer.Option("--subject", help="Only inspections of this record key.")
    ] = None,
    for_key: Annotated[
        str | None, typer.Option("--for", help="Only inspections for this work package key.")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows to list (default 200).")
    ] = LIST_LIMIT,
) -> None:
    """List the inspections of the project by key.

    `<key>  <title>  <state>  <point>  <subject>  <for>  <inspector>  <scheduled>  <result>` for
    each, `-` for none; the last line is `<listed> of <total>`.
    """
    _states(state)
    _points(point)
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = insp_views.inspection_list(
            uow.conn(),
            scope,
            state=state,
            point=point,
            area=area,
            inspector=inspector,
            subject_key=subject,
            for_key=for_key,
            limit=limit,
            viewer=viewer,
        )
    for r in page.rows:
        typer.echo(
            f"{r.key}  {cell(r.title, 40)}  {r.state}  {r.point}  {cell(r.subject_key)}  "
            f"{cell(r.for_key)}  {cell(r.inspector, 120)}  {cell(r.scheduled_for)}  "
            f"{cell(r.result)}"
        )
    typer.echo(f"{len(page.rows)} of {page.total}")


def insp_show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The inspection key, for example P123-INS-0001.")],
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show one inspection. An absent or hidden inspection is `error: no inspection <key>`."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = insp_views.inspection_detail(uow.conn(), scope, key, viewer=viewer)
    if found is None:
        fail(f"no inspection {key}")
    r = found.row
    properties = [
        ("Point", r.point),
        ("Subject", r.subject_key),
        ("For", r.for_key),
        ("Area", r.area),
        ("Inspector", r.inspector),
        ("Planned", r.planned_on),
        ("Scheduled", r.scheduled_for),
        ("Done", r.done_on),
        ("Result", r.result),
        ("Checklist", found.checklist_key),
        ("Checklist version", found.checklist_version),
        ("Recorded by", found.recorded_by),
        ("Verified by", found.verified_by),
        ("Verified on", found.verified_on),
        ("Reinspection of", found.reinspection_of_key),
        ("Cancel reason", found.cancel_reason),
        ("Note", found.note),
        ("Version", found.version),
    ]
    typer.echo(f"{r.key} · {_val(r.title)}")
    typer.echo(r.state)
    for label, value in properties:
        typer.echo(f"{label:<{LABEL_WIDTH}}{_val(value)}")
    typer.echo("")
    typer.echo("Answers")
    if not found.answers:
        typer.echo("No answers")
    else:
        table = [
            (_val(a.get("q")), _val(a.get("value")), _val(a.get("note"))) for a in found.answers
        ]
        header = ("Question", "Value", "Note")
        widths = [max(len(row[i]) for row in [header, *table]) for i in range(3)]
        for row in [header, *table]:
            typer.echo("  ".join(cellv.ljust(widths[i]) for i, cellv in enumerate(row)).rstrip())
    typer.echo("")
    if found.punch_keys:
        typer.echo(f"{'Punch items':<{LABEL_WIDTH}}{', '.join(found.punch_keys)}")
    else:
        typer.echo(f"{'Punch items':<{LABEL_WIDTH}}{EMPTY}")


def insp_export(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    format_: Annotated[str, typer.Option("--format", help="csv or jsonl.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Export the visible inspections of the project, one row each, as csv or jsonl."""
    if format_ not in insp_views.EXPORT_FORMATS:
        raise typer.BadParameter(
            f"must be one of {', '.join(insp_views.EXPORT_FORMATS)}", param_hint="'--format'"
        )
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer: cf.Viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = insp_views.inspection_list(
            uow.conn(), scope, limit=insp_views.MAX_LIMIT, viewer=viewer
        )
    typer.echo(insp_views.export_rows(page.rows, format_), nl=False)


def register(app: typer.Typer) -> None:
    """Add the inspection reads (`ls`, `show`, `export`) to the `insp` group."""
    for function, name in ((insp_ls, "ls"), (insp_show, "show"), (insp_export, "export")):
        app.command(name)(function)
