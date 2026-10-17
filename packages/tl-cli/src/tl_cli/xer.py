"""`tl xer define|upload|publish|void|link|worker|reconcile`: P6 schedules as XER snapshots (P1-I4).

A schedule is the series of snapshots of one P6 project; each upload of an XER file is an immutable
snapshot (brief 9 M11). `upload` opens the next snapshot, attaches the file and queues its build;
`worker` runs the queue (the file is read in the resource envelope of ADR-0014); `publish` makes a
valid snapshot the current schedule; `link` links a record to an activity by its stable id. Reads
(`ls`, `show`, `compare`, ...) are in `tl_cli.xer_read`. The rules are the module's
(`tl_mod_schedule`, ADR-0015); these commands parse options and print.

Who may: defining, publishing and voiding are a document controller's (or an admin's); opening a
snapshot, uploading a file, starting a build and linking are any signed-in person's; the worker and
`reconcile` are the admin's (they write as the service).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_core.files.service import CompleteUpload, RegisterUpload
from tl_core.services.queries import get_record
from tl_mod_schedule import views
from tl_mod_schedule.handlers.activity import LinkActivity, handle_link_activity
from tl_mod_schedule.handlers.publish import (
    PublishScheduleSnapshot,
    handle_publish_schedule_snapshot,
)
from tl_mod_schedule.handlers.schedules import DefineSchedule, handle_define_schedule
from tl_mod_schedule.handlers.snapshots import (
    OpenScheduleSnapshot,
    StartScheduleSnapshot,
    VoidScheduleSnapshot,
    handle_open_schedule_snapshot,
    handle_start_schedule_snapshot,
    handle_void_schedule_snapshot,
)
from tl_mod_schedule.names import SCHEDULE_TYPES, SLOT_XER
from tl_mod_schedule.reconcile import reconcile_tables, requeue
from tl_mod_schedule.worker import build_worker
from tl_xer import limits as xer_limits

from tl_cli import xer_compare, xer_read, xer_report
from tl_cli.derive_support import (
    DEV_ACTOR,
    SOURCE,
    Actor,
    Project,
    acting,
    fail,
    file_service,
    service_errors,
)
from tl_cli.session import require_admin, require_controller

app = typer.Typer(help="P6 schedules as XER snapshots.", no_args_is_help=True)
xer_read.register(app)
xer_compare.register(app)
xer_report.register(app)

_Schedule = Annotated[
    str, typer.Option("--schedule", help="The schedule's code, for example MAIN.")
]
_Number = Annotated[int, typer.Argument(min=1, help="The snapshot's number within the schedule.")]
_CHUNK = 1024 * 1024


def _snapshot(db: DbTarget, scope: str, code: str, number: int) -> tuple[str, str]:
    """``(schedule id, snapshot id)``; the module's error (`error: ...`) when there is none."""
    with open_uow(db, readonly=True) as uow:
        schedule = views.find_schedule(uow.conn(), scope, code)
        snapshot = views.find_snapshot(uow.conn(), schedule, number)
    return schedule.id, snapshot.id


