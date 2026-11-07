"""`tl awp readiness ls|show`: the last readiness evaluation of each IWP (P2-I2-T04d2).

Read only. Nothing here runs a check or writes a row: the evaluation is read from the projected
rows (`tl_mod_awp.views.readiness`), and `ls` walks the IWP list (`tl_mod_awp.iwp_views`). The CLI
prints what the view returns and looks nothing up itself. It reads as the default (lowest) viewer
and does not widen it. A missing, hidden, void or never-evaluated IWP answers alike.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_awp import iwp_views
from tl_mod_awp.readiness import views
from tl_mod_awp.readiness.engine import PASSING
from tl_mod_awp.readiness.views import ReadinessView

from tl_cli.derive_support import Project, cell, fail, scope_of, service_errors

readiness_app = typer.Typer(
    help="The last readiness evaluation of each IWP (read only).", no_args_is_help=True
)


def _passing(view: ReadinessView) -> int:
    return sum(1 for c in view.checks if c.state in PASSING)


def _ls_line(number: str, view: ReadinessView | None) -> str:
    """One IWP of `readiness ls`; an IWP never evaluated has `-` for every figure."""
    if view is None:
        return f"{number}  not evaluated  -/-  -  -"
    blocked = ", ".join(c.name for c in view.checks if c.state == "blocked") or "-"
    ready = "ready" if view.ready else "not ready"
    return (
        f"{number}  {ready}  {_passing(view)}/{len(view.checks)}  "
        f"{view.evaluated_at[:10]}  {blocked}"
    )


def readiness_ls(
    ctx: typer.Context,
    project: Project,
    state: Annotated[
        str | None,
        typer.Option("--state", help="Only IWPs in this workflow state (Draft default)."),
    ] = None,
    foreman: Annotated[
        str | None, typer.Option("--foreman", help="Only IWPs of this foreman (user:X).")
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", min=1, max=500, help="At most this many IWPs (default 200).")
    ] = 200,
) -> None:
    """List the IWPs of the project by number with their last readiness evaluation.

    `readiness: <n>`, then `<number>  <ready|not ready|not evaluated>  <passing>/<total>
    <evaluated date or ->  <blocked check names, comma-joined, or ->` for each. `not evaluated`
    has `-/-  -  -`.
    """
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        rows = iwp_views.iwp_list(conn, scope, state=state, foreman=foreman, limit=limit)
        found = [(r.number, views.readiness(conn, scope, r.number)) for r in rows]
    typer.echo(f"readiness: {len(found)}")
    for number, view in found:
        typer.echo(_ls_line(number, view))


def readiness_show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The IWP number, for example P123-IWP-PIP-0001.")],
    project: Project,
) -> None:
    """Show the last readiness evaluation of one IWP, check by check.

    Lines: `readiness <number>`, `ready  yes|no`, `checks  <passing>/<total>`,
    `evaluated  <evaluated_at>  for  <today>`; then `<name>  <state>  <count_ok>/<count_total or
    ->  <detail, cut to 80>` for each check in name order, and `  resolve  <record type>  <key>`
    for each record the check names. A missing, hidden, void or never-evaluated IWP is
    `error: no readiness for <number>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        view = views.readiness(uow.conn(), scope_of(project), number)
    if view is None:
        fail(f"no readiness for {number}")
    lines = [
        f"readiness {number}",
        f"ready  {'yes' if view.ready else 'no'}",
        f"checks  {_passing(view)}/{len(view.checks)}",
        f"evaluated  {view.evaluated_at}  for  {view.today}",
    ]
    for c in sorted(view.checks, key=lambda check: check.name):
        count = "-" if c.count_total is None else f"{c.count_ok}/{c.count_total}"
        lines.append(f"{c.name}  {c.state}  {count}  {cell(c.detail, 80)}")
        lines.extend(f"  resolve  {r.record_type}  {r.key}" for r in c.resolve_via)
    for line in lines:
        typer.echo(line)


def register(app: typer.Typer) -> None:
    """Add the `readiness` group (`ls`, `show`) to the `tl awp` group."""
    app.add_typer(readiness_app, name="readiness")
    readiness_app.command("ls")(readiness_ls)
    readiness_app.command("show")(readiness_show)
