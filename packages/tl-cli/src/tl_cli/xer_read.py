"""`tl xer ls|show|activities|activity|resolve|health`: reads of schedules (P1-I4-T09b).

None of these writes anything. The reads are the module's (`tl_mod_schedule.views`); these
commands parse options and print one line per fact, with two spaces between fields, so that a
person can read them and a script can split them. A missing schedule, snapshot or activity is the
module's error (`error: ...` on stderr, exit 1).
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schedule import views

from tl_cli.derive_support import Project, cell, service_errors

_Schedule = Annotated[
    str, typer.Option("--schedule", help="The schedule's code, for example MAIN.")
]
_Snapshot = Annotated[
    int | None, typer.Option("--snapshot", min=1, help="A snapshot number (default: current).")
]
_ActivityId = Annotated[str, typer.Argument(help="The P6 activity id, for example A1230.")]


def hours(value: float | None) -> str:
    """``-`` for none, else the hours with no trailing zeros and an ``h`` (``40h``, ``-8.5h``)."""
    return "-" if value is None else f"{value:g}h"


def ls(ctx: typer.Context, project: Project) -> None:
    """List the project's schedules, one line each.

    `<code>  <type>  current <n or ->  data date <date or ->  snapshots <n>  <title>`.
    With none: `no schedules in project <project>`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        schedules = views.schedule_views(uow.conn(), f"project:{project}")
    if not schedules:
        typer.echo(f"no schedules in project {project}")
        return
    for s in schedules:
        typer.echo(
            f"{s.code}  {s.schedule_type}  current {cell(s.current_snapshot_number)}  "
            f"data date {cell(s.current_data_date)}  snapshots {s.snapshot_count}  "
            f"{cell(s.title, 60)}"
        )


