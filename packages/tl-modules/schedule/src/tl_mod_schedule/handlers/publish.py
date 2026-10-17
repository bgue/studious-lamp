"""``PublishScheduleSnapshot``: make a valid snapshot the schedule's current one (ADR-0015).

One unit of work: the previous current snapshot becomes Superseded, this one Published,
``ScheduleSnapshot.MadeCurrent`` and ``Schedule.SnapshotPublished`` are appended, and then every
activity reference of the schedule is checked against the new snapshot. A reference whose activity
is gone is marked absent and the active links to it are flagged stale (brief 7.3: an activity
missing from the latest XER snapshot is orphaned); a reference whose activity is back is marked
present and the links this module flagged are restored. Only the links the module itself flagged
(by their reason) are restored; a link a person flagged stays flagged.

Who may run it: the document controller or the admin (ADR-0015). An agent proposes it.
The data date must be later than the current snapshot's: the current snapshot is always the
latest data date published.
"""

from __future__ import annotations

from pydantic import ConfigDict
from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.links import FlagLink, RepinLink, handle_flag_link, handle_repin_link
from tl_core.uow import UnitOfWork

from tl_mod_schedule import registry
from tl_mod_schedule.common import append, correlated, transition
from tl_mod_schedule.errors import ScheduleNotFoundError, SnapshotStateError, StaleSnapshotError
from tl_mod_schedule.handlers.snapshots import load_snapshot
from tl_mod_schedule.names import (
    ORPHAN_REASON,
    REF_PRESENCE,
    SCHEDULE,
    SCHEDULE_SNAPSHOT,
    SCHEDULE_SNAPSHOT_PUBLISHED,
    SNAPSHOT_MADE_CURRENT,
    VALID,
)

ACTIVE_LINKS_SQL = text(
    "SELECT link_id FROM cur_links WHERE to_id = :ref AND status = 'active' "
    "ORDER BY created_at, link_id"
)
ORPHANED_LINKS_SQL = text(
    "SELECT link_id FROM cur_links WHERE to_id = :ref AND status = 'stale' "
    "AND reason LIKE :reason ORDER BY created_at, link_id"
)


class PublishScheduleSnapshot(Command):
    """Make a Valid snapshot the current snapshot of its schedule."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str


def handle_publish_schedule_snapshot(
    uow: UnitOfWork, cmd: PublishScheduleSnapshot
) -> CommandResult:
    """Publish. Raises ``SnapshotStateError`` (not Valid) and ``StaleSnapshotError``."""
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
    if previous is not None and previous.data_date is not None and data_date <= previous.data_date:
        raise StaleSnapshotError(
            f"snapshot {snapshot.key} has data date {data_date}, not later than the current "
            f"snapshot {previous.key} ({previous.data_date})"
        )
    events: list = []  # type: ignore[type-arg]
    if previous is not None:
        events.extend(transition(uow, cmd, previous.id, "supersede").events)
    events.extend(transition(uow, cmd, snapshot.id, "publish").events)

    refs = registry.refs_of(conn, schedule.id)
    present = registry.activity_ids_present(conn, snapshot.id, (r.activity_id for r in refs))
    orphaned = restored = 0
    for ref in refs:
        here = ref.activity_id in present
        if here == ref.present:
            continue
        seen_id, seen_number = (
            (snapshot.id, snapshot.number)
            if here
            else (
                previous.id if previous else ref.last_seen_snapshot_id or snapshot.id,
                previous.number if previous else ref.last_seen_number or snapshot.number,
            )
        )
        events.extend(
            append(
                uow,
                cmd,
                ref.id,
                "schedule.ActivityRef",
                [
                    NewEvent(
                        event_type=REF_PRESENCE,
                        payload={
                            "present": here,
                            "snapshot_id": snapshot.id,
                            "snapshot_number": snapshot.number,
                            "last_seen_snapshot_id": seen_id,
                            "last_seen_number": seen_number,
                        },
                    )
                ],
            ).events
        )
        if not here:
            orphaned += 1
            for row in conn.execute(ACTIVE_LINKS_SQL, {"ref": ref.id}).all():
                events.extend(
                    handle_flag_link(
                        uow,
                        FlagLink(
                            actor=cmd.actor,
                            source=cmd.source,
                            scope=cmd.scope,
                            correlation_id=cmd.correlation_id,
                            link_id=str(row.link_id),
                            status="stale",
                            reason=f"{ORPHAN_REASON} {snapshot.key}"[:500],
                        ),
                        by_module=True,
                    ).events
                )
        else:
            restored += 1
            for row in conn.execute(
                ORPHANED_LINKS_SQL,
                {"ref": ref.id, "reason": ORPHAN_REASON + "%"},
            ).all():
                events.extend(
                    handle_repin_link(
                        uow,
                        RepinLink(
                            actor=cmd.actor,
                            source=cmd.source,
                            scope=cmd.scope,
                            correlation_id=cmd.correlation_id,
                            link_id=str(row.link_id),
                        ),
                        by_module=True,
                    ).events
                )
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
                    "orphaned_count": orphaned,
                    "restored_count": restored,
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
                    "orphaned_count": orphaned,
                    "restored_count": restored,
                },
            )
        ],
    )
    events.extend(pointed.events)
    return CommandResult(
        stream_id=snapshot.id, key=snapshot.key, version=marked.new_version, events=events
    )
