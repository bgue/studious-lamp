"""The `tl lake` group: sync the ledger into the DuckLake copy, and query it (brief 28).

Each subcommand parses options, makes one call into `tl_lake`, and prints. Rules (what a sync
copies, what a query may read) live in `tl_lake`.

STUB (P0-I7-T20): the five commands below raise NotImplementedError. The group, the `--lake-dir`
option, the helpers and the registration in `main.py` exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from sqlalchemy import Connection
from tl_adapters.sqlite.engine import make_engine
from tl_lake import GuardError, LakeConfig, LakeError, read_snapshot

app = typer.Typer(help="Sync the ledger into the lake and query it.", no_args_is_help=True)

_CALLER = "cli"


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@app.callback()
def lake_root(
    ctx: typer.Context,
    lake_dir: Annotated[
        str | None,
        typer.Option(
            "--lake-dir",
            envvar="TL_LAKE_DIR",
            help="Lake directory (catalog and Parquet files). Default: ./dev/data/lake.",
        ),
    ] = None,
) -> None:
    """Lake commands."""
    ctx.meta["lake_config"] = LakeConfig.at(lake_dir)


def _config(ctx: typer.Context) -> LakeConfig:
    config: LakeConfig = ctx.meta["lake_config"]
    return config


@contextmanager
def _ledger_snapshot(ctx: typer.Context) -> Iterator[Connection]:
    """The ledger as one read snapshot. The only place the CLI opens the database for the lake."""
    db: Path = ctx.obj
    if not db.exists():
        _fail(f"no ledger at {db}: run `tl init`")
    engine = make_engine(db)
    try:
        with read_snapshot(engine) as conn:
            yield conn
    finally:
        engine.dispose()


@contextmanager
def _lake_errors() -> Iterator[None]:
    """`error: refused: <why>` for a guard refusal, `error: <message>` for any other lake error."""
    try:
        yield
    except GuardError as exc:
        _fail(f"refused: {exc}")
    except LakeError as exc:
        _fail(str(exc))


@app.command("sync")
def sync(ctx: typer.Context) -> None:
    """Copy new ledger events and changed records into the lake: one snapshot per sync."""
    raise NotImplementedError("STUB (P0-I7-T20)")


@app.command("rebuild")
def rebuild(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm deleting the lake's files.")] = False,
) -> None:
    """Delete the lake's catalog and data files and load everything again from the ledger."""
    raise NotImplementedError("STUB (P0-I7-T20)")


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Show the ledger seq the lake reflects, the sync count and the row count of each table."""
    raise NotImplementedError("STUB (P0-I7-T20)")


@app.command("tables")
def tables(ctx: typer.Context) -> None:
    """List the lake's tables and columns."""
    raise NotImplementedError("STUB (P0-I7-T20)")


@app.command("query")
def query(
    ctx: typer.Context,
    sql: Annotated[str, typer.Argument(help="One SELECT over the lake tables.")],
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return.")] = 100,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON object.")] = False,
) -> None:
    """Run a read-only query through the lake_query guard."""
    raise NotImplementedError("STUB (P0-I7-T20)")
