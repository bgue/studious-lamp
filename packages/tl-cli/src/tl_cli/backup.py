"""The `tl backup` group: database snapshots (brief 24.3).

Each subcommand parses options, makes one call into `tl_adapters`, and prints. STUB (P0-I7-T02):
the `sqlite` command raises `NotImplementedError`. Remove this paragraph when done.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

app = typer.Typer(help="Back up the database.", no_args_is_help=True)


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@app.command("sqlite")
def sqlite_backup(
    ctx: typer.Context,
    to: Annotated[
        Path,
        typer.Option("--to", help="Snapshot file to create. It must not exist yet."),
    ],
) -> None:
    """Take an online snapshot of the SQLite ledger (`--db`) into a new file."""
    raise NotImplementedError
