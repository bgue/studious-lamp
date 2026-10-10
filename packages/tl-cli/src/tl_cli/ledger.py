"""The `tl ledger` group: check the ledger itself (brief 24.5, "tampering suspicion").

`tl ledger verify` recomputes every event hash from the stored fields and checks each scope's
hash chain, with no archive. To compare with an archive too, use `tl archive verify --db TARGET
--deep`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, display_target, is_postgres, make_engine, make_ledger, read_tx
from tl_core.archive import verify_ledger

app = typer.Typer(help="Check the ledger itself.", no_args_is_help=True)


@app.command("verify")
def verify(
    ctx: typer.Context,
    db: Annotated[
        str | None,
        typer.Option("--db", help="SQLite file or postgresql:// URL. Default: the root --db."),
    ] = None,
) -> None:
    """Recompute every event hash and check each scope chain; report the first divergence."""
    target: DbTarget = db if db is not None else ctx.obj
    if not is_postgres(target) and not Path(target).is_file():
        typer.echo(f"error: no ledger at {target}", err=True)
        raise typer.Exit(code=1)
    engine = make_engine(target)
    try:
        with read_tx(engine) as conn:
            issues = verify_ledger(conn)
        head: int = make_ledger(engine).head_seq()
    finally:
        engine.dispose()
    if issues:
        for issue in issues:
            seq = "-" if issue.seq is None else issue.seq
            typer.echo(f"divergence: {issue.kind} seq={seq}: {issue.detail}")
        raise typer.Exit(code=1)
    typer.echo(f"verified ledger {display_target(target)}: {head} events, hash chains intact")
