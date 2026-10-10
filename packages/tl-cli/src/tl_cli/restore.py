"""`tl restore`: rebuild an empty database from a ledger archive alone (brief 24.4).

The command parses options, makes one call into `tl_adapters.restore`, and prints. It restores
into a new SQLite file or an empty Postgres schema, never into a database that has events.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from tl_adapters.archivestore import FsArchiveStore
from tl_adapters.db import display_target, is_postgres
from tl_adapters.restore import restore_from_archive
from tl_core.archive import (
    DEFAULT_KEY_PATH,
    ArchiveError,
    RestoreError,
    load_public_key,
    public_key_path,
)


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
    if not from_archive.is_dir():
        _fail(f"no archive at {from_archive}")
    key_path = public_key if public_key is not None else public_key_path(DEFAULT_KEY_PATH)
    try:
        public = load_public_key(key_path)
    except (FileNotFoundError, ValueError) as exc:
        _fail(f"cannot read the public key {key_path}: {exc}")
    if not is_postgres(db):
        Path(db).parent.mkdir(parents=True, exist_ok=True)
    try:
        result = restore_from_archive(FsArchiveStore(from_archive), db, public_key=public)
    except RestoreError as exc:
        if exc.issue is not None:
            issue = exc.issue
            seq = "-" if issue.seq is None else issue.seq
            typer.echo(
                f"divergence: {issue.kind} segment={issue.segment or '-'} seq={seq}: {issue.detail}"
            )
        _fail(str(exc))
    except ArchiveError as exc:
        _fail(str(exc))
    typer.echo(
        f"restored {result.events} events from {result.segments} segments into "
        f"{display_target(db)} (last seq {result.last_seq})"
    )
    typer.echo(
        f"verify {result.verify_seconds:.2f}s, insert {result.insert_seconds:.2f}s, "
        f"rebuild {result.rebuild_seconds:.2f}s, total {result.total_seconds:.2f}s"
    )
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)
