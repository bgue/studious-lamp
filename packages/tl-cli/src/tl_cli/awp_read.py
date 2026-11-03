"""`tl awp cwp ls|show`, `tl awp cwa ls`, `tl awp wbs tree|show`, `tl awp path show|versions` and
`tl awp package ls`: the work-packaging reads (P2-I1-T04a).

None of these writes anything. The reads are the module's (`tl_mod_awp.views`); these commands parse
options and print one fact per line, with two spaces between fields. Hours print with thousands
separators and one decimal (`4,200.0`); a figure the view did not state is `-`. The CLI reads as the
default (lowest) viewer and does not widen it. Reports, write verbs, `rollup` and `worker` join
through `register(app)` functions of their own (T04b, T04c).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_awp import views

from tl_cli.derive_support import Project, cell, fail, scope_of, service_errors

cwp_app = typer.Typer(help="Construction work packages (CWPs).", no_args_is_help=True)
cwa_app = typer.Typer(help="Construction work areas (CWAs).", no_args_is_help=True)
wbs_app = typer.Typer(help="The work breakdown structure (WBS).", no_args_is_help=True)
path_app = typer.Typer(help="The path of construction.", no_args_is_help=True)
package_app = typer.Typer(help="Engineering and procurement work packages.", no_args_is_help=True)

#: The package kinds `tl awp package ls --kind` takes.
PACKAGE_KINDS = ("EWP", "PWP")
NO_PATH = "no path of construction in project {project}"


def hours(value: Decimal | None) -> str:
    """``-`` for none, else the figure with thousands separators and one decimal (``4,200.0``)."""
    return "-" if value is None else f"{value:,.1f}"


def cwp_ls(
    ctx: typer.Context,
    project: Project,
    state: Annotated[
        str | None, typer.Option("--state", help="Only CWPs in this state (none reads as Planned).")
    ] = None,
    discipline: Annotated[
        str | None, typer.Option("--discipline", help="Only CWPs of this discipline.")
    ] = None,
    cwa: Annotated[
        str | None, typer.Option("--cwa", help="Only CWPs in this construction work area (code).")
    ] = None,
) -> None:
    """List the CWPs of the project by number.

    `cwps: <n>`, then `<number>  <state>  <discipline or ->  <cwa or ->  <budget h or ->  <title>`
    for each, the title cut to 60 characters.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.cwp_list(
            uow.conn(), scope_of(project), state=state, discipline=discipline, cwa=cwa
        )
    typer.echo(f"cwps: {len(found)}")
    for c in found:
        typer.echo(
            f"{c.number}  {c.state}  {cell(c.discipline)}  {cell(c.cwa)}  "
            f"{hours(c.budget_hours)}  {cell(c.title, 60)}"
        )


def cwp_show(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The CWP number, for example P123-CWP-PIP-0001.")],
    project: Project,
) -> None:
    """Show one CWP with its allocation, its required packages and its activity links.

    Lines: `cwp <number>`, `title`, `state`, `discipline`, `cwa`, `planned <start> to <finish>`,
    `budget <h>`, `contractor`; then `allocations <n>` and `  <wbs code>  <percent>` for each;
    `packages <n>` and `  <package no>  <kind>  <status>` for each; `activities <n>` and
    `  <ref_key>  <status>` for each. An unknown, hidden or void CWP is `error: no CWP <number>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.cwp_detail(uow.conn(), scope_of(project), number)
    if d is None:
        fail(f"no CWP {number}")
    lines = [
        f"cwp {d.number}",
        f"title {cell(d.title, 1000)}",
        f"state {d.state}",
        f"discipline {cell(d.discipline)}",
        f"cwa {cell(d.cwa)}",
        f"planned {cell(d.planned_start)} to {cell(d.planned_finish)}",
        f"budget {hours(d.budget_hours)}",
        f"contractor {cell(d.contractor_text, 1000)}",
        f"allocations {len(d.allocations)}",
    ]
    lines.extend(f"  {a.wbs_code}  {a.percent}" for a in d.allocations)
    lines.append(f"packages {len(d.packages)}")
    lines.extend(f"  {p.package_no}  {p.kind}  {cell(p.status_text)}" for p in d.packages)
    lines.append(f"activities {len(d.activities)}")
    lines.extend(f"  {a.ref_key}  {a.status}" for a in d.activities)
    for line in lines:
        typer.echo(line)


def cwa_ls(ctx: typer.Context, project: Project) -> None:
    """List the construction work areas by code, retired ones flagged.

    `cwas: <n>`, then `<code>  <title>  <location or ->  <retired or active>` for each, the title
    cut to 60 characters.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.cwa_list(uow.conn(), scope_of(project))
    typer.echo(f"cwas: {len(found)}")
    for a in found:
        status = "retired" if a.retired else "active"
        typer.echo(f"{a.code}  {cell(a.title, 60)}  {cell(a.location_text)}  {status}")


