"""The `tl mat` read verbs: item, loc, po, stock, lot, movements, receipt list|show, mto list.

P2-I3-T05b. None of these writes anything. The reads are the module's
(`tl_mod_materials.views`); these commands parse options and print one line per fact, with two
spaces between fields, in the style of
`tl cost`. Quantities are `format(Decimal, "f")` as the view gives them; a missing value is `-`.
The verbs pass no viewer: the CLI process viewer is set by `tl_cli.main` from the session.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_materials import views
from tl_mod_materials.views import MovementView

from tl_cli.derive_support import OptProject, Project, cell, service_errors

#: The sign of a movement with no ``direction``, by kind (the stock projector's table).
SIGN_BY_KIND = {"receive": "+", "return": "+", "issue": "-", "scrap": "-"}

Limit = Annotated[int, typer.Option("--limit", min=1, max=1000, help="At most this many rows.")]


def qty(value: Decimal) -> str:
    """A quantity as the view gives it, without an exponent."""
    return format(value, "f")


def sign(movement: MovementView) -> str:
    """``+`` for stock in, ``-`` for stock out; from ``direction`` when the movement has one."""
    if movement.direction == "in":
        return "+"
    if movement.direction == "out":
        return "-"
    return SIGN_BY_KIND.get(movement.kind, "")


def receipt_line(r: views.ReceiptView) -> str:
    """`<number>  <state>  <received_on>  <location>  lines <n>  mtr <state>  <title>`."""
    return (
        f"{r.number}  {cell(r.state)}  {cell(r.received_on)}  {cell(r.location)}  "
        f"lines {r.lines}  mtr {r.mtr}  {cell(r.title, 60)}"
    )


def item_cmd(
    ctx: typer.Context,
    project: OptProject = None,
    limit: Limit = 100,
) -> None:
    """List the library items by code, or the items a project holds with `--project`.

    `<code>  <category>  <base_uom>  projects <n>  <retired or active>  <title>`. With none:
    `no items` (or `no items in project <p>`).
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}" if project else None
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.items(uow.conn(), project=scope, limit=limit)
    if not found:
        typer.echo(f"no items in project {project}" if project else "no items")
        return
    for i in found:
        typer.echo(
            f"{i.code}  {cell(i.category)}  {cell(i.base_uom)}  projects {i.projects}  "
            f"{'retired' if i.retired else 'active'}  {cell(i.title, 60)}"
        )


