"""`tl xer compare|look-ahead|trend`: what changed between snapshots and what comes next (T09c).

None of these writes anything. The reads are the module's (`tl_mod_schedule.views`); these
commands parse options and print one line per fact, with two spaces between fields. Floats and
shifts are in days (of the activity's own calendar), as the views give them.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schedule import views
from tl_mod_schedule.compare import LIST_FIELDS

from tl_cli.derive_support import Project, cell, fail, service_errors

_Schedule = Annotated[
    str, typer.Option("--schedule", help="The schedule's code, for example MAIN.")
]


def days(value: float | int | None) -> str:
    """``-`` for none, else the number with no trailing zeros and a ``d`` (``4d``, ``-5.5d``)."""
    return "-" if value is None else f"{value:g}d"


def shift(value: int | None) -> str:
    """A shift in calendar days with its sign: ``+7d``, ``-2d``, ``+0d``; ``-`` for none."""
    return "-" if value is None else f"{value:+d}d"


def compare(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    new: Annotated[
        int | None, typer.Option("--new", min=1, help="The newer snapshot (default: current).")
    ] = None,
    old: Annotated[
        int | None, typer.Option("--old", min=1, help="The older one (default: the one before).")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000, help="Rows per list.")] = 20,
) -> None:
    """Compare two snapshots of a schedule.

    Lines: `compare <new key> (<data date>) with <old key> (<data date>)`,
    `data date shift <+n>d`, `latest finish <old or -> -> <new or ->  <+n>d or -`, then
    `summary added <n>  removed <n>  date shifts <n>  float changes <n>  logic changes <n>
    progress changes <n>  duration changes <n>  critical changes <n>` (the full counts), and up to
    `--limit` rows of each list, in this order:
    `added <id>  <name>`, `removed <id>  <name>`,
    `shift <id>  start <+n>d  finish <+n>d  largest <n>d  <name>`,
    `float <id>  <old>d -> <new>d  eroded or improved  <name>`,
    `logic <added|removed|changed> <pred> -> <succ>  <old type> -> <new type>`,
    `progress <id>  <old>% -> <new>%  <old status> -> <new status>  <name>`,
    `duration <id>  <old>d -> <new>d  <name>`,
    `critical <id>  <entered|left>  float <old>d -> <new>d  <name>`.
    A list longer than `--limit` ends with `... <list> <k> more not shown`.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        c = views.comparison(uow.conn(), f"project:{project}", schedule, new, old, limit=limit)
    typer.echo(f"compare {c.new.key} ({c.new.data_date}) with {c.old.key} ({c.old.data_date})")
    typer.echo(f"data date shift {shift(c.data_date_shift_days)}")
    typer.echo(
        f"latest finish {cell(c.latest_finish_old)} -> {cell(c.latest_finish_new)}  "
        f"{shift(c.finish_shift_days)}"
    )
    counts = "  ".join(f"{name.replace('_', ' ')} {c.totals.get(name, 0)}" for name in LIST_FIELDS)
    typer.echo(f"summary {counts}")
    rows: dict[str, list[str]] = {
        "added": [f"added {r.activity_id}  {cell(r.name, 60)}" for r in c.added],
        "removed": [f"removed {r.activity_id}  {cell(r.name, 60)}" for r in c.removed],
        "date_shifts": [
            f"shift {r.activity_id}  start {shift(r.start_shift_days)}  "
            f"finish {shift(r.finish_shift_days)}  largest {r.largest_days}d  {cell(r.name, 60)}"
            for r in c.date_shifts
        ],
        "float_changes": [
            f"float {r.activity_id}  {days(r.old_days)} -> {days(r.new_days)}  "
            f"{'eroded' if r.eroded else 'improved'}  {cell(r.name, 60)}"
            for r in c.float_changes
        ],
        "logic_changes": [
            f"logic {r.kind} {r.pred_activity_id} -> {r.succ_activity_id}  "
            f"{cell(r.old_type)} -> {cell(r.new_type)}"
            for r in c.logic_changes
        ],
        "progress_changes": [
            f"progress {r.activity_id}  {r.old_percent:g}% -> {r.new_percent:g}%  "
            f"{cell(r.old_status)} -> {cell(r.new_status)}  {cell(r.name, 60)}"
            for r in c.progress_changes
        ],
        "duration_changes": [
            f"duration {r.activity_id}  {days(r.old_days)} -> {days(r.new_days)}  "
            f"{cell(r.name, 60)}"
            for r in c.duration_changes
        ],
        "critical_changes": [
            f"critical {r.activity_id}  {r.direction}  "
            f"float {days(r.old_float_days)} -> {days(r.new_float_days)}  {cell(r.name, 60)}"
            for r in c.critical_changes
        ],
    }
    for name in LIST_FIELDS:
        for line in rows[name]:
            typer.echo(line)
        more = c.totals.get(name, 0) - len(rows[name])
        if more > 0:
            typer.echo(f"... {name} {more} more not shown")


