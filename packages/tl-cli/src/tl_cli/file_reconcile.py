"""`tl file reconcile`: compare the ledger's file rows with the object store (brief 24.5).

The command function is registered by `file.py`. It prints a summary and one line per problem and
exits 1 when anything is missing or corrupt. It never repairs: see the runbook
`docs/runbooks/object-store-reconciliation.md`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.objectstore import make_object_store
from tl_adapters.sqlite.uow import open_uow
from tl_core.files.reconcile import reconcile_objects


def reconcile(
    ctx: typer.Context,
    verify: Annotated[
        bool, typer.Option("--verify", help="Also re-hash every object (reads all bytes).")
    ] = False,
) -> None:
    """Report referenced hashes that are missing from the store, and orphaned objects."""
    db: Path = ctx.obj
    try:
        store = make_object_store()
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    with open_uow(db, readonly=True) as uow:
        report = reconcile_objects(uow, store, verify=verify)

    def count(n: int) -> str:
        return str(n) if report.listed else "unknown"

    typer.echo(f"checked {report.checked}")
    typer.echo(f"verified {'true' if report.verified else 'false'}")
    typer.echo(f"missing {len(report.missing)}")
    typer.echo(f"corrupt {len(report.corrupt)}")
    typer.echo(f"orphans {count(len(report.orphans))}")
    typer.echo(f"staging {count(len(report.staging))}")
    for problem in [*report.missing, *report.corrupt]:
        line = f"{problem.kind} {problem.sha256} files={','.join(problem.file_ids)}"
        typer.echo(line if problem.detail is None else f"{line} {problem.detail}")
    for key in report.orphans:
        typer.echo(f"orphan {key}")
    if not report.ok:
        raise typer.Exit(code=1)
