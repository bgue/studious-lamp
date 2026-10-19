"""The `tl corr clock` group: the response clocks of correspondence (brief 9 M10).

A clock counts calendar or working days on the project calendar from a day zero to a due date, can
be paused (the pause days do not count), resumed, restarted, met by an answer or cancelled, and
warns at thresholds when the sweep runs. Clocks are named by their key, `<item number>-C<nn>`. All
figures come from the clock's events (recompute from the ledger); `days left` is as of today.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.uow import UnitOfWork
from tl_mod_correspondence import registry, views
from tl_mod_correspondence.handlers.clocks import (
    CancelClock,
    MeetClock,
    PauseClock,
    RestartClock,
    ResumeClock,
    StartClock,
    SweepClocks,
    handle_cancel_clock,
    handle_meet_clock,
    handle_pause_clock,
    handle_restart_clock,
    handle_resume_clock,
    handle_start_clock,
    sweep_clocks,
)

from tl_cli.corr import item_row
from tl_cli.doc import _DEFAULT_ACTOR, _Actor, _fail, _Project, _service_errors
from tl_cli.session import require_controller

app = typer.Typer(
    help="Start, pause, resume, restart, meet and cancel response clocks.", no_args_is_help=True
)

_Key = Annotated[str, typer.Argument(help="The clock key, for example P123-COR-0001-C01.")]
_On = Annotated[str | None, typer.Option("--date", help="YYYY-MM-DD. Default today.")]
_Why = Annotated[str, typer.Option("--reason", help="Why (kept in the history).")]


def clock_row(uow: UnitOfWork, scope: str, project: str, key: str) -> registry.ClockRow:
    found = registry.find_clock(uow.conn(), scope, key)
    if found is None:
        _fail(f"no clock {key!r} in project {project!r}")
    return found


def _line(c: views.ClockView) -> str:
    left = "-" if c.days_left is None else str(c.days_left)
    warn = ",".join(str(w) for w in c.warn_days) or "-"
    return (
        f"{c.key} {c.effective_state} due {c.due_on} left {left} {c.duration_days} "
        f"{c.day_type} warn {warn} {c.kind} {c.label}"
    )


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: _Project,
    overdue: Annotated[
        bool, typer.Option("--overdue", help="Only clocks past their due date.")
    ] = False,
    all_clocks: Annotated[
        bool, typer.Option("--all", help="Include met and cancelled clocks.")
    ] = False,
    due_to: Annotated[
        str | None, typer.Option("--due-to", help="Due on or before YYYY-MM-DD.")
    ] = None,
) -> None:
    """Clocks soonest due first: key, state, due date, days left, length, type, warnings, label."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = views.clock_views(
            uow.conn(),
            f"project:{project}",
            open_only=not all_clocks,
            overdue_only=overdue,
            due_to=due_to,
        )
    for clock in found:
        typer.echo(_line(clock))


