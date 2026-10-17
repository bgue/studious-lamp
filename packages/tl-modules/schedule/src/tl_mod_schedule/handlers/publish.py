"""``PublishScheduleSnapshot``: make a valid snapshot the schedule's current one (ADR-0015).

One unit of work of a small, fixed size: the previous current snapshot becomes Superseded, this
one Published, ``ScheduleSnapshot.MadeCurrent`` and ``Schedule.SnapshotPublished`` are appended,
and a job is queued (``orphans.py``) that makes the links to the schedule's activities agree with
the new snapshot: links to an activity that is gone are flagged stale, and the ones the module
flagged earlier are restored when it is back (brief 7.3). The job runs in bounded runs after the
commit, so until it has finished the links may still show the old state.

Who may run it: the document controller or the admin (ADR-0015). An agent proposes it.

Two checks on the data date, both on parsed dates and not on text: it must be later than the
current snapshot's (the current snapshot is always the latest data date published), and not more
than ``MAX_DATA_DATE_AHEAD_DAYS`` after today by the handler's clock (a data date far in the
future would sit above every later snapshot and freeze the series).
"""

from __future__ import annotations

from datetime import UTC, timedelta

from pydantic import ConfigDict
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork
from tl_core.util import current_effective_time, utcnow

from tl_mod_schedule import limits, registry
from tl_mod_schedule.common import append, correlated, stamp, transition
from tl_mod_schedule.errors import (
    FutureDataDateError,
    ScheduleNotFoundError,
    SnapshotStateError,
    StaleSnapshotError,
)
from tl_mod_schedule.handlers.snapshots import load_snapshot
from tl_mod_schedule.names import (
    SCHEDULE,
    SCHEDULE_SNAPSHOT,
    SCHEDULE_SNAPSHOT_PUBLISHED,
    SNAPSHOT_MADE_CURRENT,
    VALID,
)
from tl_mod_schedule.orphans import has_refs, queue_check


class PublishScheduleSnapshot(Command):
    """Make a Valid snapshot the current snapshot of its schedule."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str


def handle_publish_schedule_snapshot(
    uow: UnitOfWork, cmd: PublishScheduleSnapshot
) -> CommandResult:
    """Publish. Raises ``SnapshotStateError`` (not Valid), ``StaleSnapshotError`` and
    ``FutureDataDateError``."""
    cmd = correlated(cmd)
    conn = uow.conn()
    snapshot = load_snapshot(uow, cmd, cmd.snapshot_id)
    if snapshot.state != VALID:
        raise SnapshotStateError(
            f"snapshot {snapshot.key} is {snapshot.state}; only a Valid snapshot can be published"
        )
    schedule = registry.get_schedule(conn, snapshot.schedule_id)
    if schedule is None:
        raise ScheduleNotFoundError(f"no schedule {snapshot.schedule_id!r}")
    data_date = snapshot.data_date
    assert data_date is not None  # a Valid snapshot was built, so it has a data date
    previous = (
        registry.get_snapshot(conn, schedule.current_snapshot_id)
        if schedule.current_snapshot_id
        else None
    )
    # the handler's clock: simulated time when a simulation sets it, else the real one
    today = (current_effective_time() or utcnow()).astimezone(UTC).replace(tzinfo=None)
    if stamp(data_date) > today + timedelta(days=limits.MAX_DATA_DATE_AHEAD_DAYS):
        raise FutureDataDateError(
            f"snapshot {snapshot.key} has data date {data_date}, more than "
            f"{limits.MAX_DATA_DATE_AHEAD_DAYS} days after today ({today.date().isoformat()}); "
            "a data date that far ahead would freeze the series of snapshots"
        )
    if (
        previous is not None
        and previous.data_date is not None
        and stamp(data_date) <= stamp(previous.data_date)
    ):
        raise StaleSnapshotError(
            f"snapshot {snapshot.key} has data date {data_date}, not later than the current "
            f"snapshot {previous.key} ({previous.data_date})"
        )
    events: list = []  # type: ignore[type-arg]
    if previous is not None:
        events.extend(transition(uow, cmd, previous.id, "supersede").events)
    events.extend(transition(uow, cmd, snapshot.id, "publish").events)
    # The links to activities are made to agree with this snapshot by a job (orphans.py), in runs
    # of bounded size, not in this transaction: the publisher does a small, fixed amount of work.
    queued = has_refs(conn, schedule.id)
    if queued:
        queue_check(conn, schedule.id, cmd.scope)
    marked = append(
        uow,
        cmd,
        snapshot.id,
        SCHEDULE_SNAPSHOT,
        [
            NewEvent(
                event_type=SNAPSHOT_MADE_CURRENT,
                payload={
                    "previous_snapshot_id": previous.id if previous else None,
                    "orphan_check_queued": queued,
                },
            )
        ],
    )
    events.extend(marked.events)
    pointed = append(
        uow,
        cmd,
        schedule.id,
        SCHEDULE,
        [
            NewEvent(
                event_type=SCHEDULE_SNAPSHOT_PUBLISHED,
                payload={
                    "snapshot_id": snapshot.id,
                    "snapshot_number": snapshot.number,
                    "data_date": data_date,
                    "previous_snapshot_id": previous.id if previous else None,
                    "orphan_check_queued": queued,
                },
            )
        ],
    )
    events.extend(pointed.events)
    return CommandResult(
        stream_id=snapshot.id, key=snapshot.key, version=marked.new_version, events=events
    )
