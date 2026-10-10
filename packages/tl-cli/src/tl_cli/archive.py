"""The `tl archive` group: sign key, seal the ledger into segments, verify them (brief 24.3, 24.5).

Each subcommand parses options, makes calls into `tl_core.archive` and `tl_adapters`, and prints.
The sealing and verification rules live in `tl_core.archive`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from tl_adapters.archivestore import FsArchiveStore
from tl_adapters.db import DbTarget, display_target, is_postgres, make_engine, read_tx
from tl_core.archive import (
    DEFAULT_KEY_PATH,
    ArchiveError,
    Signer,
    load_public_key,
    load_signer,
    public_key_path,
    seal_segment,
    summarize_archive,
    verify_archive,
    write_keypair,
)
from tl_core.archive.segments import segment_name

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
    try:
        signer = write_keypair(key, overwrite=force)
    except FileExistsError as exc:
        _fail(str(exc))
    typer.echo(f"wrote private key {key} (key id {signer.key_id})")
    typer.echo(f"wrote public key {public_key_path(key)}")


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
    target = _target(ctx, db)
    signer = _signer(key)
    store = FsArchiveStore(archive)
    engine = make_engine(target)
    sealed = 0
    try:
        while True:
            with read_tx(engine) as conn:
                manifest = seal_segment(conn, store, signer, max_events=max_events)
            if manifest is None:
                break
            sealed += 1
            name = segment_name(manifest.first_seq, manifest.last_seq)
            typer.echo(
                f"sealed segment {name} ({manifest.event_count} events, "
                f"seq {manifest.first_seq}..{manifest.last_seq})"
            )
        summary = summarize_archive(store)
    except ArchiveError as exc:
        _fail(str(exc))
    finally:
        engine.dispose()
    if sealed == 0:
        typer.echo(f"nothing new to seal; archive is at seq {summary.last_seq}")
    else:
        typer.echo(f"sealed {sealed} segments; archive is at seq {summary.last_seq}")
    if summary.last_manifest_sha256 is not None:
        typer.echo(
            f"record outside the archive: last_seq {summary.last_seq} "
            f"manifest_sha256 {summary.last_manifest_sha256}"
        )


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
    if not archive.is_dir():
        _fail(f"no archive at {archive}")
    store = FsArchiveStore(archive)
    key_path = public_key if public_key is not None else public_key_path(DEFAULT_KEY_PATH)
    try:
        pub_bytes = load_public_key(key_path)
    except (FileNotFoundError, ValueError) as exc:
        _fail(f"cannot read the public key {key_path}: {exc}")
    if db is not None and not is_postgres(db) and not Path(db).is_file():
        _fail(f"no ledger at {db}")
    engine = make_engine(db) if db is not None else None
    try:
        if engine is None:
            issues = verify_archive(
                store,
                public_key=pub_bytes,
                deep=deep,
                stop_at_first=not all_issues,
                expect_last_seq=expect_last_seq,
                expect_manifest_sha256=expect_manifest,
            )
        else:
            with read_tx(engine) as conn:
                issues = verify_archive(
                    store,
                    public_key=pub_bytes,
                    conn=conn,
                    deep=deep,
                    stop_at_first=not all_issues,
                    expect_last_seq=expect_last_seq,
                    expect_manifest_sha256=expect_manifest,
                )
        if issues:
            for issue in issues:
                segment = issue.segment or "-"
                seq = "-" if issue.seq is None else str(issue.seq)
                typer.echo(f"divergence: {issue.kind} segment={segment} seq={seq}: {issue.detail}")
            raise typer.Exit(code=1)
        summary = summarize_archive(store)
    except ArchiveError as exc:
        _fail(str(exc))
    finally:
        if engine is not None:
            engine.dispose()
    if summary.segments == 0:
        typer.echo("verified 0 segments (the archive is empty)")
    else:
        typer.echo(
            f"verified {summary.segments} segments, seq 1..{summary.last_seq} "
            f"({summary.events} events)"
        )
    if db is not None:
        typer.echo(f"database {display_target(db)} agrees up to seq {summary.last_seq}")
