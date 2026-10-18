"""The job that makes the links to a schedule's activities agree with its current snapshot.

Publishing a snapshot used to walk every activity reference and every link of the schedule in the
publisher's transaction. Anyone signed in can link, so that was work an unprivileged person chose.
Now publication only queues this job (``Schedule.SnapshotPublished`` says so), and the worker does
the walk in runs of at most ``FLAG_BATCH`` operations:

1. **presence**: a reference whose activity is not in the current snapshot becomes absent, and one
   whose activity is there becomes present (``ActivityRef.PresenceChanged``);
2. **flag**: the active links to an absent reference become stale (``Link.Flagged``, reason
   ``ORPHAN_REASON``);
3. **restore**: the stale links to a present reference that *this module* flagged become active
   (``Link.Repinned``). The module recognises its own flag by the **source** of the latest
   ``Link.Flagged`` event of the link and its actor (both ``svc:schedule``; the API refuses a client
   source that starts with ``svc:``), never by the words of the reason: a person's flag, with the
   same words or others, stays flagged.

Each run is a function of the database, not of the last run: it takes the next outstanding
operations, so a run that is repeated, interrupted or overlapped by another does no harm, and a
publication that arrives while the job is running is caught by the next run (the job always works
against the schedule's *current* snapshot). A run that used its whole budget queues the next one.
Every run appends ``Schedule.OrphansChecked`` with its totals. While runs are outstanding the links
of the last publication may still show the old state: the module page says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, text
from tl_adapters.queue import job_queue_for
from tl_core.jobs import Claim, Expired, JobFailure
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command
from tl_core.services.links import FlagLink, RepinLink, handle_flag_link, handle_repin_link
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_schedule import limits, registry
from tl_mod_schedule.common import append
from tl_mod_schedule.errors import TypedRowsMissingError
from tl_mod_schedule.names import (
    ACTIVITY_REF,
    ACTIVITY_REF_TABLE,
    ACTIVITY_TABLE,
    FLAG_JOB_PREFIX,
    JOB_KIND_FLAG,
    ORPHAN_REASON,
    ORPHANS_CHECKED,
    REF_PRESENCE,
    SCHEDULE,
    SERVICE,
)

#: A stale link is the module's when the latest ``Link.Flagged`` event of its stream has this
#: source and this actor (``:service`` for both). The API refuses a client source that starts with
#: ``svc:``, and the actor is the second witness: a flag only the module's worker could write.
MODULE_FLAG_SQL = (
    "EXISTS (SELECT 1 FROM events e WHERE e.stream_id = l.link_id "
    "AND e.event_type = 'Link.Flagged' AND e.source = :service AND e.actor = :service "
    "AND e.seq = (SELECT MAX(f.seq) FROM events f WHERE f.stream_id = l.link_id "
    "AND f.event_type = 'Link.Flagged'))"
)
_CHANGES_SQL = text(
    "SELECT a.id, a.present, a.last_seen_snapshot_id, a.last_seen_number "
    f"FROM {ACTIVITY_REF_TABLE} a "
    f"LEFT JOIN {ACTIVITY_TABLE} s ON s.snapshot_id = :snapshot AND s.activity_id = a.activity_id "
    "WHERE a.schedule_id = :schedule AND ((a.present = :yes AND s.activity_id IS NULL) "
    "OR (a.present = :no AND s.activity_id IS NOT NULL)) ORDER BY a.id LIMIT :n"
)
_TO_FLAG_SQL = text(
    f"SELECT l.link_id FROM cur_links l JOIN {ACTIVITY_REF_TABLE} a ON a.id = l.to_id "
    "WHERE a.schedule_id = :schedule AND a.present = :no AND l.status = 'active' "
    "ORDER BY l.link_id LIMIT :n"
)
_TO_RESTORE_SQL = text(
    f"SELECT l.link_id FROM cur_links l JOIN {ACTIVITY_REF_TABLE} a ON a.id = l.to_id "
    "WHERE a.schedule_id = :schedule AND a.present = :yes AND l.status = 'stale' "
    f"AND {MODULE_FLAG_SQL} "
    "ORDER BY l.link_id LIMIT :n"
)


@dataclass(frozen=True)
class Run:
    refs_changed: int
    links_flagged: int
    links_restored: int
    complete: bool


def job_id(schedule_id: str) -> str:
    return f"{FLAG_JOB_PREFIX}{schedule_id}:{new_ulid()}"


def schedule_of(job: str) -> str:
    """The schedule a job id names; ``ValueError`` for an id that is not a flagging job's."""
    if not job.startswith(FLAG_JOB_PREFIX):
        raise ValueError("not a flagging job")
    return job[len(FLAG_JOB_PREFIX) :].split(":", 1)[0]


