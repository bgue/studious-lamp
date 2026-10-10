"""`tl restore`: rebuild an empty database from a ledger archive alone (brief 24.4).

The command parses options, makes one call into `tl_adapters.restore`, and prints. It restores
into a new SQLite file or an empty Postgres schema, never into a database that has events.
STUB (P0-I7-T04): `restore` raises `NotImplementedError`. Remove this sentence when done.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def restore(
    from_archive: Annotated[
        Path,
        typer.Option(
            "--from-archive", envvar="TL_ARCHIVE_DIR", help="Archive directory to restore from."
        ),
    ],
    db: Annotated[
        str,
        typer.Option("--db", help="Empty target: a new SQLite file or a postgresql:// URL."),
    ],
    public_key: Annotated[
        Path | None,
        typer.Option(
            "--public-key",
            envvar="TL_ARCHIVE_PUBLIC_KEY",
            help="Public key (hex file or PEM). Default: dev/data/archive-signing.pub.",
        ),
    ] = None,
) -> None:
    """Verify the archive, replay it into an empty database, rebuild projections, verify again."""
    raise NotImplementedError
