"""Open a snapshot, queue its build, void it (ADR-0015).

``OpenScheduleSnapshot`` makes the record the XER file is attached to (slot ``xer``);
``StartScheduleSnapshot`` fixes the file and queues the build in ``job_queue``; the worker
(``tl_mod_schedule.build``) reads the file in the resource envelope. Opening and starting are open
to any signed-in person: they create an unpublished, immutable snapshot and change nothing a
reader of the schedule sees. Voiding is the document controller's. A person's file is
checked before it is queued (it must be the one available file of the slot, within the size limit),
and the same file is never queued twice for one schedule.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_adapters.queue import job_queue_for
from tl_core.files.queries import list_files
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.text import clean_optional_text, clean_text
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow
from tl_xer import limits as xer_limits

from tl_mod_schedule import limits, registry
from tl_mod_schedule.common import append, correlated, require_project, transition
from tl_mod_schedule.errors import (
    DuplicateSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    SnapshotStateError,
    SourceFileError,
    TooManyOpenSnapshotsError,
)
from tl_mod_schedule.limits import MAX_P6_PROJECT, MAX_REASON
from tl_mod_schedule.names import (
    INVALID,
    JOB_KIND_BUILD,
    SCHEDULE_SNAPSHOT,
    SLOT_XER,
    SNAPSHOT_DEFINED,
    SNAPSHOT_QUEUED,
    SNAPSHOT_TABLE,
    UPLOADED,
    VALID,
)

DEFAULT_MAX_ATTEMPTS = 2


class OpenScheduleSnapshot(Command):
    """Open the next snapshot of a schedule; the XER file is attached to it next."""

    model_config = ConfigDict(extra="forbid")

    schedule_id: str
    p6_project: str | None = Field(default=None, min_length=1, max_length=MAX_P6_PROJECT)

    @field_validator("p6_project")
    @classmethod
    def _plain(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class StartScheduleSnapshot(Command):
    """Fix the snapshot's XER file and queue its build."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str


class VoidScheduleSnapshot(Command):
    """Void a snapshot that is not the schedule's current or an earlier one."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return clean_text(value)


def load_snapshot(uow: UnitOfWork, cmd: Command, snapshot_id: str) -> registry.SnapshotRow:
    """The snapshot, in the command's scope. Raises ``SnapshotNotFoundError``."""
    found = registry.get_snapshot(uow.conn(), snapshot_id)
    if found is None or found.scope != cmd.scope:
        raise SnapshotNotFoundError(f"no snapshot {snapshot_id!r} in scope {cmd.scope!r}")
    return found


def handle_open_schedule_snapshot(uow: UnitOfWork, cmd: OpenScheduleSnapshot) -> CommandResult:
    """Create the snapshot record, numbered after the schedule's last. State: Uploaded."""
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    schedule = registry.get_schedule(conn, cmd.schedule_id)
    if schedule is None or schedule.scope != cmd.scope:
        raise ScheduleNotFoundError(f"no schedule {cmd.schedule_id!r} in scope {cmd.scope!r}")
    if registry.open_count(conn, schedule.id) >= limits.MAX_OPEN_SNAPSHOTS:
        raise TooManyOpenSnapshotsError(
            f"schedule {schedule.code} already has {limits.MAX_OPEN_SNAPSHOTS} snapshots waiting "
            "for a build; wait for the worker or void one"
        )
    number = registry.next_number(conn, schedule.id)
    return create_module_record(
        uow,
        cmd,
        record_type=SCHEDULE_SNAPSHOT,
        title=f"{schedule.title} snapshot {number}",
        key=f"{schedule.code}#{number}",
        composed_key=True,
        extra_events=[
            NewEvent(
                event_type=SNAPSHOT_DEFINED,
                payload={
                    "schedule_id": schedule.id,
                    "schedule_code": schedule.code,
                    "number": number,
                    "p6_project_option": cmd.p6_project,
                },
            )
        ],
    )


