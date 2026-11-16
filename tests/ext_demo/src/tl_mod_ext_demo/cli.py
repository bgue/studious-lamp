"""The CLI group of the ext_demo module (ADR-0029).

The hook ref `tl_mod_ext_demo.cli:ext_demo_app` names the group `ext_demo`.
An attribute `<x>_app` gives the group `<x>`.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_cli.derive_support import DEV_ACTOR, SOURCE, acting, fail, scope_of, service_errors
from tl_cli.session import require_command, session_viewer

from . import MSG_NOT_FOUND
from .commands import ExtDemoAddNote, handle_add_note
from .views import get_note

ext_demo_app = typer.Typer(no_args_is_help=True)

Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]


@ext_demo_app.command()
def get(ctx: typer.Context, key: str, project: Project) -> None:
    """Print one note. A missing and a hidden note print the same text and exit 1."""
    db: DbTarget = ctx.obj
    viewer = session_viewer(db)
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = get_note(uow.conn(), scope_of(project), key, viewer=viewer)
    if found is None:
        fail(MSG_NOT_FOUND)
    typer.echo(f"{found.key}  {found.title}")
    typer.echo(found.body)


@ext_demo_app.command()
def add(
    ctx: typer.Context,
    key: str,
    project: Project,
    title: Annotated[str, typer.Option("--title", help="The note's title.")],
    body: Annotated[str, typer.Option("--body", help="The note's text.")],
    restricted: Annotated[
        bool, typer.Option("--restricted", help="Class it restricted (default internal).")
    ] = False,
    actor: Annotated[str, typer.Option("--actor", help="Actor recorded on events.")] = DEV_ACTOR,
) -> None:
    """Add a note; prints `added <key>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    command = ExtDemoAddNote(
        actor=who,
        source=SOURCE,
        scope=scope_of(project),
        key=key,
        title=title,
        body=body,
        note_class="restricted" if restricted else "internal",
    )
    with service_errors(), open_uow(db) as uow:
        require_command(uow, command)
        result = handle_add_note(uow, command)
    typer.echo(f"added {result.key}")