@app.command("start")
def start(
    ctx: typer.Context,
    number: Annotated[str, typer.Argument(help="The item number.")],
    project: _Project,
    label: Annotated[str, typer.Option("--label", help="What the clock waits for.")],
    days: Annotated[int, typer.Option("--days", min=1, help="Length in days.")],
    day_type: Annotated[str, typer.Option("--type", help="calendar or working.")] = "calendar",
    kind: Annotated[
        str, typer.Option("--kind", help="response_from_them, response_from_us, time_bar.")
    ] = "response_from_them",
    warn: Annotated[
        list[int] | None, typer.Option("--warn", help="Days before due. Repeat.")
    ] = None,
    start_on: Annotated[str | None, typer.Option("--start-on")] = None,
    start_reason: Annotated[str | None, typer.Option("--start-reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Start a response clock on an item."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = item_row(uow, scope, project, number)
        made = handle_start_clock(
            uow,
            StartClock.model_validate(
                {
                    "actor": actor, "source": "cli", "scope": scope, "item_id": row.id,
                    "label": label, "kind": kind, "duration_days": days, "day_type": day_type,
                    "warn_days": warn or [], "start_on": start_on, "start_reason": start_reason,
                }
            ),
        )  # fmt: skip
        view = views.clock_view_by_id(uow.conn(), scope, made.stream_id)
    typer.echo(f"started {made.key}")
    typer.echo(_line(view))


def _act(ctx: typer.Context, project: str, key: str, build, handler, message: str) -> None:  # type: ignore[no-untyped-def]
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = clock_row(uow, scope, project, key)
        handler(uow, build(scope, row.id))
        view = views.clock_view_by_id(uow.conn(), scope, row.id)
    typer.echo(f"{message} {key}")
    typer.echo(_line(view))


@app.command("pause")
def pause(
    ctx: typer.Context, key: _Key, project: _Project, reason: _Why, on: _On = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:  # fmt: skip
    """Pause a running clock: the days of the pause do not count."""
    _act(ctx, project, key, lambda scope, cid: PauseClock(
        actor=actor, source="cli", scope=scope, clock_id=cid, reason=reason, on=on),
        handle_pause_clock, "paused")  # fmt: skip


@app.command("resume")
def resume(
    ctx: typer.Context, key: _Key, project: _Project, on: _On = None,
    reason: Annotated[
        str | None, typer.Option("--reason", help="Needed for a date before today.")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:  # fmt: skip
    """Run a paused clock again; its due date moves by the days of the pause."""
    _act(ctx, project, key, lambda scope, cid: ResumeClock(
        actor=actor, source="cli", scope=scope, clock_id=cid, reason=reason, on=on),
        handle_resume_clock, "resumed")  # fmt: skip


@app.command("restart")
def restart(
    ctx: typer.Context, key: _Key, project: _Project, reason: _Why, on: _On = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:  # fmt: skip
    """Count again from a new day zero with the same length."""
    _act(ctx, project, key, lambda scope, cid: RestartClock(
        actor=actor, source="cli", scope=scope, clock_id=cid, reason=reason, on=on),
        handle_restart_clock, "restarted")  # fmt: skip


@app.command("meet")
def meet(
    ctx: typer.Context, key: _Key, project: _Project, on: _On = None,
    by: Annotated[
        str | None, typer.Option("--by", help="The number of the answering item.")
    ] = None,
    reason: Annotated[str | None, typer.Option("--reason")] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:  # fmt: skip
    """Close a clock because the answer came (late is allowed; the date says so)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with _service_errors(), open_uow(db) as uow:
        row = clock_row(uow, scope, project, key)
        answer = item_row(uow, scope, project, by).id if by else None
        handle_meet_clock(
            uow,
            MeetClock(actor=actor, source="cli", scope=scope, clock_id=row.id,
                      response_id=answer, reason=reason, on=on),
        )  # fmt: skip
    typer.echo(f"met {key}")


@app.command("cancel")
def cancel(
    ctx: typer.Context, key: _Key, project: _Project, reason: _Why, on: _On = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:  # fmt: skip
    """Close a clock because no answer is needed any more."""
    _act(ctx, project, key, lambda scope, cid: CancelClock(
        actor=actor, source="cli", scope=scope, clock_id=cid, reason=reason, on=on),
        handle_cancel_clock, "cancelled")  # fmt: skip


@app.command("sweep")
def sweep(
    ctx: typer.Context,
    project: _Project,
    on: Annotated[
        str | None, typer.Option("--date", help="Judge as of this day (not after today).")
    ] = None,
    actor: _Actor = _DEFAULT_ACTOR,
) -> None:
    """Record the warnings and expiries that are due (controller). Safe to repeat."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with _service_errors(), open_uow(db) as uow:
        recorded, skipped = sweep_clocks(
            uow, SweepClocks(actor=actor, source="cli", scope=scope, on=on)
        )
    if not recorded:
        typer.echo("nothing to record")
    for event in recorded:
        detail = event.payload.get("level", event.payload.get("days_overdue", ""))
        typer.echo(
            f"{event.event_type.removeprefix('ResponseClock.').lower()} {event.stream_id} {detail}"
        )
    if skipped:  # a clock the sweep could not judge is said aloud, not left to be found late
        typer.echo(
            f"skipped {len(skipped)} clock(s) it could not judge: {', '.join(skipped)}", err=True
        )
        raise typer.Exit(code=2)
