"""The `tl` command: the typer root app, `init`, `serve`, `tui` and the `projections` group (29.4).

Each subcommand parses options, makes one call into tl_core or tl_adapters, and prints. No rules
live here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import Connection
from tl_adapters.backend import BackendUnavailableError, ledger_exists, open_backend
from tl_adapters.db import (
    DbTarget,
    as_target,
    create_schema,
    display_target,
    is_postgres,
    open_uow,
    rebuild_projections,
)
from tl_core.extypes.provider import attach
from tl_core.settings.effects import mark_applied
from tl_sim import cli as sim_cli

from tl_cli import (
    archive,
    backup,
    config,
    dev,
    events,
    extypes,
    extypes_quarantine,
    feed,
    file,
    lake,
    ledger,
    link,
    new,
    proposal,
    pset,
    record,
    restore,
    schema,
    serve,
    tui,
    webhook,
    wf,
)

app = typer.Typer(
    name="tl",
    help="Throughline command line: the dev ledger, records, events, and projections.",
    no_args_is_help=True,
)
app.add_typer(record.app, name="record")
app.add_typer(events.app, name="events")
app.add_typer(schema.app, name="schema")
app.add_typer(pset.app, name="pset")
app.add_typer(wf.app, name="wf")
app.add_typer(file.app, name="file")
app.add_typer(link.app, name="link")
app.add_typer(feed.app, name="feed")
app.add_typer(proposal.app, name="proposal")
app.add_typer(config.app, name="config")
app.add_typer(extypes.app, name="types")
extypes.app.add_typer(extypes_quarantine.app, name="quarantine")
app.add_typer(lake.app, name="lake")
app.add_typer(dev.app, name="dev")
app.add_typer(new.app, name="new")
app.add_typer(webhook.app, name="webhook")
app.add_typer(sim_cli.app, name="sim")
app.command("serve")(serve.serve)
app.command("tui")(tui.tui)
app.add_typer(backup.app, name="backup")
app.add_typer(archive.app, name="archive")
app.add_typer(ledger.app, name="ledger")
app.command("restore")(restore.restore)

projections = typer.Typer(help="Maintain projections from the ledger.", no_args_is_help=True)
app.add_typer(projections, name="projections")


@app.callback()
def root(
    ctx: typer.Context,
    db: Annotated[
        str,
        typer.Option(
            "--db",
            envvar="TL_DB",
            show_default=True,
            help="SQLite ledger file or postgresql:// URL. Prefer TL_DB for a URL: it carries "
            "the password and a command line is visible in the process list.",
        ),
    ] = "./dev/data/tl.db",
) -> None:
    """Throughline dev ledger commands."""
    target = as_target(db)
    ctx.obj = target
    # registered extension types join the effective schema of every command (brief 31)
    # prime (read the settings keys of the registered types) only for a ledger that exists: opening
    # a missing SQLite file would create it, and `tl archive`/`tl backup` report a missing ledger.
    # A Postgres server that cannot be reached is left to the command that needs it.
    attach(lambda readonly=False: open_uow(target, readonly=readonly), prime=_has_ledger(target))


def _has_ledger(target: DbTarget) -> bool:
    try:
        return ledger_exists(target)
    except (BackendUnavailableError, ValueError):
        return False


@app.command("init")
def init(ctx: typer.Context) -> None:
    """Create the ledger file and its schema. Running it again is harmless."""
    db: DbTarget = ctx.obj
    if is_postgres(db):
        try:
            open_backend(db).close()  # a wrong host, password or database name fails here, named
        except (BackendUnavailableError, ValueError) as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    else:
        Path(db).parent.mkdir(parents=True, exist_ok=True)
    create_schema(db)
    typer.echo(f"initialised {display_target(db)}")


@projections.command("rebuild")
def rebuild(
    ctx: typer.Context,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Projector name to rebuild; repeat for several. Default: all."),
    ] = None,
) -> None:
    """Reset projectors and replay the whole ledger into them."""
    db: DbTarget = ctx.obj

    def carried_out(conn: Connection, last_seq: int) -> None:
        # A full replay carries out the `rebuild` and `reindex` effects of settings (P0-I8 D6),
        # up to the last event it replayed; the mark commits or rolls back with the rebuild.
        mark_applied(conn, ["rebuild", "reindex"], applied_by="rebuild", head=last_seq)

    replayed = rebuild_projections(
        db, types=only or None, after_replay=None if only else carried_out
    )
    typer.echo(f"replayed {replayed} events")
