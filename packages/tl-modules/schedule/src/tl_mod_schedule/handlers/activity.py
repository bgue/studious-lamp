"""``LinkActivity``: link a record to a P6 activity by its stable activity id (brief 7.2, M11).

A link never points at a snapshot row. It points at the activity's *reference*
(``schedule.ActivityRef``), made the first time anything links to that activity id of the schedule.
The reference resolves to the activity of whatever snapshot is current (``resolver.resolve``), and
a link that pins a snapshot number resolves to that snapshot's activity instead. The link is made
with the core ``AddLink``, so the allow-list of the record it starts at applies as for any link.
Open to any signed-in person.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import text
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import create_module_record
from tl_core.text import clean_optional_text
from tl_core.uow import UnitOfWork

from tl_mod_schedule import limits, registry
from tl_mod_schedule.common import correlated, require_project
from tl_mod_schedule.errors import (
    ActivityNotFoundError,
    NoCurrentSnapshotError,
    ScheduleNotFoundError,
    SnapshotNotFoundError,
    TooManyLinksError,
    TooManyReferencesError,
)
from tl_mod_schedule.limits import MAX_ACTIVITY_ID
from tl_mod_schedule.names import (
    ACTIVITY_REF,
    ACTIVITY_REF_TABLE,
    ACTIVITY_RELATION,
    PUBLISHED,
    REF_DEFINED,
    SUPERSEDED,
)

_LIVE_LINKS_SQL = text(
    "SELECT COUNT(*) FROM cur_links WHERE to_id = :ref "
    "AND status IN ('active', 'stale', 'suggested')"
)
_REFS_SQL = text(f"SELECT COUNT(*) FROM {ACTIVITY_REF_TABLE} WHERE schedule_id = :schedule")


class LinkActivity(Command):
    """Link ``from_id`` to activity ``activity_id`` of a schedule."""

    model_config = ConfigDict(extra="forbid")

    from_id: str
    schedule_id: str
    activity_id: str = Field(min_length=1, max_length=MAX_ACTIVITY_ID)
    #: A snapshot number to pin the link to; null floats to the current snapshot.
    pin: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("activity_id", "note")
    @classmethod
    def _plain(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def handle_link_activity(uow: UnitOfWork, cmd: LinkActivity) -> CommandResult:
    """Make the reference if it is new, then the link (``ActivityRef.Defined``, ``Link.Added``).

    Raises ``ScheduleNotFoundError``, ``NoCurrentSnapshotError``, ``SnapshotNotFoundError`` (a pin
    that names no published snapshot) and ``ActivityNotFoundError``.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    schedule = registry.get_schedule(conn, cmd.schedule_id)
    if schedule is None or schedule.scope != cmd.scope:
        raise ScheduleNotFoundError(f"no schedule {cmd.schedule_id!r} in scope {cmd.scope!r}")
    if schedule.current_snapshot_id is None:
        raise NoCurrentSnapshotError(f"schedule {schedule.code} has no published snapshot yet")
    checked_id = schedule.current_snapshot_id
    if cmd.pin is not None:
        pinned = registry.find_snapshot(conn, schedule.id, cmd.pin)
        if pinned is None or pinned.state not in (PUBLISHED, SUPERSEDED):
            raise SnapshotNotFoundError(
                f"schedule {schedule.code} has no published snapshot number {cmd.pin}"
            )
        checked_id = pinned.id
    activity = registry.get_activity(conn, checked_id, cmd.activity_id)
    if activity is None:
        raise ActivityNotFoundError(
            f"no activity {cmd.activity_id!r} in the snapshot the link would resolve to"
        )
    events = []
    ref = registry.find_ref(conn, schedule.id, cmd.activity_id)
    if ref is not None:
        held = conn.execute(_LIVE_LINKS_SQL, {"ref": ref.id}).scalar_one()
        if int(held) >= limits.MAX_LINKS_PER_ACTIVITY:
            raise TooManyLinksError(
                f"activity {cmd.activity_id!r} already has {limits.MAX_LINKS_PER_ACTIVITY} links; "
                "retract one before adding another"
            )
        ref_id = ref.id
    else:
        known = conn.execute(_REFS_SQL, {"schedule": schedule.id}).scalar_one()
        if int(known) >= limits.MAX_REFS_PER_SCHEDULE:
            raise TooManyReferencesError(
                f"schedule {schedule.code} already has {limits.MAX_REFS_PER_SCHEDULE} "
                "linked activities"
            )
        current = registry.get_snapshot(conn, schedule.current_snapshot_id)
        assert current is not None
        made = create_module_record(
            uow,
            cmd,
            record_type=ACTIVITY_REF,
            title=f"{cmd.activity_id} {activity.name}"[:200],
            key=f"{schedule.code}/{cmd.activity_id}",
            composed_key=True,
            extra_events=[
                NewEvent(
                    event_type=REF_DEFINED,
                    payload={
                        "schedule_id": schedule.id,
                        "schedule_code": schedule.code,
                        "activity_id": cmd.activity_id,
                        "first_snapshot_id": current.id,
                        "first_snapshot_number": current.number,
                    },
                )
            ],
        )
        ref_id = made.stream_id
        events.extend(made.events)
    linked = handle_add_link(
        uow,
        AddLink(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            from_id=cmd.from_id,
            to_id=ref_id,
            relation=ACTIVITY_RELATION,
            pin=None if cmd.pin is None else str(cmd.pin),
            note=cmd.note,
        ),
    )
    events.extend(linked.events)
    return CommandResult(
        stream_id=linked.stream_id, key=linked.key, version=linked.version, events=events
    )