def show(ctx: typer.Context, project: Project, schedule: _Schedule) -> None:
    """Show a schedule and its snapshots, newest first.

    Lines: `schedule <code>`, `title <title>`, `type <type>`, `p6 project <name or ->`,
    `owner <name or ->`, `current <n or ->  data date <date or ->`, `links being checked`
    (only while the flagging job has work left), then for each snapshot
    `snapshot <n>  <state>  data date <date or ->  activities <n or ->  errors <n or ->
    warnings <n or ->  <source file or ->`; the current snapshot has `  current` after its state.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.schedule_detail(uow.conn(), f"project:{project}", schedule)
    lines = [
        f"schedule {d.code}",
        f"title {d.title}",
        f"type {d.schedule_type}",
        f"p6 project {cell(d.p6_project)}",
        f"owner {cell(d.owner)}",
        f"current {cell(d.current_snapshot_number)}  data date {cell(d.current_data_date)}",
    ]
    if d.links_being_checked:
        lines.append("links being checked")
    for s in d.snapshots:
        current = "  current" if s.is_current else ""
        lines.append(
            f"snapshot {s.number}  {s.state}{current}  data date {cell(s.data_date)}  "
            f"activities {cell(s.activity_count)}  errors {cell(s.error_count)}  "
            f"warnings {cell(s.warning_count)}  {cell(s.source_name)}"
        )
    for line in lines:
        typer.echo(line)


def activities(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    snapshot: _Snapshot = None,
    critical: Annotated[bool, typer.Option("--critical", help="Only critical activities.")] = False,
    status: Annotated[str | None, typer.Option("--status", help="Only this status.")] = None,
    search: Annotated[
        str | None, typer.Option("--search", help="Id or name contains this text.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 50,
    offset: Annotated[int, typer.Option("--offset", min=0)] = 0,
) -> None:
    """List the activities of a snapshot in file order.

    First `<snapshot key>  data date <date>  showing <n> of <total> from <offset>`, then
    `<id>  <status>  start <early start>  finish <early finish>  float <n>h  <percent>%
    <critical or ok>  <name>` per activity (`-` for a missing value, float in hours).
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        page = views.activity_page(
            uow.conn(),
            f"project:{project}",
            schedule,
            snapshot,
            critical=True if critical else None,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
    typer.echo(
        f"{page.snapshot_key}  data date {cell(page.data_date)}  "
        f"showing {len(page.rows)} of {page.total} from {page.offset}"
    )
    for a in page.rows:
        flag = "critical" if a.critical else "ok"
        typer.echo(
            f"{a.activity_id}  {a.status}  start {cell(a.early_start)}  "
            f"finish {cell(a.early_finish)}  float {hours(a.total_float_hr)}  "
            f"{a.percent_complete:g}%  {flag}  {cell(a.name, 60)}"
        )


def activity(
    ctx: typer.Context,
    activity_id: _ActivityId,
    project: Project,
    schedule: _Schedule,
    snapshot: _Snapshot = None,
) -> None:
    """Show one activity and the relationships around it.

    Lines: `activity <id> in <snapshot key>`, `name <name>`, `wbs <path>`,
    `type <task type>  status <status>  percent <n>`, `early <start> -> <finish>`,
    `late <start> -> <finish>`, `actual <start> -> <finish>`,
    `float total <n>h  free <n>h  <critical or ok>`, `predecessors <n>` and `successors <n>`,
    each followed by one line per relationship: `  <other id>  <type>  lag <n>h`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        d = views.activity_detail(uow.conn(), f"project:{project}", schedule, activity_id, snapshot)
    a = d.activity
    flag = "critical" if a.critical else "ok"
    lines = [
        f"activity {a.activity_id} in {d.snapshot_key}",
        f"name {a.name}",
        f"wbs {a.wbs_path}",
        f"type {a.task_type}  status {a.status}  percent {a.percent_complete:g}",
        f"early {cell(a.early_start)} -> {cell(a.early_finish)}",
        f"late {cell(a.late_start)} -> {cell(a.late_finish)}",
        f"actual {cell(a.actual_start)} -> {cell(a.actual_finish)}",
        f"float total {hours(a.total_float_hr)}  free {hours(a.free_float_hr)}  {flag}",
        f"predecessors {len(d.predecessors)}",
    ]
    lines.extend(
        f"  {r.pred_activity_id}  {r.relationship_type}  lag {hours(r.lag_hr)}"
        for r in d.predecessors
    )
    lines.append(f"successors {len(d.successors)}")
    lines.extend(
        f"  {r.succ_activity_id}  {r.relationship_type}  lag {hours(r.lag_hr)}"
        for r in d.successors
    )
    for line in lines:
        typer.echo(line)


def resolve(
    ctx: typer.Context,
    activity_id: _ActivityId,
    project: Project,
    schedule: _Schedule,
    as_of: Annotated[
        str | None,
        typer.Option(
            "--as-of", help="A snapshot number, a date (YYYY-MM-DD) or `current` (the default)."
        ),
    ] = None,
) -> None:
    """Say what an activity id is now, or as of a snapshot or a date.

    `<activity id>  <state>  <schedule>#<n> or -  data date <date or ->`, and, when the activity
    is in that snapshot, a second line `name <name>  start <early start>  finish <early finish>
    float <n>h`. States: current, as_of, orphaned, unknown_activity, no_snapshot.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        r = views.resolution(
            uow.conn(), f"project:{project}", schedule, activity_id, views.as_of_of(as_of)
        )
    snapshot = "-" if r.snapshot_number is None else f"{r.schedule_code}#{r.snapshot_number}"
    typer.echo(f"{r.activity_id}  {r.state}  {snapshot}  data date {cell(r.data_date)}")
    if r.activity is not None:
        a = r.activity
        typer.echo(
            f"name {a.name}  start {cell(a.early_start)}  finish {cell(a.early_finish)}  "
            f"float {hours(a.total_float_hr)}"
        )


def health(ctx: typer.Context, project: Project, schedule: _Schedule) -> None:
    """List the links whose activity is not in the current snapshot (orphaned links).

    `orphaned links: <n>`, then `<link id>  record <id>  activity <id>  last seen <snapshot
    number or ->` for each.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        links = views.orphans(uow.conn(), f"project:{project}", schedule)
    typer.echo(f"orphaned links: {len(links)}")
    for link in links:
        typer.echo(
            f"{link.link_id}  record {link.from_id}  activity {link.activity_id}  "
            f"last seen {cell(link.last_seen_number)}"
        )


def register(app: typer.Typer) -> None:
    """Add the read commands to the `tl xer` group."""
    for name, function in (
        ("ls", ls),
        ("show", show),
        ("activities", activities),
        ("activity", activity),
        ("resolve", resolve),
        ("health", health),
    ):
        app.command(name)(function)
