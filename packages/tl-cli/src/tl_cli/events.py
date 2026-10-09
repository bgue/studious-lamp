"""The `tl events` group: read the ledger of a project scope (brief 5.1)."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import Event

app = typer.Typer(help="Read the ledger.", no_args_is_help=True)

_PAGE = 500


@app.command("tail")
def tail(
    ctx: typer.Context,
    project: Annotated[
        str,
        typer.Option("--project", help="Project ID; reads scope project:<ID>."),
    ],
    n: Annotated[
        int,
        typer.Option("-n", min=0, help="How many of the newest events to print."),
    ] = 10,
) -> None:
    """Print the last N events of the project scope, oldest first."""
    db: Path = ctx.obj
    scope = f"project:{project}"
    newest: deque[Event] = deque(maxlen=n)
    with open_uow(db, readonly=True) as uow:
        seq = 0
        while True:
            page = uow.ledger.read_after(seq, scope=scope, limit=_PAGE)
            if not page:
                break
            newest.extend(page)
            seq = page[-1].seq
    for event in newest:
        typer.echo(
            f"{event.seq} {event.recorded_at.isoformat()} {event.event_type} "
            f"{event.stream_id} v{event.stream_version} {event.hash}"
        )
