"""`tl awp iwp ls|show|scope`: the IWP reads (P2-I2-T04d).

None of these writes anything. The reads are the module's (`tl_mod_awp.iwp_views`), which apply the
viewer's class filter and check no access word; these commands parse options and print one fact
per line, with two spaces between fields. Hours print with thousands separators and one decimal;
a figure the view did not state is `-`. The CLI reads as the default (lowest) viewer and does not
widen it. `register(app)` adds the three commands to the `iwp` group the glue ticket (T04g) makes.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_awp import iwp_views

from tl_cli.awp_read import hours
from tl_cli.derive_support import Project, cell, fail, scope_of, service_errors

#: The default and the most rows the list and the scope print (the view clamps to 1..500).
LIST_LIMIT = 200
SCOPE_LIMIT = 500


def iwp_ls(
    ctx: typer.Context,
    project: Project,
    state: Annotated[
        str | None, typer.Option("--state", help="Only IWPs in this state (none reads as Draft).")
    ] = None,
    discipline: Annotated[
        str | None, typer.Option("--discipline", help="Only IWPs of this discipline.")
    ] = None,
    foreman: Annotated[
        str | None, typer.Option("--foreman", help="Only IWPs with this foreman (user:X).")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most IWPs to list (default 200).")
    ] = LIST_LIMIT,
) -> None:
    """List the IWPs of the project by number.

    `iwps: <n>`, then `<number>  <state>  <discipline or ->  <foreman or ->  <hours or ->
    <scope count>  <title>` for each, the title cut to 60 characters.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = iwp_views.iwp_list(
            uow.conn(),
            scope_of(project),
            state=state,
            discipline=discipline,
            foreman=foreman,
            limit=limit,
        )
    typer.echo(f"iwps: {len(found)}")
    for w in found:
        typer.echo(
            f"{w.number}  {w.state}  {cell(w.discipline)}  {cell(w.foreman)}  "
            f"{hours(w.estimated_hours)}  {w.scope_count}  {cell(w.title, 60)}"
        )


def iwp_show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number, for example P123-IWP-PIP-0001.")],
    project: Project,
) -> None:
    """Show one IWP with its crew, its scope by type, its pins, its open constraints and sign-offs.

    Lines: `iwp <number>`, `title`, `state`, `discipline`, `foreman`, `cwp`,
    `planned <start> to <finish>`, `hours <h or ->`, `crew`, `scope <n>` then `  <type>  <count>`
    for each type, `pins <n>`, `open constraints <n>`, `signoffs <n>` then `  <by>  <role>  <at>`
    for each sign-off (the record hash is never printed). An unknown, hidden or void IWP is
    `error: no IWP <number>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = iwp_views.iwp_detail(uow.conn(), scope_of(project), number)
    if d is None:
        fail(f"no IWP {number}")
    lines = [
        f"iwp {d.number}",
        f"title {cell(d.title, 1000)}",
        f"state {d.state}",
        f"discipline {cell(d.discipline)}",
        f"foreman {cell(d.foreman)}",
        f"cwp {cell(d.cwp_number)}",
        f"planned {cell(d.planned_start)} to {cell(d.planned_finish)}",
        f"hours {hours(d.estimated_hours)}",
        f"crew {cell(d.crew_text, 1000)}",
        f"scope {d.scope_count}",
    ]
    lines.extend(f"  {record_type}  {n}" for record_type, n in d.scope_by_type.items())
    lines.append(f"pins {d.pin_count}")
    lines.append(f"open constraints {d.open_constraints}")
    lines.append(f"signoffs {len(d.signoffs)}")
    lines.extend(
        f"  {cell(s.get('by'))}  {cell(s.get('role'))}  {cell(s.get('at'))}" for s in d.signoffs
    )
    for line in lines:
        typer.echo(line)


def iwp_scope(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number, for example P123-IWP-PIP-0001.")],
    project: Project,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most members to list (default 500).")
    ] = SCOPE_LIMIT,
) -> None:
    """List the scope of one IWP: its scope items and tags, by type then key.

    `scope: <n>`, then `<number or ->  <type>  <commodity or ->  <qty or ->  <uom or ->
    <est hours or ->  <description>` for each, the description cut to 60 characters. An unknown,
    hidden or void IWP is `error: no IWP <number>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = iwp_views.iwp_scope(uow.conn(), scope_of(project), number, limit=limit)
    if found is None:
        fail(f"no IWP {number}")
    typer.echo(f"scope: {len(found)}")
    for s in found:
        typer.echo(
            f"{cell(s.number)}  {s.type}  {cell(s.commodity)}  {cell(s.qty)}  {cell(s.uom)}  "
            f"{hours(s.est_hours)}  {cell(s.description, 60)}"
        )


def register(app: typer.Typer) -> None:
    """Add the IWP reads (`ls`, `show`, `scope`) to the `iwp` group the glue ticket makes."""
    for function, name in ((iwp_ls, "ls"), (iwp_show, "show"), (iwp_scope, "scope")):
        app.command(name)(function)
