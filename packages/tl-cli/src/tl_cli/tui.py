"""`tl tui`: the terminal UI, embedded on the dev ledger or remote against an API (P0-I4).

A thin wrapper over ``tl_tui.main.run``. Embedded is the default. ``--remote URL`` with a dev token
(``--token``, or ``TL_TOKEN`` so the token stays out of the process list) runs the same screens
over HTTP and SSE.
"""

from __future__ import annotations

from typing import Annotated

import typer


def tui(
    ctx: typer.Context,
    remote: Annotated[
        str | None,
        typer.Option("--remote", envvar="TL_REMOTE", help="API URL; default is embedded."),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", envvar="TL_TOKEN", help="Dev token for --remote."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", envvar="TL_PROJECT", help="Project id (default P123)."),
    ] = None,
    actor: Annotated[
        str | None, typer.Option("--actor", help="Remote: the name the header shows.")
    ] = None,
) -> None:
    """Open the TUI. Embedded unless --remote is given."""
    from tl_tui import main as tui_main

    try:
        tui_main.run(remote=remote, token=token, db=ctx.obj, project=project, actor=actor)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