def loc_cmd(ctx: typer.Context, project: Project, limit: Limit = 100) -> None:
    """List the locations of a project as a tree.

    `locations: <n>`, then `<code>  <title indented 2 spaces per depth>  <kind>  lots <n>
    lines <n>` for each, in tree order. With none: `no locations in project <p>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.locations_tree(uow.conn(), f"project:{project}", limit=limit)
    if not found:
        typer.echo(f"no locations in project {project}")
        return
    typer.echo(f"locations: {len(found)}")
    for loc in found:
        indent = "  " * loc.depth
        typer.echo(
            f"{loc.code}  {indent}{cell(loc.title, 60)}  {cell(loc.kind)}  "
            f"lots {loc.lots}  lines {loc.lines}"
        )


def po_cmd(
    ctx: typer.Context,
    project: Project,
    q: Annotated[
        str | None, typer.Option("--q", help="Key, item or supplier contains this text.")
    ] = None,
    limit: Limit = 100,
) -> None:
    """List the PO lines of a project by key.

    `<key>  <item_code>  ordered <q>  received <q> <uom>  promised <date or ->  <supplier_text>`.
    With none: `no PO lines in project <p>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.po_lines(uow.conn(), f"project:{project}", q=q, limit=limit)
    if not found:
        typer.echo(f"no PO lines in project {project}")
        return
    for p in found:
        typer.echo(
            f"{p.key}  {p.item_code}  ordered {qty(p.qty_ordered)}  "
            f"received {qty(p.qty_received)} {cell(p.uom)}  "
            f"promised {cell(p.promised_date)}  {cell(p.supplier_text, 60)}"
        )


def stock_cmd(
    ctx: typer.Context,
    project: Project,
    lot: Annotated[str | None, typer.Option("--lot", help="The lot key.")] = None,
    location: Annotated[str | None, typer.Option("--location", help="The location code.")] = None,
    item: Annotated[str | None, typer.Option("--item", help="The item code.")] = None,
    heat: Annotated[str | None, typer.Option("--heat", help="The heat number.")] = None,
    subtree: Annotated[
        bool, typer.Option("--subtree", help="With --location: that location and those below it.")
    ] = False,
    limit: Limit = 100,
) -> None:
    """List the stock balances of a project by lot and location.

    `stock rows: <n>`, then `<lot>  <heat or ->  <item_code>  <location>  on hand <q>  reserved <q>
    available <q>  <uom>  <item_title>` for each.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.stock(
            uow.conn(),
            f"project:{project}",
            lot=lot,
            location=location,
            item=item,
            heat=heat,
            subtree=subtree,
            limit=limit,
        )
    typer.echo(f"stock rows: {len(found)}")
    for s in found:
        typer.echo(
            f"{s.lot}  {cell(s.heat_no)}  {s.item_code}  {s.location}  "
            f"on hand {qty(s.on_hand)}  reserved {qty(s.reserved)}  "
            f"available {qty(s.available)}  {cell(s.uom)}  {cell(s.item_title, 60)}"
        )


def lot_cmd(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="The lot key, for example P123-RCPT-0001@1.")],
    project: Project,
) -> None:
    """Show one lot: its heat, item and receipt, its balances, reservations and last ten moves.

    `lot <key>  heat <h or ->  <item_code>  <item_title>  receipt <n or ->  po line <k or ->`, then
    `qty <location>  on hand <q>  reserved <q>  available <q>` for each balance,
    `reserved <mto_line>  <location>  <q>` for each reservation, and
    `move <date>  <kind>  <q> <uom>  <from or ->  <to or ->  <actor>` for each movement, newest
    first.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.lot_detail(uow.conn(), f"project:{project}", key)
    typer.echo(
        f"lot {d.key}  heat {cell(d.heat_no)}  {d.item_code}  {cell(d.item_title, 60)}  "
        f"receipt {cell(d.receipt)}  po line {cell(d.po_line)}"
    )
    for q in d.quantities:
        typer.echo(
            f"qty {q.location}  on hand {qty(q.on_hand)}  reserved {qty(q.reserved)}  "
            f"available {qty(q.available)}"
        )
    for r in d.reservations:
        typer.echo(f"reserved {r.mto_line}  {r.location}  {qty(r.qty)}")
    for m in d.movements:
        typer.echo(
            f"move {m.recorded_at[:10]}  {m.kind}  {qty(m.qty)} {cell(m.uom)}  "
            f"{cell(m.from_location)}  {cell(m.to_location)}  {m.actor}"
        )


def movements_cmd(
    ctx: typer.Context,
    project: Project,
    lot: Annotated[str | None, typer.Option("--lot", help="The lot key.")] = None,
    since: Annotated[str | None, typer.Option("--since", help="From this day, YYYY-MM-DD.")] = None,
    until: Annotated[
        str | None, typer.Option("--until", help="Up to this day, YYYY-MM-DD, included.")
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="receive, issue, transfer, return, adjust, scrap, ..."),
    ] = None,
    limit: Limit = 100,
) -> None:
    """List the movements of a project in ledger order.

    `movements: <n>`, then `<date>  <kind>  <lot>  <item_code>  <+/-><q> <uom>  <from>  <to>
    <actor>` for each. The sign is `+` for stock in and `-` for stock out.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.movements(
            uow.conn(),
            f"project:{project}",
            lot=lot,
            since=since,
            until=until,
            kind=kind,
            limit=limit,
        )
    typer.echo(f"movements: {len(found)}")
    for m in found:
        typer.echo(
            f"{m.recorded_at[:10]}  {m.kind}  {m.lot}  {m.item_code}  "
            f"{sign(m)}{qty(m.qty)} {cell(m.uom)}  {cell(m.from_location)}  "
            f"{cell(m.to_location)}  {m.actor}"
        )


def receipt_list(
    ctx: typer.Context,
    project: Project,
    open_only: Annotated[
        bool, typer.Option("--open", help="Only receipts not yet decided (Received, Inspected).")
    ] = False,
    missing_mtr: Annotated[
        bool, typer.Option("--missing-mtr", help="Only receipts that still lack a required MTR.")
    ] = False,
    limit: Limit = 100,
) -> None:
    """List the receipts of a project by number.

    `<number>  <state>  <received_on>  <location>  lines <n>  mtr <state>  <title>` for each.
    With none: `no receipts in project <p>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.receipts(
            uow.conn(),
            f"project:{project}",
            open_only=open_only,
            missing_mtr=missing_mtr,
            limit=limit,
        )
    if not found:
        typer.echo(f"no receipts in project {project}")
        return
    for r in found:
        typer.echo(receipt_line(r))