_SAME_FILE_SQL = text(
    f"SELECT t.id FROM {SNAPSHOT_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE t.schedule_id = :schedule AND t.source_sha256 = :sha AND t.id <> :id "
    "AND COALESCE(r.status, 'Uploaded') <> 'Void'"
)


def handle_start_schedule_snapshot(uow: UnitOfWork, cmd: StartScheduleSnapshot) -> CommandResult:
    """Record the file, queue the build. Appends ``ScheduleSnapshot.Queued``.

    Raises ``SnapshotStateError`` (not Uploaded, or already queued), ``SourceFileError`` (no file,
    more than one, not yet available, over the size limit) and ``DuplicateSnapshotError``.
    """
    cmd = correlated(cmd)
    snapshot = load_snapshot(uow, cmd, cmd.snapshot_id)
    if snapshot.state != UPLOADED or snapshot.queued:
        raise SnapshotStateError(
            f"snapshot {snapshot.key} is {snapshot.state}"
            + (" and its build is already queued" if snapshot.queued else "")
            + "; a build is queued once, for an Uploaded snapshot"
        )
    files = list_files(uow, cmd.scope, snapshot.id, slot=SLOT_XER, current_only=False)
    live = [f for f in files if f.superseded_by is None and f.status != "rejected"]
    if not live:
        raise SourceFileError(f"snapshot {snapshot.key} has no XER file; attach one first")
    if len(live) > 1:
        raise SourceFileError(f"snapshot {snapshot.key} has more than one XER file")
    source = live[0]
    if source.status != "available":
        raise SourceFileError(f"the XER file of {snapshot.key} is still being scanned")
    if source.size > xer_limits.MAX_BYTES:
        raise SourceFileError(
            f"the XER file is {source.size} bytes; the limit is {xer_limits.MAX_BYTES}"
        )
    twin = (
        uow.conn()
        .execute(
            _SAME_FILE_SQL,
            {"schedule": snapshot.schedule_id, "sha": source.sha256, "id": snapshot.id},
        )
        .first()
    )
    if twin is not None:
        raise DuplicateSnapshotError(
            f"another snapshot of {snapshot.schedule_code} was made from this file (same SHA-256)"
        )
    done = append(
        uow,
        cmd,
        snapshot.id,
        SCHEDULE_SNAPSHOT,
        [
            NewEvent(
                event_type=SNAPSHOT_QUEUED,
                payload={
                    "source_file_id": source.file_id,
                    "source_name": source.filename,
                    "source_sha256": source.sha256,
                    "source_size": source.size,
                    "requested_by": cmd.actor,
                },
            )
        ],
    )
    job_queue_for(uow.conn()).enqueue(
        uow.conn(),
        job_id=snapshot.id,
        kind=JOB_KIND_BUILD,
        scope=cmd.scope,
        now=utcnow(),
        max_attempts=DEFAULT_MAX_ATTEMPTS,
    )
    return CommandResult(
        stream_id=snapshot.id, key=snapshot.key, version=done.new_version, events=done.events
    )


def handle_void_schedule_snapshot(uow: UnitOfWork, cmd: VoidScheduleSnapshot) -> CommandResult:
    """Uploaded, Invalid or Valid to Void. A published or processing snapshot cannot be voided.

    A snapshot whose build is queued but not claimed has its queue row cancelled by the worker
    (the kind refuses a snapshot that is not Uploaded or Processing).
    """
    cmd = correlated(cmd)
    snapshot = load_snapshot(uow, cmd, cmd.snapshot_id)
    if snapshot.state not in (UPLOADED, INVALID, VALID):
        raise SnapshotStateError(
            f"snapshot {snapshot.key} is {snapshot.state}; only an Uploaded, Invalid or Valid "
            "snapshot can be voided"
        )
    moved = transition(uow, cmd, snapshot.id, "void", reason=cmd.reason)
    return CommandResult(
        stream_id=snapshot.id, key=snapshot.key, version=moved.version, events=moved.events
    )
