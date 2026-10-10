"""The `tl archive` group: sign key, seal the ledger into segments, verify them (brief 24.3, 24.5).

Each subcommand parses options, makes calls into `tl_core.archive` and `tl_adapters`, and prints.
The sealing and verification rules live in `tl_core.archive`. STUB (P0-I7-T03): the three commands
raise `NotImplementedError`. Remove this sentence when done.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from tl_adapters.db import DbTarget, is_postgres
from tl_core.archive import DEFAULT_KEY_PATH, Signer, load_signer

app = typer.Typer(help="Seal and verify the ledger archive.", no_args_is_help=True)

DEFAULT_ARCHIVE_DIR = Path("dev/data/archive")

ArchiveOption = Annotated[
    Path,
    typer.Option(
        "--archive",
        envvar="TL_ARCHIVE_DIR",
        help="Archive directory (independent of the database and the object store).",
    ),
]
KeyOption = Annotated[
    Path,
    typer.Option("--key", envvar="TL_ARCHIVE_KEY", help="Ed25519 signing key (PEM)."),
]
PublicKeyOption = Annotated[
    Path | None,
    typer.Option(
        "--public-key",
        envvar="TL_ARCHIVE_PUBLIC_KEY",
        help="Public key (hex file or PEM). Default: dev/data/archive-signing.pub.",
    ),
]
DbOption = Annotated[
    str | None,
    typer.Option("--db", help="SQLite file or postgresql:// URL. Default: the root --db."),
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


def _target(ctx: typer.Context, db: str | None) -> DbTarget:
    """The database to read: ``--db`` if given, else the root ``--db`` (a SQLite path)."""
    target: DbTarget = db if db is not None else ctx.obj
    if not is_postgres(target) and not Path(target).is_file():
        _fail(f"no ledger at {target}: run `tl init`")
    return target


def _signer(key: Path) -> Signer:
    try:
        return load_signer(key)
    except FileNotFoundError:
        _fail(f"no signing key at {key}: run `tl archive keygen`")
    except ValueError as exc:
        _fail(str(exc))


@app.command("keygen")
def keygen(
    key: KeyOption = DEFAULT_KEY_PATH,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing key (old segments stop verifying).")
    ] = False,
) -> None:
    """Create the Ed25519 signing key pair (dev key; production custody is a later decision)."""
    raise NotImplementedError


@app.command("seal")
def seal(
    ctx: typer.Context,
    archive: ArchiveOption = DEFAULT_ARCHIVE_DIR,
    key: KeyOption = DEFAULT_KEY_PATH,
    db: DbOption = None,
    max_events: Annotated[
        int, typer.Option("--max-events", min=1, help="Most events in one segment.")
    ] = 10_000,
) -> None:
    """Seal every event not yet archived into signed segments."""
    raise NotImplementedError


@app.command("verify")
def verify(
    archive: ArchiveOption = DEFAULT_ARCHIVE_DIR,
    public_key: PublicKeyOption = None,
    db: Annotated[
        str | None,
        typer.Option("--db", help="Also check this SQLite file or postgresql:// URL."),
    ] = None,
    deep: Annotated[
        bool, typer.Option("--deep", help="Also check each Parquet file against its NDJSON.")
    ] = False,
    all_issues: Annotated[
        bool, typer.Option("--all", help="Report one divergence per segment, not only the first.")
    ] = False,
    expect_last_seq: Annotated[
        int | None,
        typer.Option(
            "--expect-last-seq", help="The archive must reach this seq (recorded at seal time)."
        ),
    ] = None,
    expect_manifest: Annotated[
        str | None,
        typer.Option(
            "--expect-manifest",
            help="This manifest SHA-256 (recorded at seal time) must be in the chain.",
        ),
    ] = None,
) -> None:
    """Verify signatures, the manifest chain, every event hash and the per-scope chains."""
    raise NotImplementedError
