"""`tl awp look-ahead` and the `tl awp week` group: the planner's weekly cycle (P2-I5-T04).

The look-ahead is a read of the next weeks with the IWPs linked to each activity. The week verbs
build one S4a command each (``tl_mod_awp.commands``) and run it through ``awp_write._execute``;
the handlers check the state, the word and the stale version, so this module repeats none of
those checks. ``--expected-version`` defaults to the plan's version read in the same unit of work.
A plan is named by its ISO week ``YYYY-Www``; an IWP by its number.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

import typer
from sqlalchemy import Connection
from tl_adapters.db import DbTarget, open_uow
from tl_core.confidentiality import Viewer
from tl_core.services.commands import Command
from tl_core.uow import UnitOfWork
from tl_mod_awp import kpis, week_views
from tl_mod_awp.commands import CloseWeek, CommitIwpToWeek, OpenWeeklyPlan, RecordWeekOutcome
from tl_mod_awp.look_ahead_view import look_ahead_view
from tl_mod_awp.week_views import WeekRow
from tl_mod_schedule import views as schedule_views

from tl_cli.awp_iwp_write import _iwp_id
from tl_cli.awp_write import _execute, _line
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    cell,
    fail,
    scope_of,
    service_errors,
)
from tl_cli.session import session_viewer

_Schedule = Annotated[
    str, typer.Option("--schedule", help="The schedule's code, for example MAIN.")
]
_LIST_LIMIT = 520  # the most plans a resolution or a count reads


def _day(text: str | None) -> date:
    """``--date`` as a day; today when it is not given."""
    if text is None:
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError:
        fail(f"--date must be YYYY-MM-DD, not {text!r}")


def _plan(conn: Connection, scope: str, viewer: Viewer, week: str) -> WeekRow:
    """The plan named ``YYYY-Www`` that the viewer may read (a missing or hidden one is refused)."""
    for row in week_views.list_weeks(conn, scope, viewer, limit=_LIST_LIMIT):
        if row.week == week:
            return row
    fail(f"no week {week}")


def _plan_version(uow: UnitOfWork, project: str, week: str, viewer: Viewer) -> tuple[str, int]:
    """The id and the current version of the plan named ``week``, read in this unit of work."""
    conn = uow.conn()
    row = _plan(conn, scope_of(project), viewer, week)
    detail = week_views.week_detail(conn, row.id, viewer)
    return row.id, detail.version


def week_look_ahead(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    snapshot: Annotated[
        int | None, typer.Option("--snapshot", min=1, help="A snapshot (default: current).")
    ] = None,
    weeks: Annotated[int, typer.Option("--weeks", help="Weeks to look ahead, 1 to 26.")] = 4,
) -> None:
    """The activities under way or starting in the next weeks, with the IWPs linked to each.

    Lines: `window <start> to <end>  weeks <n>  need-by lead <lead>w`, `activities: <n>`, then
    `<activity id>  <phase>  <early start|->  <critical *|->  <name>` per activity and
    `  <number>  <state>  need-by <date|->  ready <ok>/<total>|-  blocking <n>` per linked IWP
    (`ready -` when it was never evaluated).
    """
    db: DbTarget = ctx.obj
    viewer = session_viewer(db)
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        found = schedule_views.find_schedule(conn, scope, schedule)
        snap = schedule_views.find_snapshot(conn, found, snapshot, built=True)
        try:
            r = look_ahead_view(conn, scope, snap, viewer, weeks=weeks)
        except ValueError as problem:
            fail(str(problem))
    typer.echo(
        f"window {r.window_start} to {r.window_end}  weeks {r.weeks}  need-by lead {r.lead_weeks}w"
    )
    typer.echo(f"activities: {len(r.items)}")
    for item in r.items:
        a = item.row
        critical = "*" if a.critical else "-"
        typer.echo(
            f"{a.activity_id}  {a.phase}  {cell(a.early_start)}  {critical}  {cell(a.name, 40)}"
        )
        for iwp in item.iwps:
            ready = f"{iwp.checks_ok}/{iwp.checks_total}" if iwp.evaluated else "-"
            typer.echo(
                f"  {iwp.number}  {iwp.state}  need-by {cell(iwp.need_by)}  "
                f"ready {ready}  blocking {iwp.open_blocking}"
            )


def week_open(
    ctx: typer.Context,
    project: Project,
    date_: Annotated[
        str | None, typer.Option("--date", help="A day of the week, YYYY-MM-DD. Default today.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Open the weekly plan of the ISO week of the day. Prints `open <week>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    day = _day(date_)
    monday = day - timedelta(days=day.weekday())
    year, week, _ = monday.isocalendar()
    label = f"{year}-W{week:02d}"

    def build(uow: UnitOfWork) -> Command:
        return OpenWeeklyPlan(actor=who, source=SOURCE, scope=scope_of(project), week_start=monday)

    _line("open", label, _execute(db, build))


def week_commit(
    ctx: typer.Context,
    week: Annotated[str, typer.Argument(help="The plan's ISO week, YYYY-Www.")],
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    project: Project,
    hours: Annotated[str, typer.Option("--hours", help="The committed hours, for example 40.0.")],
    foreman: Annotated[
        str | None, typer.Option("--foreman", help="The foreman, as user:X.")
    ] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The plan version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Commit an IWP to the week's plan. Prints `commit <week>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    viewer = session_viewer(db)

    def build(uow: UnitOfWork) -> Command:
        plan, current = _plan_version(uow, project, week, viewer)
        iwp = _iwp_id(uow, project, number)
        return CommitIwpToWeek(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            plan_id=plan,
            iwp_id=iwp,
            committed_hours=hours,
            foreman=foreman,
            expected_version=expected_version or current,
        )

    _line("commit", week, _execute(db, build))


def week_outcome(
    ctx: typer.Context,
    week: Annotated[str, typer.Argument(help="The plan's ISO week, YYYY-Www.")],
    number: Annotated[str, typer.Argument(help="The IWP number.")],
    result: Annotated[str, typer.Argument(help="done or missed.")],
    project: Project,
    reason: Annotated[
        str | None, typer.Option("--reason", help="The miss reason key (for missed).")
    ] = None,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The plan version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Record the outcome of a committed IWP: `done` or `missed`. Prints
    `outcome <week>  version <n>`."""
    if result not in ("done", "missed"):
        fail(f"{result!r} is not done or missed")
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    viewer = session_viewer(db)

    def build(uow: UnitOfWork) -> Command:
        plan, current = _plan_version(uow, project, week, viewer)
        iwp = _iwp_id(uow, project, number)
        return RecordWeekOutcome(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            plan_id=plan,
            iwp_id=iwp,
            outcome=result,  # type: ignore[arg-type]
            miss_reason=reason,
            expected_version=expected_version or current,
        )

    _line("outcome", week, _execute(db, build))


