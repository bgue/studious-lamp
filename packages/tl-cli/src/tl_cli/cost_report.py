"""`tl cost report budget|uncoded`: the cost reports (P1-I4-T10a).

Both read and write nothing. The reports are the module's (`tl_mod_cost.reports`); these commands
parse options and print one line per fact, with two spaces between fields. Figures are printed
with `money()` of `tl_cli.cost_read`; a figure the snapshot did not state is `-`.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_cost import reports
from tl_mod_cost.names import UNITS

from tl_cli.cost_read import money
from tl_cli.derive_support import Project, cell, fail, service_errors


def budget(
    ctx: typer.Context,
    project: Project,
    unit: Annotated[str, typer.Option("--unit", help="hours, quantity or amount.")] = "quantity",
    parent: Annotated[
        str | None, typer.Option("--parent", help="Only the direct children of this code.")
    ] = None,
    over: Annotated[
        bool, typer.Option("--over", help="Only codes whose forecast is over the budget.")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 200,
) -> None:
    """Budget against forecast for each cost code, in one unit.

    First `budget report (<unit>): <n> codes, <k> over budget`, then per code
    `<code>  level <n>  uom <uom or ->  budget <x>  actual <x>  eac <x>  variance <x>
    spent <p>%  linked <n>  <over or ok>  <title>`: `variance` is budget minus eac (negative:
    over budget), `spent` is actual as a percentage of budget with one decimal (`-` without a
    budget above zero), `linked` is the number of records linked to the code. A `--unit` other
    than the three is `error: ...` on stderr, exit 1.
    """
    db: DbTarget = ctx.obj
    if unit not in UNITS:
        fail(f"unit must be one of {', '.join(UNITS)}")
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = reports.budget_report(
            uow.conn(),
            f"project:{project}",
            unit=unit,
            parent=parent,
            over_only=over,
            limit=limit,
        )
    over_count = sum(1 for line in found if line.over_budget)
    typer.echo(f"budget report ({unit}): {len(found)} codes, {over_count} over budget")
    for line in found:
        spent = "-" if line.percent_spent is None else f"{line.percent_spent:.1f}%"
        state = "over" if line.over_budget else "ok"
        typer.echo(
            f"{line.code}  level {line.level}  uom {cell(line.uom)}"
            f"  budget {money(line.budget)}  actual {money(line.actual)}"
            f"  eac {money(line.eac)}  variance {money(line.variance)}"
            f"  spent {spent}  linked {line.linked_records}  {state}"
            f"  {cell(line.title, 60)}"
        )


def uncoded(
    ctx: typer.Context,
    project: Project,
    record_type: Annotated[
        str, typer.Option("--type", help="The record type, for example engineering.Tag.")
    ],
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 200,
) -> None:
    """List the records of a type that are linked to no cost code.

    First `records without a cost code (<type>): <n>`, then `<key or ->  <id>  <title>` for each,
    by key.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = reports.records_without_cost_code(
            uow.conn(), f"project:{project}", record_type, limit=limit
        )
    typer.echo(f"records without a cost code ({record_type}): {len(found)}")
    for record in found:
        typer.echo(f"{cell(record.key)}  {record.id}  {cell(record.title, 60)}")


def register(app: typer.Typer) -> None:
    """Add the `report` group to the `tl cost` group."""
    group = typer.Typer(help="Cost reports.", no_args_is_help=True)
    group.command("budget")(budget)
    group.command("uncoded")(uncoded)
    app.add_typer(group, name="report")
