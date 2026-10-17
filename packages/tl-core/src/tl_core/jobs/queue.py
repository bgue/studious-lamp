"""The claim queue over ``job_queue`` (ADR-0014): enqueue, claim with a lease, complete, fail.

Every method takes the connection of a unit of work and never commits, so a queue change and the
ledger events that describe it are one transaction. The SQL is portable except one clause: the
claim selects its candidate row with ``claim_lock`` appended, which a database adapter sets
(``FOR UPDATE SKIP LOCKED`` on Postgres, nothing on SQLite, whose write transaction already holds
the single writer lock). ``tl_adapters.queue`` has the two subclasses; this class alone is a
correct queue on any database that serialises writers.

Rules:

* A row is claimable when it is ``queued`` and ``run_after`` has come, or ``running`` and its lease
  ran out, and ``attempt < max_attempts`` for the second case.
* A claim is a compare-and-set on the state it read, so two claimers never get the same attempt.
* ``complete`` and ``fail`` are compare-and-sets on ``(job_id, attempt, lease_owner, running)``. A
  late worker whose lease was taken over gets ``lost`` and writes nothing. Repeating a completion
  of the same attempt is ``already``, not an error: completion is idempotent on (job id, attempt).
* A running row whose lease ran out with no attempt left is failed for good by ``reap_expired``,
  which returns what it failed so the caller can append the matching events.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text

from tl_core.jobs.types import (
    CANCELLED,
    DEFAULT_MAX_ATTEMPTS,
    DONE,
    FAILED,
    MAX_ERROR,
    QUEUED,
    RUNNING,
    Claim,
    Completion,
    Expired,
    FailOutcome,
    QueueRow,
    iso_z,
)

_COLUMNS = (
    "job_id, kind, scope, state, priority, attempt, max_attempts, run_after, lease_owner, "
    "lease_until, enqueued_at, started_at, finished_at, last_error"
)
_INSERT_SQL = text(
    "INSERT INTO job_queue (job_id, kind, scope, state, priority, attempt, max_attempts, "
    "run_after, enqueued_at) VALUES (:job_id, :kind, :scope, 'queued', :priority, :attempt, "
    ":max_attempts, :run_after, :now)"
)
_GET_SQL = text(f"SELECT {_COLUMNS} FROM job_queue WHERE job_id = :job_id")
_LEASE_CLAIM_SQL = text(
    "UPDATE job_queue SET state = 'running', attempt = attempt + 1, lease_owner = :owner, "
    "lease_until = :until, started_at = :now, last_error = NULL "
    "WHERE job_id = :job_id AND attempt = :attempt AND "
    "((state = 'queued' AND run_after <= :now) OR "
    "(state = 'running' AND lease_until <= :now AND attempt < max_attempts))"
)
_EXTEND_SQL = text(
    "UPDATE job_queue SET lease_until = :until WHERE job_id = :job_id AND attempt = :attempt "
    "AND lease_owner = :owner AND state = 'running'"
)
_COMPLETE_SQL = text(
    "UPDATE job_queue SET state = 'done', finished_at = :now, lease_until = NULL "
    "WHERE job_id = :job_id AND attempt = :attempt AND lease_owner = :owner AND state = 'running'"
)
_RETRY_SQL = text(
    "UPDATE job_queue SET state = 'queued', run_after = :run_after, lease_owner = NULL, "
    "lease_until = NULL, last_error = :error WHERE job_id = :job_id AND attempt = :attempt "
    "AND lease_owner = :owner AND state = 'running'"
)
_FINAL_SQL = text(
    "UPDATE job_queue SET state = 'failed', finished_at = :now, lease_until = NULL, "
    "last_error = :error WHERE job_id = :job_id AND attempt = :attempt "
    "AND lease_owner = :owner AND state = 'running'"
)
_CANCEL_SQL = text(
    "UPDATE job_queue SET state = 'cancelled', finished_at = :now "
    "WHERE job_id = :job_id AND state = 'queued'"
)
_REAP_SELECT = (
    "SELECT job_id, kind, scope, attempt, max_attempts FROM job_queue "
    "WHERE state = 'running' AND lease_until <= :now AND attempt >= max_attempts"
)
_REAP_SQL = text(
    "UPDATE job_queue SET state = 'failed', finished_at = :now, lease_until = NULL, "
    "last_error = 'the lease ran out and no attempt is left' "
    "WHERE job_id = :job_id AND state = 'running' AND attempt = :attempt"
)


def _row(found: Any) -> QueueRow:
    return QueueRow(
        job_id=found.job_id,
        kind=found.kind,
        scope=found.scope,
        state=found.state,
        priority=int(found.priority),
        attempt=int(found.attempt),
        max_attempts=int(found.max_attempts),
        run_after=found.run_after,
        lease_owner=found.lease_owner,
        lease_until=found.lease_until,
        enqueued_at=found.enqueued_at,
        started_at=found.started_at,
        finished_at=found.finished_at,
        last_error=found.last_error,
    )


def _kind_filter(kinds: Sequence[str] | None, scope: str | None) -> tuple[str, dict[str, Any]]:
    clause = ""
    params: dict[str, Any] = {}
    if kinds:
        names: list[str] = []
        for index, kind in enumerate(kinds):
            params[f"k{index}"] = kind
            names.append(f":k{index}")
        clause += f" AND kind IN ({', '.join(names)})"
    if scope is not None:
        clause += " AND scope = :scope"
        params["scope"] = scope
    return clause, params


class JobQueue:
    """The queue. Subclass it and set ``claim_lock`` for a database that needs a row lock."""

    #: Appended to the claim's candidate select (``" FOR UPDATE SKIP LOCKED"``).
    claim_lock: str = ""

    def enqueue(
        self,
        conn: Connection,
        *,
        job_id: str,
        kind: str,
        scope: str,
        now: datetime,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        priority: int = 0,
        run_after: datetime | None = None,
        attempt: int = 0,
    ) -> None:
        """Queue a job. ``attempt`` is for ``reconcile``: the claims it already used."""
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        conn.execute(
            _INSERT_SQL,
            {
                "job_id": job_id,
                "kind": kind,
                "scope": scope,
                "priority": priority,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "run_after": iso_z(run_after or now),
                "now": iso_z(now),
            },
        )

    def get(self, conn: Connection, job_id: str) -> QueueRow | None:
        found = conn.execute(_GET_SQL, {"job_id": job_id}).first()
        return None if found is None else _row(found)

    def claim(
        self,
        conn: Connection,
        *,
        owner: str,
        now: datetime,
        lease_s: float,
        kinds: Sequence[str] | None = None,
        scope: str | None = None,
    ) -> Claim | None:
        """Lease the best claimable job to ``owner``; ``None`` when nothing is claimable.

        Call ``reap_expired`` first in the same transaction, so a job with no attempt left is
        failed for good instead of being skipped for ever.
        """
        stamp = iso_z(now)
        extra, params = _kind_filter(kinds, scope)
        candidate = text(
            f"SELECT {_COLUMNS} FROM job_queue WHERE "
            "((state = 'queued' AND run_after <= :now) OR "
            "(state = 'running' AND lease_until <= :now AND attempt < max_attempts))"
            f"{extra} ORDER BY priority DESC, run_after, job_id LIMIT 1{self.claim_lock}"
        )
        found = conn.execute(candidate, {"now": stamp, **params}).first()
        if found is None:
            return None
        until = iso_z(now + timedelta(seconds=lease_s))
        taken = conn.execute(
            _LEASE_CLAIM_SQL,
            {
                "job_id": found.job_id,
                "attempt": found.attempt,
                "owner": owner,
                "until": until,
                "now": stamp,
            },
        ).rowcount
        if taken != 1:
            return None  # another claimer got it between the select and the update
        return Claim(
            job_id=found.job_id,
            kind=found.kind,
            scope=found.scope,
            attempt=int(found.attempt) + 1,
            max_attempts=int(found.max_attempts),
            owner=owner,
            lease_until=until,
        )

    def extend(self, conn: Connection, claim: Claim, *, now: datetime, lease_s: float) -> bool:
        """Push the lease of a claim out; ``False`` when the claim is no longer this caller's."""
        until = iso_z(now + timedelta(seconds=lease_s))
        return (
            conn.execute(
                _EXTEND_SQL,
                {
                    "job_id": claim.job_id,
                    "attempt": claim.attempt,
                    "owner": claim.owner,
                    "until": until,
                },
            ).rowcount
            == 1
        )

    def complete(self, conn: Connection, claim: Claim, *, now: datetime) -> Completion:
        """Mark the claimed attempt done. Idempotent on (job id, attempt)."""
        params = {
            "job_id": claim.job_id,
            "attempt": claim.attempt,
            "owner": claim.owner,
            "now": iso_z(now),
        }
        if conn.execute(_COMPLETE_SQL, params).rowcount == 1:
            return "done"
        found = self.get(conn, claim.job_id)
        if (
            found is not None
            and found.state == DONE
            and found.attempt == claim.attempt
            and found.lease_owner == claim.owner
        ):
            return "already"
        return "lost"

    def fail(
        self,
        conn: Connection,
        claim: Claim,
        *,
        now: datetime,
        error: str,
        retry_delay_s: float,
        permanent: bool = False,
    ) -> FailOutcome:
        """Record a failed attempt: queue it again after ``retry_delay_s``, or fail it for good.

        It fails for good when this was the last attempt or ``permanent`` is set.
        """
        params: dict[str, Any] = {
            "job_id": claim.job_id,
            "attempt": claim.attempt,
            "owner": claim.owner,
            "now": iso_z(now),
            "error": error[:MAX_ERROR],
        }
        if permanent or claim.attempt >= claim.max_attempts:
            if conn.execute(_FINAL_SQL, params).rowcount == 1:
                return "final"
        else:
            params["run_after"] = iso_z(now + timedelta(seconds=retry_delay_s))
            if conn.execute(_RETRY_SQL, params).rowcount == 1:
                return "retry"
        found = self.get(conn, claim.job_id)
        if (
            found is not None
            and found.attempt == claim.attempt
            and found.lease_owner in (None, claim.owner)
            and found.state in (QUEUED, FAILED)
            and found.last_error == error[:MAX_ERROR]
        ):
            return "already"
        return "lost"

    def cancel(self, conn: Connection, job_id: str, *, now: datetime) -> bool:
        """Cancel a queued job. A running job cannot be cancelled: ``False``."""
        return conn.execute(_CANCEL_SQL, {"job_id": job_id, "now": iso_z(now)}).rowcount == 1

    def reap_expired(self, conn: Connection, *, now: datetime, limit: int = 20) -> list[Expired]:
        """Fail for good the running jobs whose lease ran out with no attempt left."""
        stamp = iso_z(now)
        found = conn.execute(
            text(f"{_REAP_SELECT} ORDER BY job_id LIMIT {int(limit)}{self.claim_lock}"),
            {"now": stamp},
        ).all()
        reaped: list[Expired] = []
        for row in found:
            if (
                conn.execute(
                    _REAP_SQL, {"job_id": row.job_id, "attempt": row.attempt, "now": stamp}
                ).rowcount
                == 1
            ):
                reaped.append(
                    Expired(
                        job_id=row.job_id,
                        kind=row.kind,
                        scope=row.scope,
                        attempt=int(row.attempt),
                        max_attempts=int(row.max_attempts),
                    )
                )
        return reaped

    def counts(self, conn: Connection, *, scope: str | None = None) -> dict[str, int]:
        """Rows per state (every state is present, 0 when empty)."""
        sql = "SELECT state, COUNT(*) AS n FROM job_queue"
        params: dict[str, Any] = {}
        if scope is not None:
            sql += " WHERE scope = :scope"
            params["scope"] = scope
        sql += " GROUP BY state"
        found = {r.state: int(r.n) for r in conn.execute(text(sql), params).all()}
        return {state: found.get(state, 0) for state in (QUEUED, RUNNING, DONE, FAILED, CANCELLED)}