def week_close(
    ctx: typer.Context,
    week: Annotated[str, typer.Argument(help="The plan's ISO week, YYYY-Www.")],
    project: Project,
    expected_version: Annotated[
        int | None, typer.Option("--expected-version", min=1, help="The plan version you read.")
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Close the week's plan and give its PPC. Prints `close <week>  version <n>`."""
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    viewer = session_viewer(db)

    def build(uow: UnitOfWork) -> Command:
        plan, current = _plan_version(uow, project, week, viewer)
        return CloseWeek(
            actor=who,
            source=SOURCE,
            scope=scope_of(project),
            plan_id=plan,
            expected_version=expected_version or current,
        )

    _line("close", week, _execute(db, build))


def week_ls(ctx: typer.Context, project: Project) -> None:
    """List the weekly plans, the latest first: `weeks: <n>`, then `<week>  <state>  <commitments>
    ppc <x|->` per plan."""
    db: DbTarget = ctx.obj
    viewer = session_viewer(db)
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        rows = week_views.list_weeks(conn, scope, viewer, limit=_LIST_LIMIT)
        counts = [len(week_views.week_detail(conn, r.id, viewer).commitments) for r in rows]
    typer.echo(f"weeks: {len(rows)}")
    for row, commitments in zip(rows, counts, strict=True):
        typer.echo(f"{row.week}  {row.state}  {commitments}  ppc {row.ppc or '-'}")


def week_show(
    ctx: typer.Context,
    week: Annotated[str, typer.Argument(help="The plan's ISO week, YYYY-Www.")],
    project: Project,
) -> None:
    """Show one plan with its commitments and notes. A missing or hidden week is one error."""
    db: DbTarget = ctx.obj
    viewer = session_viewer(db)
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        row = _plan(conn, scope, viewer, week)
        detail = week_views.week_detail(conn, row.id, viewer)
    typer.echo(f"week {detail.week}")
    typer.echo(f"state {detail.state}")
    typer.echo(f"ppc {detail.ppc or '-'}")
    typer.echo(f"commitments {len(detail.commitments)}")
    for c in detail.commitments:
        typer.echo(
            f"  {c.iwp_key}  {c.iwp_state}  {c.committed_hours}  {c.foreman or '-'}  "
            f"{c.outcome or '-'}  {c.miss_reason or '-'}"
        )
    for note in detail.notes:
        typer.echo(f"note: {note}")


def week_ppc(
    ctx: typer.Context,
    project: Project,
    weeks: Annotated[int, typer.Option("--weeks", help="Closed weeks to pool.")] = 4,
) -> None:
    """The PPC pooled over the last closed weeks: `ppc <x|->  weeks <k>`."""
    db: DbTarget = ctx.obj
    viewer = session_viewer(db)
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        conn = uow.conn()
        tile = kpis.ppc_tile(conn, scope, viewer, weeks=weeks)
        closed = [
            r
            for r in week_views.list_weeks(conn, scope, viewer, limit=_LIST_LIMIT)
            if r.state == "Closed"
        ]
    value = "-" if tile.value is None else str(tile.value)
    typer.echo(f"ppc {value}  weeks {min(len(closed), weeks)}")
    if tile.value is None:
        typer.echo(tile.detail)  # "no closed week yet" or "nothing committed in closed weeks"


def week_reasons(ctx: typer.Context, project: Project) -> None:
    """The miss-reason keys of the adopted edition, one per line (keys, never labels)."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    with service_errors(), open_uow(db, readonly=True) as uow:
        keys = week_views.miss_reasons(uow.conn(), scope)
    for key in keys:
        typer.echo(key)


def register(app: typer.Typer) -> None:
    """Add `look-ahead` and the `week` group to ``tl awp``."""
    app.command("look-ahead")(week_look_ahead)
    week_app = typer.Typer(
        help="The weekly plan: open, commit, outcome, close, PPC.", no_args_is_help=True
    )
    app.add_typer(week_app, name="week")
    verbs = (
        ("open", week_open),
        ("ls", week_ls),
        ("show", week_show),
        ("commit", week_commit),
        ("outcome", week_outcome),
        ("close", week_close),
        ("ppc", week_ppc),
        ("reasons", week_reasons),
    )
    for name, function in verbs:
        week_app.command(name)(function)