def look_ahead(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    snapshot: Annotated[
        int | None, typer.Option("--snapshot", min=1, help="A snapshot (default: current).")
    ] = None,
    weeks: Annotated[int, typer.Option("--weeks", help="Weeks to look ahead, 1 to 26.")] = 4,
) -> None:
    """List what is under way or starts in the next weeks from the data date.

    Lines: `look-ahead <snapshot key>  <window start> to <window end>  <weeks> weeks`,
    `in progress <n>  late start <n>  starting <n>  critical <n>  total <n>`, then
    `<id>  <phase>  start <early start>  finish <early finish>  float <n>d  <percent>%
    <critical or ok>  <name>` per activity, in the order the module gives. A `--weeks` outside 1
    to 26 is `error: ...` on stderr, exit 1.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        try:
            r = views.look_ahead_view(uow.conn(), f"project:{project}", schedule, snapshot, weeks)
        except ValueError as problem:
            fail(str(problem))
    typer.echo(f"look-ahead {r.snapshot_key}  {r.window_start} to {r.window_end}  {r.weeks} weeks")
    typer.echo(
        f"in progress {r.counts.get('in_progress', 0)}  "
        f"late start {r.counts.get('late_start', 0)}  "
        f"starting {r.counts.get('starting', 0)}  "
        f"critical {r.counts.get('critical', 0)}  "
        f"total {r.counts.get('total', 0)}"
    )
    for a in r.rows:
        typer.echo(
            f"{a.activity_id}  {a.phase}  start {cell(a.early_start)}  "
            f"finish {cell(a.early_finish)}  float {days(a.total_float_days)}  "
            f"{a.percent_complete:g}%  {'critical' if a.critical else 'ok'}  {cell(a.name, 60)}"
        )


def trend(
    ctx: typer.Context,
    activity_id: Annotated[str, typer.Argument(help="The P6 activity id, for example A1230.")],
    project: Project,
    schedule: _Schedule,
) -> None:
    """Show one activity's float in every published snapshot, oldest first.

    `trend <id> in <schedule>`, then `<schedule>#<n>  <state>  data date <date>  float <n>d
    start <early start>  finish <early finish>  <percent>%  <critical or ok>` per snapshot that
    has the activity.
    """
    db: DbTarget = ctx.obj
    with service_errors(), open_uow(db, readonly=True) as uow:
        points = views.float_trend(uow.conn(), f"project:{project}", schedule, activity_id)
    typer.echo(f"trend {activity_id} in {schedule}")
    for p in points:
        typer.echo(
            f"{schedule}#{p.snapshot_number}  {p.state}  data date {cell(p.data_date)}  "
            f"float {days(p.total_float_days)}  start {cell(p.early_start)}  "
            f"finish {cell(p.early_finish)}  {p.percent_complete:g}%  "
            f"{'critical' if p.critical else 'ok'}"
        )


def register(app: typer.Typer) -> None:
    """Add the comparison commands to the `tl xer` group."""
    for name, function in (
        ("compare", compare),
        ("look-ahead", look_ahead),
        ("trend", trend),
    ):
        app.command(name)(function)
