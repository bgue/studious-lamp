"""`tl report [REPORT]`: one report per module, one row per record (V3-P0).

The reports are the modules' own (``ModuleSpec.reports``, ``tl_core.modules.module_reports``); this
command parses options and writes. It reads as the signed-in person: a record they may not read is
not a row, with no count, gap or mark. Nothing is written to the ledger. Without a name it lists
the reports, one ``name  title`` per line.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, TextIO

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality
from tl_core.modules import module_reports
from tl_core.report_out import FORMATS, render

from tl_cli.derive_support import fail, service_errors


def report(
    ctx: typer.Context,
    name: Annotated[
        str | None, typer.Argument(help="The report; omit it to list the reports.")
    ] = None,
    project: Annotated[
        str | None, typer.Option("--project", help="Project ID; scope project:<ID>.")
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="csv (default) or jsonl.")] = "csv",
    out: Annotated[
        Path | None, typer.Option("--out", help="Write here instead of the screen.")
    ] = None,
) -> None:
    """Write one report, a row per record the signed-in person may read; header row first (CSV).

    Dates are ISO; an empty value is empty (CSV) or null (JSONL). An unknown name, a missing
    --project or an unknown format is `error: ...` on stderr, exit 1.
    """
    available = module_reports()
    if name is None:
        for found in available.values():
            typer.echo(f"{found.name}  {found.title}")
        return
    chosen = available.get(name)
    if chosen is None:
        fail(f"unknown report {name!r}; `tl report` lists them")
    if project is None:
        fail("--project is required")
    if fmt not in FORMATS:
        fail(f"format must be one of {', '.join(FORMATS)}")
    db: DbTarget = ctx.obj
    handle: TextIO = out.open("w", encoding="utf-8", newline="") if out is not None else sys.stdout
    rows = 0
    try:
        with service_errors(), open_uow(db, readonly=True) as uow:
            for line in render(
                chosen, uow.conn(), f"project:{project}", confidentiality.current_viewer(), fmt
            ):
                handle.write(line)
                rows += 1
    finally:
        if out is not None:
            handle.close()
    if out is not None:
        typer.echo(f"wrote {rows - (1 if fmt == 'csv' else 0)} rows to {out}")


__all__ = ["report"]
