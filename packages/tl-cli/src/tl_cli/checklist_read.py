"""`tl checklist ls|show`: the checklist reads (P2-INSP-T05).

None of these writes anything. Every verb first checks the access word `quality.view` on the
project for the invoking actor (``punch_read.enter``), before any checklist is read; a refusal is
`error: forbidden: ...`. The reads go through ``tl_mod_quality.insp_views`` with the session's
viewer, so a hidden checklist answers the same as a missing key. The CLI prints the fields the
views return and queries nothing itself. ``register(app)`` adds the two commands to the
``checklist`` group.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_quality import insp_views

from tl_cli.derive_support import DEV_ACTOR, cell, fail, scope_of, service_errors
from tl_cli.punch_read import Actor, enter

#: The default and the most rows the list prints.
LIST_LIMIT = 200


def _yes_no(value: Any) -> str:
    return "yes" if value else "no"


def checklist_ls(
    ctx: typer.Context,
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
    state: Annotated[
        str | None, typer.Option("--state", help="Draft, Published or Retired.")
    ] = None,
    discipline: Annotated[
        str | None, typer.Option("--discipline", help="Only this discipline.")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most rows to list (default 200).")
    ] = LIST_LIMIT,
) -> None:
    """List the checklists of the project by key.

    `checklists: <shown> of <total>`, then `<key>  <title>  <discipline>  version <v>  <state>
    <questions> questions` for each, `-` for no discipline, the title cut to 50.
    """
    if state is not None and state not in insp_views.CHECKLIST_STATES:
        allowed = ", ".join(insp_views.CHECKLIST_STATES)
        raise typer.BadParameter(f"must be one of {allowed}", param_hint="'--state'")
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = insp_views.checklist_list(
            uow.conn(),
            scope,
            state=state,
            discipline=discipline,
            limit=limit,
            viewer=viewer,
        )
    typer.echo(f"checklists: {len(page.rows)} of {page.total}")
    for r in page.rows:
        typer.echo(
            f"{r.key}  {cell(r.title, 50)}  {cell(r.discipline)}  version {r.version}  "
            f"{r.state}  {r.question_count} questions"
        )


def checklist_show(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The checklist key, for example P123-CHK-0001.")],
    project: Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Show one checklist and its questions.

    An absent or hidden one is `error: no checklist <key>`."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = insp_views.checklist_detail(uow.conn(), scope, key, viewer=viewer)
    if found is None:
        fail(f"no checklist {key}")
    r = found.row
    lines = [
        f"checklist {r.key}",
        f"title  {cell(r.title, 200)}",
        f"discipline  {cell(r.discipline)}",
        f"version  {r.version}",
        f"state  {r.state}",
        f"supersedes  {cell(found.supersedes_key)}",
        f"published  {cell(found.published_by, 120)}  {cell(found.published_on)}",
        f"retired  {cell(found.retired_on)}",
        "id  text  kind  required  fails when",
    ]
    for line in lines:
        typer.echo(line)
    for q in found.questions:
        typer.echo(
            f"{cell(q.get('id'), 16)}  {cell(q.get('text'), 60)}  {cell(q.get('kind'), 16)}  "
            f"{_yes_no(q.get('required'))}  {cell(q.get('fails_when'), 16)}"
        )


def register(app: typer.Typer) -> None:
    """Add the checklist reads (`ls`, `show`) to the `checklist` group."""
    for function, name in ((checklist_ls, "ls"), (checklist_show, "show")):
        app.command(name)(function)
