"""`tl mat report NAME`: the materials reports (P2-I3-T05b).

The report reads and writes nothing. It is the module's (`tl_mod_materials.reports`); this command
parses options and prints. `--format table` prints the columns, one row per line, then `rows: <n>`
(and `truncated` when a view hit its bound); `--format csv` prints `to_csv` verbatim, so its cells
are formula-safe.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_cost import views as cost_views
from tl_mod_materials.reports import build_report, to_csv

from tl_cli.derive_support import Project, cell, fail, service_errors

FORMATS = ("table", "csv")


def report_cmd(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(
            help="stock_on_hand, movement_log, mto_status, shortages, heat_trace or "
            "consumables_by_cost_code."
        ),
    ],
    project: Project,
    since: Annotated[
        str | None, typer.Option("--since", help="From this day, YYYY-MM-DD (movement reports).")
    ] = None,
    until: Annotated[
        str | None, typer.Option("--until", help="Up to this day, YYYY-MM-DD, included.")
    ] = None,
    heat: Annotated[
        str | None, typer.Option("--heat", help="The heat number; required by heat_trace.")
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="table or csv.")] = "table",
) -> None:
    """Build one materials report for a project and print it.

    `table`: the columns joined by two spaces, then one line of cells per row, then `rows: <n>`
    (and `truncated` when set). `csv`: the report as CSV, verbatim. An unknown name, a
    `heat_trace` without `--heat`, or a bad date is `error: ...` on stderr, exit 1.
    """
    db: DbTarget = ctx.obj
    if fmt not in FORMATS:
        fail(f"format must be one of {', '.join(FORMATS)}")
    scope = f"project:{project}"
    try:
        with service_errors(), open_uow(db, readonly=True) as uow:
            conn = uow.conn()
            cost_codes = {c.id: c.code for c in cost_views.cost_codes(conn, scope)}
            built = build_report(
                conn,
                scope,
                name,
                since=since,
                until=until,
                heat=heat,
                cost_codes=cost_codes,
            )
    except ValueError as exc:
        fail(str(exc))
    if fmt == "csv":
        typer.echo(to_csv(built), nl=False)
        return
    typer.echo("  ".join(built.columns))
    for row in built.rows:
        typer.echo("  ".join(cell(value) for value in row))
    typer.echo(f"rows: {len(built.rows)}")
    if built.truncated:
        typer.echo("truncated")


def register(app: typer.Typer) -> None:
    """Add the `report` command to the `tl mat` group."""
    app.command("report")(report_cmd)
