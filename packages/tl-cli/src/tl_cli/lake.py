"""The `tl lake` group: sync the ledger into the DuckLake copy, and query it (brief 28).

Each subcommand parses options, makes one call into `tl_lake`, and prints. Rules (what a sync
copies, what a query may read) live in `tl_lake`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from sqlalchemy import Connection
from sqlalchemy.exc import SQLAlchemyError
from tl_adapters.sqlite.engine import make_engine
from tl_core.services.errors import ServiceError
from tl_core.settings.resolver import value_of
from tl_core.settings.values import duration_seconds
from tl_lake import (
    GuardError,
    LakeConfig,
    LakeError,
    LakeQueryService,
    SyncResult,
    describe_lake,
    lake_status,
    read_snapshot,
    sync_lake,
)

app = typer.Typer(help="Sync the ledger into the lake and query it.", no_args_is_help=True)

_CALLER = "cli"
INTERVAL_KEY = "lake.sync.interval"
#: Seconds to wait when the interval setting cannot be read and none was read before.
DEFAULT_INTERVAL_S = 300.0
#: The wait between watch runs; the tests replace it.
_sleep: Callable[[float], None] = time.sleep


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


def _print_sync(result: SyncResult) -> None:
    if result.up_to_date:
        typer.echo(f"lake is up to date as of seq {result.last_seq}")
        return
    typer.echo(
        f"synced seq {result.first_seq}..{result.last_seq} ({result.events} events) "
        f"in snapshot {result.snapshot_id}"
    )
    counts = ", ".join(f"{table} {rows}" for table, rows in result.silver_rows.items())
    typer.echo(f"silver rows: {counts}")


def watch_loop(
    run_once: Callable[[], None],
    interval: Callable[[], float],
    sleep: Callable[[float], None],
    max_runs: int | None = None,
) -> int:
    """Call ``run_once``, then wait ``interval()`` seconds, again and again; return the run count.

    The interval is read again before every wait, so a changed setting applies to the next wait.
    If it cannot be read (the ledger is busy, the value is bad) the last one read is used, or
    ``DEFAULT_INTERVAL_S`` before the first. A run that raises ``GuardError`` or ``LakeError``
    prints ``error: <message>`` to standard error and the loop goes on. With ``max_runs`` the
    loop stops after that many runs, without a wait after the last one.
    """
    runs = 0
    wait = DEFAULT_INTERVAL_S
    while True:
        try:
            run_once()
        except (GuardError, LakeError) as exc:
            typer.echo(f"error: {exc}", err=True)
        runs += 1
        if max_runs is not None and runs >= max_runs:
            return runs
        try:
            wait = interval()
        except (ServiceError, SQLAlchemyError, ValueError, OSError):
            pass  # keep the last good interval
        sleep(wait)


def _interval_seconds(ctx: typer.Context) -> float:
    """``lake.sync.interval`` in force now, in seconds.

    Read in a fresh read snapshot of the ledger: the company value, else the default.
    """
    with _ledger_snapshot(ctx) as conn:
        value = value_of(conn, INTERVAL_KEY)
    return duration_seconds(str(value))


@app.command("sync")
def sync(
    ctx: typer.Context,
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            help="Keep syncing, waiting `lake.sync.interval` between syncs, until interrupted.",
        ),
    ] = False,
    max_runs: Annotated[
        int | None,
        typer.Option("--max-runs", min=1, hidden=True, help="Stop a watch after this many syncs."),
    ] = None,
) -> None:
    """Copy new ledger events and changed records into the lake: one snapshot per sync."""
    if max_runs is not None and not watch:
        _fail("--max-runs only applies with --watch")
    if not watch:
        with _lake_errors(), _ledger_snapshot(ctx) as conn:
            result = sync_lake(_config(ctx), conn)
        _print_sync(result)
        return

    def once() -> None:
        with _ledger_snapshot(ctx) as conn:
            result = sync_lake(_config(ctx), conn)
        _print_sync(result)

    try:
        watch_loop(once, lambda: _interval_seconds(ctx), lambda s: _sleep(s), max_runs)
    except KeyboardInterrupt:
        typer.echo("watch stopped")


@app.command("rebuild")
def rebuild(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm deleting the lake's files.")] = False,
) -> None:
    """Delete the lake's catalog and data files and load everything again from the ledger."""
    if not yes:
        _fail("rebuild deletes the lake's catalog and data files; pass --yes to continue")
    with _lake_errors(), _ledger_snapshot(ctx) as conn:
        result = sync_lake(_config(ctx), conn, rebuild=True)
    _print_sync(result)


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Show the ledger seq the lake reflects, the sync count and the row count of each table."""
    with _lake_errors():
        lake = lake_status(_config(ctx))
    if not lake.initialised or lake.snapshot_id is None or lake.synced_at is None:
        typer.echo("lake not initialised: run `tl lake sync`")
        return
    synced = lake.synced_at.isoformat(sep=" ", timespec="seconds")
    typer.echo(f"as of seq {lake.as_of_seq} (snapshot {lake.snapshot_id}, synced {synced})")
    typer.echo(f"syncs {lake.syncs}")
    for table in sorted(lake.tables):
        typer.echo(f"{table} {lake.tables[table]}")


@app.command("tables")
def tables(ctx: typer.Context) -> None:
    """List the lake's tables and columns."""
    with _lake_errors():
        described = describe_lake(_config(ctx))
    for name in sorted(described):
        typer.echo(name)
        for column, column_type in described[name]:
            typer.echo(f"  {column} {column_type}")


@app.command("query")
def query(
    ctx: typer.Context,
    sql: Annotated[str, typer.Argument(help="One SELECT over the lake tables.")],
    limit: Annotated[int, typer.Option("--limit", help="Maximum rows to return.")] = 100,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON object.")] = False,
) -> None:
    """Run a read-only query through the lake_query guard."""
    with _lake_errors():
        result = LakeQueryService(_config(ctx)).query(sql, limit=limit, caller=_CALLER)
    if as_json:
        payload = {
            "columns": result.columns,
            "rows": result.rows,
            "truncated": result.truncated,
            "limit": result.limit,
            "as_of_seq": result.as_of_seq,
            "snapshot_id": result.snapshot_id,
        }
        typer.echo(json.dumps(payload))
        return
    typer.echo(" | ".join(result.columns))
    for row in result.rows:
        typer.echo(" | ".join("NULL" if value is None else str(value) for value in row))
    if result.truncated:
        typer.echo(f"truncated at {len(result.rows)} rows")
    typer.echo(result.as_of_line())
