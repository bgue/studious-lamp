"""The `tl backup` group: database snapshots (brief 24.3).

Each subcommand parses options, makes one call into `tl_adapters`, and prints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from tl_adapters.db import DbTarget, is_postgres
from tl_adapters.sqlite.backup import BackupError, backup_database

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
    target: DbTarget = ctx.obj
    if is_postgres(target):
        _fail(
            "tl backup sqlite takes a SQLite ledger; for Postgres use pgBackRest "
            "(docs/runbooks/pgbackrest-restore.md) or `tl archive seal`"
        )
    source = Path(target)
    try:
        result = backup_database(source, to)
    except BackupError as error:
        _fail(str(error))
    typer.echo(
        f"backed up {result.head_seq} events from {result.source} to {result.dest} "
        f"({result.bytes} bytes, sha256 {result.sha256})"
    )
