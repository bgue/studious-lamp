"""`tl cost snapshots|codes|show`: reads of cost codes and snapshots (P1-I4-T02b).

None of these writes anything. The reads are the module's (`tl_mod_cost.views`); these commands
parse options and print one line per fact, with two spaces between fields. Figures are printed
with thousands separators and two decimals; a figure the snapshot did not state is `-`.
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
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.cost_snapshots(uow.conn(), f"project:{project}")
    if not found:
        typer.echo(f"no cost snapshots in project {project}")
        return
    for s in found:
        typer.echo(
            f"{s.key}  as of {s.as_of}  rows {s.row_count}  new {s.new_code_count}  "
            f"revised {s.revised_code_count}  {cell(s.currency)}  {cell(s.source_name)}"
        )


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
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.cost_codes(
            uow.conn(), f"project:{project}", parent=parent, search=search, limit=limit
        )
    typer.echo(f"cost codes: {len(found)}")
    for c in found:
        typer.echo(
            f"{c.code}  level {c.level}  uom {cell(c.uom)}  "
            f"budget {money(c.figures.get('amount_budget'))}  "
            f"actual {money(c.figures.get('amount_actual'))}  "
            f"eac {money(c.figures.get('amount_eac'))}  {cell(c.title, 60)}"
        )


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
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.cost_code_detail(uow.conn(), f"project:{project}", code)
    lines = [
        f"cost code {d.code}",
        f"title {d.title}",
        f"parent {cell(d.parent_code)}",
        f"level {d.level}",
        f"uom {cell(d.uom)}",
        f"active {'yes' if d.is_active else 'no'}",
        f"children {', '.join(d.children) if d.children else '-'}",
        f"figures from {d.period or '-'} as of {d.as_of or '-'}",
    ]
    lines.extend(matrix(unit, d.figures) for unit in UNITS)
    lines.append(f"history {len(d.history)}")
    for h in d.history:
        lines.append(
            f"  {h.period}@{h.revision}  as of {h.as_of}  "
            f"amount budget {money(h.figures.get('amount_budget'))}  "
            f"actual {money(h.figures.get('amount_actual'))}  "
            f"eac {money(h.figures.get('amount_eac'))}  "
            f"hours actual {money(h.figures.get('hours_actual'))}"
        )
    for line in lines:
        typer.echo(line)


def register(app: typer.Typer) -> None:
    """Add the read commands to the `tl cost` group."""
    for name, function in (("snapshots", snapshots), ("codes", codes), ("show", show)):
        app.command(name)(function)
