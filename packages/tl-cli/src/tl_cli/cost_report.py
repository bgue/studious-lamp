# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl cost report budget|uncoded`: the cost reports (P1-I4-T10a).

Both read and write nothing. The reports are the module's (`tl_mod_cost.reports`); these commands
parse options and print one line per fact, with two spaces between fields. Figures are printed
with `money()` of `tl_cli.cost_read`; a figure the snapshot did not state is `-`.


STUB (P1-I4-T10a): the bodies of `budget` and `uncoded` are `NotImplementedError`; the options,
docstrings (the exact output) and `register` are written. The ticket fills the bodies by their
STEPS comments.
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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. A `--unit` that is not in `UNITS` is `fail(f"unit must be one of {',
    #    '.join(UNITS)}")` (it prints `error: ...` on stderr and exits 1). Do this before
    #    you open the database.
    # 3. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the report with `uow.conn()` and the scope `f"project:{project}"`, and
    #    leave the `with` before you print. The report is `reports.budget_report(conn,
    #    scope, unit=unit, parent=parent, over_only=over, limit=limit)`.
    # 4. Print `budget report (<unit>): <n> codes, <k> over budget` where k counts the lines
    #    with `over_budget`.
    # 5. Per line print the line of the docstring: the figures with `money(x)` (the helper
    #    imported above: `-` for none), `spent` as `<percent:.1f>%` or `-`, `over` or `ok`,
    #    `cell(x.uom)` and `cell(x.title, 60)`.
    raise NotImplementedError


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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the report with `uow.conn()` and the scope `f"project:{project}"`, and
    #    leave the `with` before you print. The report is
    #    `reports.records_without_cost_code(conn, scope, record_type, limit=limit)`.
    # 3. Print `records without a cost code (<type>): <n>`, then one line per record:
    #    `<cell(key)>  <id>  <cell(title, 60)>`.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the `report` group to the `tl cost` group."""
    group = typer.Typer(help="Cost reports.", no_args_is_help=True)
    group.command("budget")(budget)
    group.command("uncoded")(uncoded)
    app.add_typer(group, name="report")
