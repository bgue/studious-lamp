# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl cost snapshots|codes|show`: reads of cost codes and snapshots (P1-I4-T02b).

None of these writes anything. The reads are the module's (`tl_mod_cost.views`); these commands
parse options and print one line per fact, with two spaces between fields. Figures are printed
with thousands separators and two decimals; a figure the snapshot did not state is `-`.


STUB (P1-I4-T02b): the bodies of `snapshots`, `codes` and `show` are `NotImplementedError`; the
options, docstrings (the exact output), the helpers `money` and `matrix` and `register` are
written. The ticket fills the bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_cost import views

from tl_cli.derive_support import Project, cell, service_errors

#: The five measures of each unit, in the order they are printed.
MEASURES = ("budget", "actual", "earned", "ftc", "eac")
UNITS = ("hours", "quantity", "amount")


def money(value: float | None) -> str:
    """``-`` for none, else the figure with thousands separators and two decimals."""
    return "-" if value is None else f"{value:,.2f}"


def matrix(unit: str, figures: dict[str, float | None]) -> str:
    """`<unit>  budget <x>  actual <x>  earned <x>  ftc <x>  eac <x>` from the keys
    `<unit>_<measure>` of ``figures``."""
    parts = [f"{measure} {money(figures.get(f'{unit}_{measure}'))}" for measure in MEASURES]
    return f"{unit}  " + "  ".join(parts)


def snapshots(ctx: typer.Context, project: Project) -> None:
    """List the imported periods, newest first.

    `<period>@<revision>  as of <date>  rows <n>  new <n>  revised <n>  <currency or ->
    <source file or ->`. With none: `no cost snapshots in project <project>`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.cost_snapshots(conn, scope)`.
    # 3. No snapshots: print `no cost snapshots in project <project>`.
    # 4. Per snapshot print the line of the docstring (`s.key`, `s.as_of`, `s.row_count`,
    #    `s.new_code_count`, `s.revised_code_count`, `cell(s.currency)`,
    #    `cell(s.source_name)`).
    raise NotImplementedError


def codes(
    ctx: typer.Context,
    project: Project,
    parent: Annotated[
        str | None, typer.Option("--parent", help="Only the direct children of this code.")
    ] = None,
    search: Annotated[
        str | None, typer.Option("--search", help="Code or title contains this text.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=20000)] = 100,
) -> None:
    """List the cost codes by code, with the latest amounts.

    `cost codes: <n>`, then `<code>  level <n>  uom <uom or ->  budget <amount>  actual <amount>
    eac <amount>  <title>` for each, the amounts being the `amount_*` figures of the latest
    snapshot that stated the code.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.cost_codes(conn, scope,
    #    parent=parent, search=search, limit=limit)`.
    # 3. Print `cost codes: <n>`, then one line per code: the amounts are
    #    `money(c.figures.get('amount_budget'))`, `'amount_actual'` and `'amount_eac'`;
    #    `cell(c.uom)` and `cell(c.title, 60)`.
    raise NotImplementedError


def show(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The cost code, for example 4210-PIP.")],
    project: Project,
) -> None:
    """Show one cost code, its latest figures and what every snapshot said about it.

    Lines: `cost code <code>`, `title <title>`, `parent <code or ->`, `level <n>`,
    `uom <uom or ->`, `active <yes or no>`, `children <codes, comma separated, or ->`,
    `figures from <period or -> as of <date or ->`, then one line per unit
    (`hours`, `quantity`, `amount`): `<unit>  budget <x>  actual <x>  earned <x>  ftc <x>
    eac <x>`, then `history <n>` and for each snapshot, oldest first,
    `  <period>@<revision>  as of <date>  amount budget <x>  actual <x>  eac <x>  hours actual <x>`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.cost_code_detail(conn, scope,
    #    code)`.
    # 3. Collect the lines of the docstring in a list: the eight header lines (`children`
    #    joins `d.children` with `, ` and is `-` when empty; `figures from` uses `d.period`
    #    or `-`), one `matrix(unit, d.figures)` line for each of `UNITS`, then `history <n>`
    #    and one line per entry of `d.history` in the order given.
    # 4. A history line is `  <period>@<revision>  as of <as_of>  amount budget <x>  actual
    #    <x>  eac <x>  hours actual <x>` with `money()` of `amount_budget`, `amount_actual`,
    #    `amount_eac` and `hours_actual`. Print each line.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the read commands to the `tl cost` group."""
    for name, function in (("snapshots", snapshots), ("codes", codes), ("show", show)):
        app.command(name)(function)
