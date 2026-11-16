"""The lapse job: kind ``permits.lapse``, one run per project and minute.

Job id ``ptwlapse:<project>:<YYYY-MM-DDTHH:MM>`` (UTC; the minute of ``now``, a parameter of the
run, not the clock). ``prepare`` reads each Active permit of the project whose ``valid_until`` is
not after ``now`` (no end counts as lapsed, as ``rules.effective_state``) and that was not flagged
for that same ``valid_until``; ``settle`` appends one ``Permit.Lapsed`` for each (source
``job:permits.lapse``; the projector sets ``lapse_flagged_for``). At most ``LIMIT`` permits per
run: when more remain, ``settle`` queues the same run again (the queue row is already done in that
transaction), and the flagged ones no longer match. The job never changes a state, a
``valid_until`` or any other field, and puts no record text in an event. A job has no record, so
``started``, ``failed`` and ``expired`` write nothing; the queue row keeps the error code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import text
from tl_adapters.queue import job_queue_for
from tl_core.jobs import DEFAULT_MAX_ATTEMPTS, JobFailure, JobRunner, UowFactory, iso_z
from tl_core.jobs.types import DONE, QUEUED, Claim, Expired
from tl_core.ledger import NewEvent, iso_utc
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_permits.handlers.common import version_of
from tl_mod_permits.names import (
    ACTIVE,
    FEED_NONE,
    JOB_ACTOR,
    JOB_KIND,
    JOB_PREFIX,
    JOB_SOURCE,
    PERMIT,
    PERMIT_LAPSED,
    PERMIT_TABLE,
)

LIMIT: Final = 500
BAD_ID = "not a permit lapse job id"
_MINUTE = "%Y-%m-%dT%H:%M"
_ACTIVE_SQL = text(
    "SELECT p.id, p.valid_until, p.lapse_flagged_for "
    f"FROM {PERMIT_TABLE} p JOIN cur_core_record r ON r.id = p.id "
    "WHERE p.scope = :scope AND r.voided = :no AND r.status = :active ORDER BY p.id"
)
_REQUEUE_SQL = text(
    "UPDATE job_queue SET state = :queued, attempt = 0, run_after = :now, lease_owner = NULL, "
    "lease_until = NULL, started_at = NULL, finished_at = NULL, last_error = NULL, "
    "enqueued_at = :now WHERE job_id = :job_id AND state = :done"
)


def job_id(project: str, now: datetime) -> str:
    """``ptwlapse:<project>:<YYYY-MM-DDTHH:MM>``, the UTC minute of ``now`` (aware)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    return f"{JOB_PREFIX}{project}:{now.astimezone(UTC).strftime(_MINUTE)}"


def parse_job_id(value: str) -> tuple[str, datetime]:
    """``(project, minute)`` of a job id (aware UTC); ``ValueError`` for another shape."""
    if not value.startswith(JOB_PREFIX):
        raise ValueError(BAD_ID)
    project, sep, minute = value.removeprefix(JOB_PREFIX).partition(":")
    if not sep or not project:
        raise ValueError(BAD_ID)
    try:
        return project, datetime.strptime(minute, _MINUTE).replace(tzinfo=UTC)
    except ValueError:
        raise ValueError(BAD_ID) from None


def _instant(value: object) -> datetime | None:
    """A stored time (text or datetime) as an aware UTC instant; ``None`` stays ``None``."""
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def request(uow: UnitOfWork, project: str, now: datetime) -> bool:
    """Queue the run of ``project`` for the minute of ``now``; ``False`` when that run is already
    queued or done (one run per project and minute)."""
    conn = uow.conn()
    queue = job_queue_for(conn)
    made = job_id(project, now)
    if queue.get(conn, made) is not None:
        return False
    queue.enqueue(
        conn,
        job_id=made,
        kind=JOB_KIND,
        scope=f"project:{project}",
        now=utcnow(),
        max_attempts=DEFAULT_MAX_ATTEMPTS,
    )
    return True


@dataclass(frozen=True)
class Flag:
    permit_id: str
    valid_until: datetime | None


@dataclass(frozen=True)
class Outcome:
    scope: str
    now: datetime
    flags: list[Flag]
    remaining: int


class LapseKind:
    kind = JOB_KIND

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        return None

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Outcome:
        try:
            _, now = parse_job_id(claim.job_id)
        except ValueError:
            raise JobFailure("bad_job_id", BAD_ID, retryable=False) from None
        rows = (
            uow.conn()
            .execute(_ACTIVE_SQL, {"scope": claim.scope, "no": False, "active": ACTIVE})
            .all()
        )
        flags: list[Flag] = []
        for r in rows:
            until = _instant(r.valid_until)
            if until is not None and until > now:
                continue
            if until is not None and _instant(r.lapse_flagged_for) == until:
                continue
            flags.append(Flag(str(r.id), until))
        return Outcome(claim.scope, now, flags[:LIMIT], max(0, len(flags) - LIMIT))

    def run(self, work: Outcome) -> Outcome:
        return work

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Outcome) -> None:
        correlation = new_ulid()
        for flag in outcome.flags:
            payload: dict[str, object] = {
                "record_id": flag.permit_id,
                "valid_until": None if flag.valid_until is None else iso_utc(flag.valid_until),
                "at": iso_utc(outcome.now),
                "feed_policy": FEED_NONE,
            }
            uow.append(
                stream_id=flag.permit_id,
                stream_type=PERMIT,
                scope=outcome.scope,
                expected_version=version_of(uow, flag.permit_id),
                events=[NewEvent(event_type=PERMIT_LAPSED, payload=payload)],
                actor=JOB_ACTOR,
                source=JOB_SOURCE,
                correlation_id=correlation,
                causation_id=None,
            )
        if outcome.remaining > 0:
            # the queue row is done in this transaction: queue the same run once more
            uow.conn().execute(
                _REQUEUE_SQL,
                {
                    "queued": QUEUED,
                    "done": DONE,
                    "now": iso_z(utcnow()),
                    "job_id": claim.job_id,
                },
            )

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


def run_once(open_uow_factory: UowFactory, project: str, now: datetime) -> int:
    """Queue the run of ``project`` for ``now`` and run the runner until idle; the number of events
    appended (``0`` when the run was already done). The helper tests and demos call."""
    with open_uow_factory() as uow:
        before = _event_count(uow)
        request(uow, project, now)
    with open_uow_factory() as uow:
        queue = job_queue_for(uow.conn())
    JobRunner(open_uow_factory, queue, [LapseKind()], worker_id="permits.lapse").run_until_idle()
    with open_uow_factory() as uow:
        return _event_count(uow) - before


def _event_count(uow: UnitOfWork) -> int:
    return int(uow.conn().execute(text("SELECT count(*) FROM events")).scalar_one())


__all__ = ["LIMIT", "LapseKind", "job_id", "parse_job_id", "request", "run_once"]