def queue_check(conn: Connection, schedule_id: str, scope: str) -> str:
    """Queue a run for a schedule; the job id."""
    made = job_id(schedule_id)
    job_queue_for(conn).enqueue(
        conn, job_id=made, kind=JOB_KIND_FLAG, scope=scope, now=utcnow(), max_attempts=3
    )
    return made


def has_refs(conn: Connection, schedule_id: str) -> bool:
    return (
        conn.execute(
            text(f"SELECT 1 FROM {ACTIVITY_REF_TABLE} WHERE schedule_id = :s LIMIT 1"),
            {"s": schedule_id},
        ).first()
        is not None
    )


_COUNT_SQL = text(f"SELECT COUNT(*) FROM {ACTIVITY_TABLE} WHERE snapshot_id = :snapshot")


def rows_present(conn: Connection, snapshot: registry.SnapshotRow) -> bool:
    """Whether the snapshot's activities are all in the database, as many as ``Built`` recorded.

    After a restore they are not until ``tl xer reconcile`` has written them; judging the links
    against none would call every activity gone.
    """
    found = conn.execute(_COUNT_SQL, {"snapshot": snapshot.id}).scalar_one()
    return int(found) == (snapshot.activity_count or 0)


def require_rows(conn: Connection, snapshot: registry.SnapshotRow) -> None:
    """``TypedRowsMissingError`` unless the snapshot's activities are all in the database."""
    if not rows_present(conn, snapshot):
        raise TypedRowsMissingError(
            f"the activities of {snapshot.key} are not in the database (after a restore?): "
            "an admin runs `tl xer reconcile`"
        )


def outstanding(conn: Connection, schedule_id: str) -> bool:
    """Whether the current snapshot of the schedule and its links disagree anywhere.

    ``False`` while the current snapshot's rows are missing (nothing can be judged).
    """
    schedule = registry.get_schedule(conn, schedule_id)
    if schedule is None or schedule.current_snapshot_id is None:
        return False
    current = registry.get_snapshot(conn, schedule.current_snapshot_id)
    if current is None or not rows_present(conn, current):
        return False
    base = {"schedule": schedule_id, "yes": True, "no": False, "n": 1}
    if conn.execute(_CHANGES_SQL, {**base, "snapshot": schedule.current_snapshot_id}).first():
        return True
    if conn.execute(_TO_FLAG_SQL, base).first():
        return True
    return conn.execute(_TO_RESTORE_SQL, {**base, "service": SERVICE}).first() is not None


