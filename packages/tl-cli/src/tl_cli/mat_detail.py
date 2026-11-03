"""The `tl mat` detail reads of the S5 fields: mto show, item-projects (P2-I3-T05d).

Read only: ``open_uow(db, readonly=True)``, no viewer passed (the CLI process viewer is set by
``tl_cli.main`` from the session), as ``tl_cli.mat_read``. One line per fact, two spaces between
fields; quantities through ``mat_read.qty`` and empty values through ``cell``.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_materials import views_detail
from tl_mod_materials.views import MtoLineView

from tl_cli import mat_read
from tl_cli.derive_support import Project, cell, service_errors


def mto_line_text(line: MtoLineView) -> str:
    """A take-off line as `tl mat mto list` prints it (the same fields, in the same order)."""
    return (
        f"{line.key}  {line.item_code}  required {mat_read.qty(line.required)}  "
        f"reserved {mat_read.qty(line.reserved)}  issued {mat_read.qty(line.issued)}  "
        f"short {mat_read.qty(line.short)}  for {cell(line.work_package)}  "
        f"{cell(line.item_title, 60)}"
    )


def mto_show(
    ctx: typer.Context,
    key: Annotated[
        str, typer.Argument(help="The take-off line key, for example ISO-1234@A/MTO/001.")
    ],
    project: Project,
) -> None:
    """Show one take-off line: its line as `mto list` prints it, then its reservations and open
    receipts.

    Then `reserved <lot>  <location>  <q> <uom>` for each reservation, or `no reservations`, and
    `receipt <number>  <state>  <received_on>  <q> <uom>  <supplier_text or ->` for each open
    receipt (state Received or Inspected), or `no open receipts`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views_detail.mto_line_detail(uow.conn(), f"project:{project}", key)
    typer.echo(mto_line_text(d))
    if not d.reservations:
        typer.echo("no reservations")
    for r in d.reservations:
        typer.echo(
            f"reserved {cell(r.lot)}  {cell(r.location)}  {mat_read.qty(r.qty)} {cell(d.uom)}"
        )
    if not d.open_receipts:
        typer.echo("no open receipts")
    for o in d.open_receipts:
        typer.echo(
            f"receipt {cell(o.number)}  {cell(o.state)}  {cell(o.received_on)}  "
            f"{mat_read.qty(o.qty)} {cell(o.uom)}  {cell(o.supplier_text, 60)}"
        )


def item_projects_cmd(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The company item code.")],
) -> None:
    """Show the quantities of one company item in each project that holds it.

    `item <code>  projects: <n>`, then `<project>  on hand <q>  reserved <q>  available <q>  <uom>`
    for each project. An unknown or unreadable item prints `no projects for item <code>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views_detail.item_projects(uow.conn(), code)
    if not found:
        typer.echo(f"no projects for item {code}")
        return
    typer.echo(f"item {code}  projects: {len(found)}")
    for p in found:
        typer.echo(
            f"{cell(p.project)}  on hand {mat_read.qty(p.on_hand)}  "
            f"reserved {mat_read.qty(p.reserved)}  available {mat_read.qty(p.available)}  "
            f"{cell(p.uom)}"
        )


def register(app: typer.Typer) -> None:
    """Add the detail read verbs to the `tl mat` group and its `mto` sub-group."""
    mat_read._group(app, "mto").command("show")(mto_show)
    app.command("item-projects")(item_projects_cmd)