def receipt_show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The receipt number, for example P123-RCPT-0001.")],
    project: Project,
) -> None:
    """Show one receipt: its line as `receipt list` prints it, then its lines and files.

    Then `line <n>  <item_code>  <q> <uom>  heat <h or ->  <condition>` for each line, and
    `file <slot or ->  <filename>  <status>` for each file.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.receipt_detail(uow.conn(), f"project:{project}", number)
    typer.echo(receipt_line(d))
    for line in d.line_rows:
        typer.echo(
            f"line {line.line_no}  {line.item_code}  {qty(line.qty)} {cell(line.uom)}  "
            f"heat {cell(line.heat_no)}  {cell(line.condition)}"
        )
    for f in d.files:
        typer.echo(f"file {cell(f.slot)}  {cell(f.filename, 60)}  {cell(f.status)}")


def mto_list(
    ctx: typer.Context,
    project: Project,
    work_package: Annotated[
        str | None, typer.Option("--work-package", help="The work package number.")
    ] = None,
    short_only: Annotated[
        bool, typer.Option("--short-only", help="Only lines with a shortage.")
    ] = False,
    limit: Limit = 100,
) -> None:
    """List the take-off lines of a project by key.

    `<key>  <item_code>  required <q>  reserved <q>  issued <q>  short <q>  for <work_package or ->
    <item_title>` for each. With none: `no take-off lines in project <p>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.mto_lines(
            uow.conn(),
            f"project:{project}",
            work_package=work_package,
            short_only=short_only,
            limit=limit,
        )
    if not found:
        typer.echo(f"no take-off lines in project {project}")
        return
    for line in found:
        typer.echo(
            f"{line.key}  {line.item_code}  required {qty(line.required)}  "
            f"reserved {qty(line.reserved)}  issued {qty(line.issued)}  "
            f"short {qty(line.short)}  for {cell(line.work_package)}  {cell(line.item_title, 60)}"
        )


def _group(app: typer.Typer, name: str) -> typer.Typer:
    """The sub-group ``name`` that ``tl_cli.mat`` added to ``app``."""
    for info in app.registered_groups:
        if info.name == name and info.typer_instance is not None:
            return info.typer_instance
    raise LookupError(f"the {name} group is not on the materials app")


def register(app: typer.Typer) -> None:
    """Add the read verbs to the `tl mat` group, and to its `receipt` and `mto` sub-groups."""
    for name, function in (
        ("item", item_cmd),
        ("loc", loc_cmd),
        ("po", po_cmd),
        ("stock", stock_cmd),
        ("lot", lot_cmd),
        ("movements", movements_cmd),
    ):
        app.command(name)(function)
    _group(app, "receipt").command("list")(receipt_list)
    _group(app, "receipt").command("show")(receipt_show)
    _group(app, "mto").command("list")(mto_list)