def run_once(uow: UnitOfWork, schedule_id: str, *, budget: int | None = None) -> Run | None:
    """Do the next outstanding operations (at most ``budget``, default ``limits.FLAG_BATCH``).

    ``None``: no such schedule.
    """
    conn = uow.conn()
    schedule = registry.get_schedule(conn, schedule_id)
    if schedule is None:
        return None
    if schedule.current_snapshot_id is None:
        return Run(0, 0, 0, True)
    current = registry.get_snapshot(conn, schedule.current_snapshot_id)
    assert current is not None
    if not rows_present(conn, current):
        raise TypedRowsMissingError(
            f"the activities of {current.key} are not in the database; run `tl xer reconcile`"
        )
    command = Command(
        actor=SERVICE, source=SERVICE, scope=schedule.scope, correlation_id=new_ulid()
    )
    history = registry.history(conn, schedule_id)
    before = next((s for s in reversed(history) if s.id != current.id), None)
    left = limits.FLAG_BATCH if budget is None else budget
    changed = flagged = restored = 0
    params = {"schedule": schedule_id, "yes": True, "no": False}

    for row in conn.execute(_CHANGES_SQL, {**params, "snapshot": current.id, "n": left}).all():
        here = not bool(row.present)  # the row is wrong either way: flip it
        seen_id, seen_number = (
            (current.id, current.number)
            if here
            else (
                (before.id, before.number)
                if before is not None
                else (
                    str(row.last_seen_snapshot_id or current.id),
                    int(row.last_seen_number or current.number),
                )
            )
        )
        append(
            uow,
            command,
            str(row.id),
            ACTIVITY_REF,
            [
                NewEvent(
                    event_type=REF_PRESENCE,
                    payload={
                        "present": here,
                        "snapshot_id": current.id,
                        "snapshot_number": current.number,
                        "last_seen_snapshot_id": seen_id,
                        "last_seen_number": seen_number,
                    },
                )
            ],
        )
        changed += 1
        left -= 1
    if left > 0:
        for row in conn.execute(_TO_FLAG_SQL, {**params, "n": left}).all():
            handle_flag_link(
                uow,
                FlagLink(
                    actor=SERVICE,
                    source=SERVICE,
                    scope=schedule.scope,
                    correlation_id=command.correlation_id,
                    link_id=str(row.link_id),
                    status="stale",
                    reason=f"{ORPHAN_REASON} {current.key}"[:500],
                ),
                by_module=True,
            )
            flagged += 1
            left -= 1
    if left > 0:
        for row in conn.execute(_TO_RESTORE_SQL, {**params, "service": SERVICE, "n": left}).all():
            handle_repin_link(
                uow,
                RepinLink(
                    actor=SERVICE,
                    source=SERVICE,
                    scope=schedule.scope,
                    correlation_id=command.correlation_id,
                    link_id=str(row.link_id),
                ),
                by_module=True,
            )
            restored += 1
            left -= 1
    complete = left > 0  # every query came back short of its limit: nothing is left
    append(
        uow,
        command,
        schedule.id,
        SCHEDULE,
        [
            NewEvent(
                event_type=ORPHANS_CHECKED,
                payload={
                    "snapshot_id": current.id,
                    "snapshot_number": current.number,
                    "refs_changed": changed,
                    "links_flagged": flagged,
                    "links_restored": restored,
                    "complete": complete,
                },
            )
        ],
    )
    return Run(changed, flagged, restored, complete)


class FlagOrphansKind:
    """The job kind of :func:`run_once`.

    It appends no event of its own for starting or failing: the queue row holds the attempts and
    the last error, and a run that completes says what it did (``Schedule.OrphansChecked``).
    """

    kind = JOB_KIND_FLAG

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        return None

    def prepare(self, uow: UnitOfWork, claim: Claim) -> str:
        try:
            schedule_id = schedule_of(claim.job_id)
        except ValueError:
            raise JobFailure("bad_job", "not a flagging job", retryable=False) from None
        if registry.get_schedule(uow.conn(), schedule_id) is None:
            raise JobFailure("schedule_missing", "the schedule does not exist", retryable=False)
        return schedule_id

    def run(self, work: str) -> str:
        return work

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: str) -> None:
        result = run_once(uow, outcome)
        if result is not None and not result.complete:
            queue_check(uow.conn(), outcome, claim.scope)

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        return None

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        return None


__all__ = [
    "FlagOrphansKind",
    "Run",
    "has_refs",
    "job_id",
    "outstanding",
    "queue_check",
    "run_once",
    "schedule_of",
]