@app.command("define")
def define(
    ctx: typer.Context,
    code: Annotated[str, typer.Argument(help="The schedule's code, for example MAIN.")],
    project: Project,
    name: Annotated[str, typer.Option("--name", help="A title for people.")],
    schedule_type: Annotated[
        str, typer.Option("--type", help=f"One of {', '.join(SCHEDULE_TYPES)}.")
    ] = "current",
    owner: Annotated[str | None, typer.Option("--owner", help="Who owns the schedule.")] = None,
    p6_project: Annotated[
        str | None,
        typer.Option("--p6-project", help="The P6 project to read when a file holds several."),
    ] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Register a schedule (controller). Prints `defined <code> <id>`."""
    db: DbTarget = ctx.obj
    require_controller(db)
    with service_errors(), open_uow(db) as uow:
        made = handle_define_schedule(
            uow,
            DefineSchedule(
                actor=acting(db, actor),
                source=SOURCE,
                scope=f"project:{project}",
                code=code,
                name=name,
                schedule_type=schedule_type,
                owner=owner,
                p6_project=p6_project,
            ),
        )
    typer.echo(f"defined {made.key} {made.stream_id}")


@app.command("upload")
def upload(
    ctx: typer.Context,
    path: Annotated[
        Path, typer.Argument(help="The XER file.", exists=True, dir_okay=False, readable=True)
    ],
    project: Project,
    schedule: _Schedule,
    p6_project: Annotated[
        str | None,
        typer.Option("--p6-project", help="The P6 project to read from this file (if several)."),
    ] = None,
    no_start: Annotated[
        bool, typer.Option("--no-start", help="Attach the file but do not queue the build.")
    ] = False,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Open the next snapshot, attach the XER file and queue its build.

    Prints `queued <key> <id>` (`uploaded ...` with --no-start). A worker (`tl xer worker`) builds
    it. The same file is never queued twice for a schedule.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    size = path.stat().st_size
    if size > xer_limits.MAX_BYTES:
        fail(f"{path.name} is {size} bytes; an XER file may be at most {xer_limits.MAX_BYTES}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    service = file_service()
    who = acting(db, actor)
    with service_errors():
        with open_uow(db, readonly=True) as uow:
            found = views.find_schedule(uow.conn(), scope, schedule)
        with open_uow(db) as uow:  # one transaction: a refused upload leaves no snapshot behind
            opened = handle_open_schedule_snapshot(
                uow,
                OpenScheduleSnapshot(
                    actor=who,
                    source=SOURCE,
                    scope=scope,
                    schedule_id=found.id,
                    p6_project=p6_project,
                ),
            )
            ticket = service.register_upload(
                uow,
                RegisterUpload(
                    actor=who,
                    source=SOURCE,
                    scope=scope,
                    record_id=opened.stream_id,
                    slot=SLOT_XER,
                    filename=path.name,
                    content_type="application/octet-stream",
                    size=size,
                    sha256=digest.hexdigest(),
                ),
            )
            done = CompleteUpload(actor=who, source=SOURCE, scope=scope, upload_id=ticket.upload_id)
            if ticket.exists:
                service.complete_upload(uow, done)
            else:
                with path.open("rb") as source_file:
                    service.complete_upload(uow, done, source_file)
            if not no_start:
                handle_start_schedule_snapshot(
                    uow,
                    StartScheduleSnapshot(
                        actor=who, source=SOURCE, scope=scope, snapshot_id=opened.stream_id
                    ),
                )
    if no_start:
        typer.echo(f"uploaded {opened.key} {opened.stream_id}")
        return
    typer.echo(f"queued {opened.key} {opened.stream_id}")


@app.command("start")
def start(
    ctx: typer.Context,
    number: _Number,
    project: Project,
    schedule: _Schedule,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Queue the build of an uploaded snapshot (after `upload --no-start`)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with service_errors():
        _, snapshot_id = _snapshot(db, scope, schedule, number)
        with open_uow(db) as uow:
            made = handle_start_schedule_snapshot(
                uow,
                StartScheduleSnapshot(
                    actor=acting(db, actor), source=SOURCE, scope=scope, snapshot_id=snapshot_id
                ),
            )
    typer.echo(f"queued {made.key} {made.stream_id}")


@app.command("publish")
def publish(
    ctx: typer.Context,
    number: _Number,
    project: Project,
    schedule: _Schedule,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Make a valid snapshot the current schedule (controller).

    Prints `published <key>`. When the schedule has links to activities, the worker then flags the
    ones whose activity is not in this snapshot and restores the ones whose activity came back (a
    queued job, in bounded runs); until it has run they still show the old state.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with service_errors():
        _, snapshot_id = _snapshot(db, scope, schedule, number)
        with open_uow(db) as uow:
            made = handle_publish_schedule_snapshot(
                uow,
                PublishScheduleSnapshot(
                    actor=acting(db, actor), source=SOURCE, scope=scope, snapshot_id=snapshot_id
                ),
            )
    typer.echo(f"published {made.key}")
    checked = [e for e in made.events if e.event_type == "ScheduleSnapshot.MadeCurrent"]
    if checked and checked[0].payload.get("orphan_check_queued"):
        typer.echo(
            "links to activities will be checked by the worker (`tl xer worker`): "
            "those whose activity left are flagged, those whose activity is back are restored"
        )


@app.command("void")
def void(
    ctx: typer.Context,
    number: _Number,
    project: Project,
    schedule: _Schedule,
    reason: Annotated[str, typer.Option("--reason", help="Why.")],
    actor: Actor = DEV_ACTOR,
) -> None:
    """Void a snapshot that is not published (controller)."""
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    require_controller(db)
    with service_errors():
        _, snapshot_id = _snapshot(db, scope, schedule, number)
        with open_uow(db) as uow:
            made = handle_void_schedule_snapshot(
                uow,
                VoidScheduleSnapshot(
                    actor=acting(db, actor),
                    source=SOURCE,
                    scope=scope,
                    snapshot_id=snapshot_id,
                    reason=reason,
                ),
            )
    typer.echo(f"voided {made.key}")


@app.command("link")
def link(
    ctx: typer.Context,
    record: Annotated[str, typer.Argument(help="The key of the record to link.")],
    activity: Annotated[str, typer.Argument(help="The P6 activity id, for example A1230.")],
    project: Project,
    schedule: _Schedule,
    pin: Annotated[
        int | None,
        typer.Option("--pin", min=1, help="Pin the link to this snapshot number (default: float)."),
    ] = None,
    note: Annotated[str | None, typer.Option("--note")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Link a record to an activity by its stable id. Prints `linked <record> -> <ref key> <id>`.

    A floating link resolves to the current snapshot; --pin N resolves to snapshot N.
    """
    db: DbTarget = ctx.obj
    scope = f"project:{project}"
    with service_errors(), open_uow(db) as uow:
        found = views.find_schedule(uow.conn(), scope, schedule)
        source = get_record(uow, scope, record)
        if source is None:
            fail(f"no record with key {record!r} in project {project!r}")
        made = handle_link_activity(
            uow,
            LinkActivity(
                actor=acting(db, actor),
                source=SOURCE,
                scope=scope,
                from_id=str(source["id"]),
                schedule_id=found.id,
                activity_id=activity,
                pin=pin,
                note=note,
            ),
        )
    typer.echo(f"linked {record} -> {schedule}/{activity} {made.stream_id}")


@app.command("worker")
def worker(
    ctx: typer.Context,
    once: Annotated[bool, typer.Option("--once", help="Run what is queued, then exit.")] = False,
    requeue_lost: Annotated[
        bool, typer.Option("--requeue", help="First queue again builds a restore lost.")
    ] = False,
    idle: Annotated[
        float, typer.Option("--idle", min=0.1, help="Seconds to wait when idle.")
    ] = 2.0,
    timeout: Annotated[
        float, typer.Option("--timeout", min=1, help="Seconds reading one file may take.")
    ] = 60.0,
) -> None:
    """Run the build queue (admin).

    Prints `ran <snapshot id> <kind> <outcome>` per build and `worker done: ran=<n>`. Without
    --once it waits for more until interrupted (Ctrl-C ends it cleanly).
    """
    db: DbTarget = ctx.obj
    require_admin(db)
    service = file_service()
    with service_errors():
        if requeue_lost:
            typer.echo(f"requeued {requeue(db)}")
        ran = 0
        with build_worker(db, service, timeout_s=timeout) as made:
            try:
                while True:
                    result = made.runner.run_once()
                    if result is None:
                        if once:
                            break
                        time.sleep(idle)
                        continue
                    typer.echo(f"ran {result.job_id} {result.kind} {result.outcome}")
                    ran += 1
            except KeyboardInterrupt:
                pass
    typer.echo(f"worker done: ran={ran}")


@app.command("reconcile")
def reconcile(
    ctx: typer.Context,
    project: Annotated[
        str | None, typer.Option("--project", help="Only this project (default: all).")
    ] = None,
    timeout: Annotated[
        float, typer.Option("--timeout", min=1, help="Seconds reading one file may take.")
    ] = 60.0,
) -> None:
    """After a restore: queue lost builds again and write the typed rows from the XER files (admin).

    Writes the typed rows from the files first, then queues what the queue lost. Prints
    `requeued <n>`, one `<key> <outcome> <detail>` line per built snapshot and a summary. Exits 1
    when a file no longer gives the rows the ledger recorded (`mismatch`) or cannot be read.
    """
    db: DbTarget = ctx.obj
    require_admin(db)
    service = file_service()
    with service_errors():
        # the typed rows first: the flagging of links is judged against them
        done = reconcile_tables(
            db, service, scope=None if project is None else f"project:{project}", timeout_s=timeout
        )
        typer.echo(f"requeued {requeue(db)}")
    for item in done:
        typer.echo(f"{item.key} {item.outcome} {item.detail}")
    bad = [i for i in done if i.outcome in ("mismatch", "unreadable")]
    rebuilt = sum(1 for i in done if i.outcome == "rebuilt")
    typer.echo(f"reconciled {len(done)} snapshot(s): rebuilt={rebuilt} problems={len(bad)}")
    if bad:
        raise typer.Exit(code=1)
