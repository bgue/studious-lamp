# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl xer ls|show|activities|activity|resolve|health`: reads of schedules (P1-I4-T09b).

None of these writes anything. The reads are the module's (`tl_mod_schedule.views`); these
commands parse options and print one line per fact, with two spaces between fields, so that a
person can read them and a script can split them. A missing schedule, snapshot or activity is the
module's error (`error: ...` on stderr, exit 1).


STUB (P1-I4-T09b): the bodies of `ls`, `show`, `activities`, `activity`, `resolve` and `health`
are `NotImplementedError`; the options, docstrings (the exact output) and `register` are written.
The ticket fills the bodies by their STEPS comments.
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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.schedule_views(conn, scope)`.
    # 3. No schedules: print `no schedules in project <project>`.
    # 4. Per schedule print the line in the docstring; `cell(x)` writes `-` for a missing
    #    value, `cell(s.title, 60)` cuts the title.
    raise NotImplementedError


def show(ctx: typer.Context, project: Project, schedule: _Schedule) -> None:
    """Show a schedule and its snapshots, newest first.

    Lines: `schedule <code>`, `title <title>`, `type <type>`, `p6 project <name or ->`,
    `owner <name or ->`, `current <n or ->  data date <date or ->`, `links being checked`
    (only while the flagging job has work left), then for each snapshot
    `snapshot <n>  <state>  data date <date or ->  activities <n or ->  errors <n or ->
    warnings <n or ->  <source file or ->`; the current snapshot has `  current` after its state.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.schedule_detail(conn, scope,
    #    schedule)`.
    # 3. Collect the lines of the docstring in a list in that order; add `links being
    #    checked` after the `current` line only when `d.links_being_checked` is true.
    # 4. A snapshot line has `  current` after its state when `s.is_current`. Use `cell()`
    #    for every value that can be missing.
    # 5. Print each line with `typer.echo`.
    raise NotImplementedError


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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.activity_page(conn, scope,
    #    schedule, snapshot, critical=..., status=status, search=search, limit=limit,
    #    offset=offset)`; pass `critical=True` when the flag is set and `None` otherwise
    #    (`False` would ask for the non-critical ones).
    # 3. Print the header with `page.snapshot_key`, `cell(page.data_date)`,
    #    `len(page.rows)`, `page.total` and `page.offset`.
    # 4. Per row print the line of the docstring: float with `hours(a.total_float_hr)` (the
    #    helper above), percent with `:g`, `critical` or `ok`, the name with `cell(a.name,
    #    60)`.
    raise NotImplementedError


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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.activity_detail(conn, scope,
    #    schedule, activity_id, snapshot)`.
    # 3. Collect the lines of the docstring in a list: the eight lines about the activity,
    #    then `predecessors <n>` and one line per relationship `  <pred_activity_id>
    #    <relationship_type>  lag <hours(lag_hr)>`, then `successors <n>` and one line per
    #    relationship with `succ_activity_id`.
    # 4. `early`, `late` and `actual` lines are `<name> <cell(start)> -> <cell(finish)>`.
    #    Print each line.
    raise NotImplementedError


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
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.resolution(conn, scope, schedule,
    #    activity_id, views.as_of_of(as_of))`; `as_of_of` turns the option text into what
    #    the view takes.
    # 3. The snapshot is `-` when `r.snapshot_number` is `None`, else `<schedule>#<number>`.
    #    Print `<activity id>  <state>  <snapshot>  data date <cell(r.data_date)>`.
    # 4. When `r.activity` is not `None`, print the second line of the docstring.
    raise NotImplementedError


def health(ctx: typer.Context, project: Project, schedule: _Schedule) -> None:
    """List the links whose activity is not in the current snapshot (orphaned links).

    `orphaned links: <n>`, then `<link id>  record <id>  activity <id>  last seen <snapshot
    number or ->` for each.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.orphans(conn, scope, schedule)`.
    # 3. Print `orphaned links: <n>`, then one line per link as in the docstring.
    raise NotImplementedError


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
