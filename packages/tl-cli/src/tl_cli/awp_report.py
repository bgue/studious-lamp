"""`tl awp report NAME`: the three awp reports, as lines or as CSV (P2-I1-T04b).

Reads only. The figures come from ``tl_mod_awp.reports``, which reads through the awp views (the
viewer's class filter applies). The cost system's hours come from ``tl_mod_cost.views.cost_codes``,
the latest snapshot's ``hours_budget`` of each code of the project.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated

import typer
from pydantic import BaseModel
from sqlalchemy import Connection
from tl_adapters.db import DbTarget, as_target, open_uow
from tl_mod_awp import iwp_reports, reports
from tl_mod_awp.iwp_reports import IWP_REPORT_NAMES
from tl_mod_awp.reports import REPORT_NAMES, CostFigure
from tl_mod_cost.views import cost_codes

from tl_cli.derive_support import Project, cell, fail, service_errors

COST_CODE_LIMIT: int = 20000
ALL_NAMES: tuple[str, ...] = (*REPORT_NAMES, *IWP_REPORT_NAMES)
#: The constraint reports and the field each groups by.
_GROUP_BY: dict[str, str] = {
    "constraints_by_category": "category",
    "constraints_by_owner": "owner",
    "constraints_by_age": "age",
}


def _cost_figures(conn: Connection, project: str) -> dict[str, CostFigure]:
    """The project's cost codes by code: the title and the stated ``hours_budget`` (or None)."""
    figures: dict[str, CostFigure] = {}
    for view in cost_codes(conn, f"project:{project}", limit=COST_CODE_LIMIT):
        hours = view.figures.get("hours_budget")
        figures[view.code] = CostFigure(
            title=view.title, hours_budget=None if hours is None else Decimal(str(hours))
        )
    return figures


def _target(ctx: typer.Context, db: str | None) -> DbTarget:
    """The ledger of ``--db`` when given, else the root ``--db`` of the ``tl`` command."""
    if db is None:
        if ctx.obj is None:
            fail("no ledger: give --db SQLITE_FILE or the root --db")
        target: DbTarget = ctx.obj
        return target
    try:
        return as_target(db)
    except ValueError as exc:  # the message never repeats the value: it can hold a password
        fail(str(exc))


def report(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(
            help="cwp_status, wbs_vs_cost_code, cwa_sequence, iwp_status, iwp_readiness, "
            "constraint_log, constraints_by_category, constraints_by_owner or constraints_by_age.",
        ),
    ],
    project: Project,
    as_csv: Annotated[
        bool, typer.Option("--csv", help="Print CSV: a header line, then one line per row.")
    ] = False,
    db: Annotated[
        str | None,
        typer.Option("--db", help="SQLite file or postgresql:// URL. Default: the root --db."),
    ] = None,
) -> None:
    """Print one awp report for a project: the CWP reports (`cwp_status`, `wbs_vs_cost_code`,
    `cwa_sequence`), the IWP reports (`iwp_status`, `iwp_readiness`) or the constraint reports
    (`constraint_log`, `constraints_by_category`, `constraints_by_owner`, `constraints_by_age`).

    Without `--csv`, one line per row with the fields two spaces apart. An unknown NAME is
    `error: ...` on stderr, exit 1.
    """
    if name not in ALL_NAMES:
        fail(f"report must be one of {', '.join(ALL_NAMES)}")
    target = _target(ctx, db)
    scope = f"project:{project}"
    with service_errors(), open_uow(target, readonly=True) as uow:
        conn = uow.conn()
        if name == "cwp_status":
            rows: Sequence[BaseModel] = reports.cwp_status(conn, scope)
        elif name == "wbs_vs_cost_code":
            rows = reports.wbs_vs_cost_code(conn, scope, _cost_figures(conn, project))
        elif name == "cwa_sequence":
            rows = reports.cwa_sequence(conn, scope)
        elif name == "iwp_status":
            rows = iwp_reports.iwp_status(conn, scope)
        elif name == "iwp_readiness":
            rows = iwp_reports.iwp_readiness(conn, scope)
        elif name == "constraint_log":
            rows = iwp_reports.constraint_log(conn, scope)
        else:
            rows = iwp_reports.constraint_groups_report(conn, scope, _GROUP_BY[name])
    if as_csv:
        typer.echo(reports.to_csv(rows), nl=False)
        return
    for row in rows:
        values = [cell(reports.format_value(v), 60) for v in row.model_dump().values()]
        typer.echo("  ".join(values))


def register(app: typer.Typer) -> None:
    """Add the `report` command to the awp command group (the supervisor mounts it after merge).

    The command goes in a nameless sub-app: a Typer with one command and no sub-group collapses to
    that command, which would make `report` the NAME argument on a bare app.
    """
    group = typer.Typer(help="awp reports.", no_args_is_help=True)
    group.command("report")(report)
    app.add_typer(group)
