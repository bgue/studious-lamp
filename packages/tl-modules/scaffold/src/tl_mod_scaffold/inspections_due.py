"""The inspections-due job: kind ``scaffold.inspections_due``, one run per project and day.

Job id ``inspdue:<project>:<YYYY-MM-DD>`` (the date is ``today``, a parameter of the run, not the
clock). ``prepare`` reads each standing scaffold of the project and the interval setting, and picks
those that ``rules.due_state`` calls ``due`` or ``overdue`` and that were not flagged for the same
``next_due_on``; ``settle`` appends one ``Scaffold.InspectionDue`` for each (source
``job:scaffold.inspections_due``, the projector sets ``flagged_due_on``). A run the same day finds
nothing left to flag and writes nothing. The job never changes a tag or a state. A job has no
record, so ``started``, ``failed`` and ``expired`` write nothing; the queue row keeps the error
code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from tl_adapters.queue import job_queue_for
from tl_core.jobs import DEFAULT_MAX_ATTEMPTS, JobFailure
from tl_core.jobs.types import Claim, Expired
from tl_core.ledger import NewEvent
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_scaffold import rules
from tl_mod_scaffold.handlers.common import version_of
from tl_mod_scaffold.names import (
    FEED_NONE,
    INSPECTION_DUE,
    INTERVAL_SETTING,
    JOB_ACTOR,
    JOB_KIND,
    JOB_PREFIX,
    JOB_SOURCE,
    REQUESTED,
    SCAFFOLD,
    SCAFFOLD_TABLE,
)

BAD_ID = "not an inspections-due job id"
_STANDING_SQL = text(
    "SELECT s.id, COALESCE(r.status, :initial) AS state, s.last_inspected_on, s.next_due_on, "
    f"s.flagged_due_on FROM {SCAFFOLD_TABLE} s JOIN cur_core_record r ON r.id = s.id "
    "WHERE s.scope = :scope AND r.voided = :no ORDER BY s.id"
)


def job_id(project: str, today: date) -> str:
    """``inspdue:<project>:<YYYY-MM-DD>``."""
    return f"{JOB_PREFIX}{project}:{today.isoformat()}"


def parse_job_id(value: str) -> tuple[str, date]:
    """``(project, today)`` of a job id; ``ValueError`` for another shape."""
    if not value.startswith(JOB_PREFIX):
        raise ValueError(BAD_ID)
    project, _, day = value.removeprefix(JOB_PREFIX).rpartition(":")
    if not project:
        raise ValueError(BAD_ID)
    return project, date.fromisoformat(day)


def request(uow: UnitOfWork, project: str, today: date) -> bool:
    """Queue the run of ``project`` for ``today``; ``False`` when that run is already queued or done
    (one run per project and day)."""
    conn = uow.conn()
    queue = job_queue_for(conn)
    made = job_id(project, today)
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
    scaffold_id: str
    due_on: str
    state: str


@dataclass(frozen=True)
class Outcome:
    scope: str
    flags: list[Flag]


class InspectionsDueKind:
    kind = JOB_KIND

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        return None

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Outcome:
        try:
            _, today = parse_job_id(claim.job_id)
        except ValueError:
            raise JobFailure("bad_job_id", BAD_ID, retryable=False) from None
        conn = uow.conn()
        interval = int(value_of(conn, INTERVAL_SETTING, project=project_of_scope(claim.scope)))
        rows = conn.execute(
            _STANDING_SQL, {"initial": REQUESTED, "scope": claim.scope, "no": False}
        ).all()
        flags: list[Flag] = []
        for r in rows:
            last = None if r.last_inspected_on is None else date.fromisoformat(r.last_inspected_on)
            if rules.due_state(str(r.state), last, today, interval) not in ("due", "overdue"):
                continue
            if r.next_due_on is None or r.flagged_due_on == r.next_due_on:
                continue
            flags.append(Flag(str(r.id), str(r.next_due_on), str(r.state)))
        return Outcome(claim.scope, flags)

    def run(self, work: Outcome) -> Outcome:
        return work

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Outcome) -> None:
        correlation = new_ulid()
        for flag in outcome.flags:
            uow.append(
                stream_id=flag.scaffold_id,
                stream_type=SCAFFOLD,
                scope=outcome.scope,
                expected_version=version_of(uow, flag.scaffold_id),
                events=[
                    NewEvent(
                        event_type=INSPECTION_DUE,
                        payload={
                            "record_id": flag.scaffold_id,
                            "due_on": flag.due_on,
                            "state": flag.state,
                            "feed_policy": FEED_NONE,
                        },
                    )
                ],
                actor=JOB_ACTOR,
                source=JOB_SOURCE,
                correlation_id=correlation,
                causation_id=None,
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


__all__ = ["InspectionsDueKind", "job_id", "parse_job_id", "request"]
