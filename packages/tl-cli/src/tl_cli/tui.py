"""`tl tui`: the terminal UI, embedded on the dev ledger or remote against an API (P0-I4).

A thin wrapper over ``tl_tui.main.run``. Embedded is the default: the TUI shows its sign-in screen,
unless ``tl login`` already signed in to this ledger, whose session it then uses. ``--remote URL``
runs the same screens over HTTP and SSE and signs in to the server on the TUI's own screen, or
takes a token (``--token``, or ``TL_TOKEN`` so the token stays out of the process list).
"""

from __future__ import annotations

from typing import Annotated

import typer

from tl_cli.session import current_principal


def tui(
    ctx: typer.Context,
    remote: Annotated[
        str | None,
        typer.Option("--remote", envvar="TL_REMOTE", help="API URL; default is embedded."),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            envvar="TL_TOKEN",
            help="Dev token for --remote; prefer TL_TOKEN "
            "(command-line arguments are visible in ps).",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", envvar="TL_PROJECT", help="Project id (default P123)."),
    ] = None,
    actor: Annotated[
        str | None, typer.Option("--actor", help="Remote: the name the header shows.")
    ] = None,
    record_type: Annotated[
        str | None,
        typer.Option(
            "--type", envvar="TL_TYPE", help="Record type of the grid (default core.Record)."
        ),
    ] = None,
) -> None:
    """Open the TUI. Embedded unless --remote is given."""
    from tl_tui import main as tui_main
    from tl_tui.sign_in import SignedIn

    signed_in = None
    principal = current_principal(ctx.obj) if remote is None else None
    if principal is not None:  # `tl login` signed in to this ledger: do not ask again
        name = principal.actor.partition(":")[2]
        signed_in = SignedIn(actor=principal.actor, username=name, roles=tuple(principal.roles))
    try:
        tui_main.run(
            remote=remote,
            token=token,
            db=ctx.obj,
            project=project,
            actor=actor,
            record_type=record_type,
            signed_in=signed_in,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
