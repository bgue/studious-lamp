"""The `tl` command: the typer root app, `init`, and the `projections` group (brief 29.4).

Each subcommand parses options, makes one call into tl_core or tl_adapters, and prints. No rules
live here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.sqlite.uow import create_schema, rebuild_projections

from tl_cli import events, record

app = typer.Typer(
    name="tl",
    help="Throughline command line: the dev ledger, records, events, and projections.",
    no_args_is_help=True,
)
app.add_typer(record.app, name="record")
app.add_typer(events.app, name="events")

projections = typer.Typer(help="Maintain projections from the ledger.", no_args_is_help=True)
app.add_typer(projections, name="projections")


@app.callback()
def root(
    ctx: typer.Context,
    db: Annotated[
        str,
        typer.Option("--db", envvar="TL_DB", show_default=True, help="SQLite ledger file."),
    ] = "./dev/data/tl.db",
) -> None:
    """Throughline dev ledger commands."""
    ctx.obj = Path(db)


@app.command("init")
def init(ctx: typer.Context) -> None:
    """Create the ledger file and its schema. Running it again is harmless."""
    db: Path = ctx.obj
    db.parent.mkdir(parents=True, exist_ok=True)
    create_schema(db)
    typer.echo(f"initialised {db}")


@projections.command("rebuild")
def rebuild(
    ctx: typer.Context,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help="Projector name to rebuild; repeat for several. Default: all."),
    ] = None,
) -> None:
    """Reset projectors and replay the whole ledger into them."""
    db: Path = ctx.obj
    replayed = rebuild_projections(db, types=only or None)
    typer.echo(f"replayed {replayed} events")