def wbs_tree(
    ctx: typer.Context,
    project: Project,
    depth: Annotated[
        int | None,
        typer.Option("--depth", min=1, help="Only nodes this deep; 1 is the top node alone."),
    ] = None,
) -> None:
    """Print the WBS depth-first, each node indented two spaces per level below the top.

    `wbs nodes: <n>`, then `<code>  <indent><title>  <total h or ->  <cost codes>` for each, the
    title cut to 50 characters and the cost codes as `code=hours` joined by spaces (or `-`).
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.wbs_tree(uow.conn(), scope_of(project), depth=depth)
    typer.echo(f"wbs nodes: {len(found)}")
    for n in found:
        codes = " ".join(f"{code}={hours(h)}" for code, h in n.by_cost_code.items()) or "-"
        typer.echo(
            f"{n.code}  {'  ' * n.depth}{cell(n.title, 50)}  {hours(n.total_hours)}  {codes}"
        )


def wbs_show(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The WBS code, for example 1.1.1.")],
    project: Project,
) -> None:
    """Show one WBS node with its rollup.

    Lines: `wbs <code>`, `title`, `parent <code or ->`, `depth <n>`, `retired yes|no`,
    `total <h or ->`, then `  <cost code>  <hours>` for each cost code of the node.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.wbs_detail(uow.conn(), scope_of(project), code)
    if d is None:
        fail(f"no WBS node {code}")
    lines = [
        f"wbs {d.code}",
        f"title {cell(d.title, 1000)}",
        f"parent {cell(d.parent_code)}",
        f"depth {d.depth}",
        f"retired {'yes' if d.retired else 'no'}",
        f"total {hours(d.total_hours)}",
    ]
    lines.extend(f"  {cost_code}  {hours(h)}" for cost_code, h in d.by_cost_code.items())
    for line in lines:
        typer.echo(line)


def path_show(
    ctx: typer.Context,
    project: Project,
    version: Annotated[
        int | None, typer.Option("--version", min=1, help="The version to show (default current).")
    ] = None,
) -> None:
    """Show the steps of one version of the path of construction.

    `path version <v> of <current>`, then `<position>  <cwa or ->  <reason or ->  <actor>
    <recorded_at>` for each step. With no such path or version:
    `no path of construction in project <P>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        p = views.path(uow.conn(), scope_of(project), version=version)
    if p is None:
        typer.echo(NO_PATH.format(project=project))
        return
    typer.echo(f"path version {p.version} of {p.current_version}")
    for s in p.steps:
        typer.echo(
            f"{s.position}  {cell(s.cwa)}  {cell(s.reason_code)}  {s.actor}  {s.recorded_at}"
        )


def path_versions(ctx: typer.Context, project: Project) -> None:
    """List the versions of the path of construction, newest first.

    `<version>  <recorded_at>  <actor>  steps <n>  <current or ->` for each.
    With no path: `no path of construction in project <P>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.path_versions(uow.conn(), scope_of(project))
    if not found:
        typer.echo(NO_PATH.format(project=project))
        return
    for v in found:
        current = "current" if v.is_current else "-"
        typer.echo(f"{v.version}  {v.recorded_at}  {v.actor}  steps {v.step_count}  {current}")


def package_ls(
    ctx: typer.Context,
    project: Project,
    kind: Annotated[
        str | None, typer.Option("--kind", help="Only EWP or only PWP packages (default both).")
    ] = None,
) -> None:
    """List the EWP and PWP references of the project by package number.

    `packages: <n>`, then `<package no>  <kind>  <status or ->  forecast <date or ->  actual
    <date or ->  <constraint yes|no>` for each.
    """
    if kind is not None and kind not in PACKAGE_KINDS:
        fail(f"unknown package kind {kind!r}; the kinds are EWP and PWP")
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        found = views.package_list(uow.conn(), scope_of(project), kind=kind)
    typer.echo(f"packages: {len(found)}")
    for p in found:
        constraint = "yes" if p.constraint_source else "no"
        typer.echo(
            f"{p.package_no}  {p.kind}  {cell(p.status_text)}  "
            f"forecast {cell(p.forecast_date)}  actual {cell(p.actual_date)}  {constraint}"
        )


def register(app: typer.Typer) -> None:
    """Add the read groups (`cwp`, `cwa`, `wbs`, `path`, `package`) to the `tl awp` group."""
    app.add_typer(cwp_app, name="cwp")
    app.add_typer(cwa_app, name="cwa")
    app.add_typer(wbs_app, name="wbs")
    app.add_typer(path_app, name="path")
    app.add_typer(package_app, name="package")
    for group, name, function in (
        (cwp_app, "ls", cwp_ls),
        (cwp_app, "show", cwp_show),
        (cwa_app, "ls", cwa_ls),
        (wbs_app, "tree", wbs_tree),
        (wbs_app, "show", wbs_show),
        (path_app, "show", path_show),
        (path_app, "versions", path_versions),
        (package_app, "ls", package_ls),
    ):
        group.command(name)(function)
