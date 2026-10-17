"""The worker loop: claim a job, run it outside any transaction, settle it (ADR-0014).

One pass of :meth:`JobRunner.run_once` is three short transactions around one long step that holds
none:

1. **Claim** (write): fail for good the jobs whose lease ran out with no attempt left, lease the
   next job, and let its kind append the "started" event. Commit.
2. **Run** (read, then nothing): the kind reads what it needs in a read-only unit of work
   (``prepare``), then ``run`` does the work with no transaction open. The work is a pure function
   of what ``prepare`` returned (an extractor reads bytes and returns a result), so a crash here
   loses nothing: the lease runs out and the job is claimed again.
3. **Settle** (write): compare-and-set the queue row on ``(job, attempt, owner)``. Only if the
   claim is still ours does the kind write its results and events. If the lease was taken over the
   late worker writes nothing, so a job completes at most once. A failure of the work or of the
   settlement is recorded in a fresh transaction: the job is queued again after a delay, or failed
   for good when no attempt is left or the failure is permanent.

A kind is any object with the methods of :class:`JobKind`. The kind owns the events (they belong to
its record type); this module owns the queue rules.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, Protocol

from tl_core.jobs.queue import JobQueue
from tl_core.jobs.types import (
    DEFAULT_LEASE_S,
    MAX_ERROR,
    RETRY_BASE_S,
    Claim,
    Clock,
    Expired,
    UowFactory,
    iso_z,
)
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

log = logging.getLogger(__name__)

Outcome = Literal["done", "already", "lost", "retry", "final"]


class JobFailure(Exception):
    """What a kind raises (or returns the news of) when an attempt cannot finish.

    ``code`` is short and fixed (``source_not_available``); ``message`` is words for a person,
    without paths or stack traces. A non-retryable failure fails the job for good at once.
    """

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class JobKind(Protocol):
    """A kind of job: the code that knows its record, its events and its work."""

    kind: str

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        """Append the "started" event of the attempt (same transaction as the claim)."""
        ...

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Any:
        """Read what the work needs, in a read-only unit of work. Raise ``JobFailure``."""
        ...

    def run(self, work: Any) -> Any:
        """Do the work with no transaction open. Pure: no ledger, no network. May raise."""
        ...

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Any) -> None:
        """Write the results and the "succeeded" event. Called only when the claim is still ours."""
        ...

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        """Append the "failed" event of the attempt."""
        ...

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        """Append the final "failed" event of a job whose lease ran out with no attempt left."""
        ...


@dataclass(frozen=True)
class RunResult:
    """What one pass did with one job."""

    job_id: str
    kind: str
    attempt: int
    outcome: Outcome


def failure_from(exc: BaseException) -> JobFailure:
    """A ``JobFailure`` for any exception, with text safe to store: no paths, no traces.

    A ``ServiceError`` has a fixed message that names the caller's values (that is its contract),
    so it is kept; anything else is reduced to its type name.
    """
    if isinstance(exc, JobFailure):
        return exc
    if isinstance(exc, ServiceError):
        return JobFailure("refused", str(exc)[:MAX_ERROR], retryable=False)
    return JobFailure("internal_error", f"unexpected {type(exc).__name__}", retryable=True)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{new_ulid()[-6:]}"


class JobRunner:
    def __init__(
        self,
        open_uow: UowFactory,
        queue: JobQueue,
        kinds: Sequence[JobKind],
        *,
        worker_id: str | None = None,
        lease_s: float = DEFAULT_LEASE_S,
        retry_base_s: float = RETRY_BASE_S,
        clock: Clock = utcnow,
    ) -> None:
        names = [k.kind for k in kinds]
        if len(set(names)) != len(names):
            raise ValueError("two job kinds share a name")
        self._open = open_uow
        self._queue = queue
        self._kinds: Mapping[str, JobKind] = {k.kind: k for k in kinds}
        self.worker_id = worker_id or default_worker_id()
        self._lease_s = lease_s
        self._retry_base_s = retry_base_s
        self._clock = clock

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(self._kinds)

    # --- one pass -------------------------------------------------------------------------

    def run_once(self, *, scope: str | None = None) -> RunResult | None:
        """Claim and run at most one job. ``None`` when there is nothing to do."""
        claim = self._claim(scope)
        if claim is None:
            return None
        kind = self._kinds[claim.kind]
        try:
            with self._open(readonly=True) as uow:
                work = kind.prepare(uow, claim)
            outcome = kind.run(work)
        except Exception as exc:  # noqa: BLE001 - any failure of the work is the job's failure
            return self._record_failure(kind, claim, failure_from(exc))
        try:
            with self._open() as uow:
                completion = self._queue.complete(uow.conn(), claim, now=self._clock())
                if completion == "done":
                    kind.settle(uow, claim, outcome)
        except Exception as exc:  # noqa: BLE001 - the transaction rolled back, queue row included
            return self._record_failure(kind, claim, failure_from(exc))
        return RunResult(claim.job_id, claim.kind, claim.attempt, completion)

    def run_until_idle(self, *, scope: str | None = None, limit: int = 10_000) -> list[RunResult]:
        """Run jobs until nothing is claimable (or ``limit`` jobs have run)."""
        results: list[RunResult] = []
        while len(results) < limit:
            result = self.run_once(scope=scope)
            if result is None:
                break
            results.append(result)
        return results

    def serve(
        self,
        stop: Callable[[], bool],
        *,
        idle_s: float = 2.0,
        scope: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> int:
        """Run jobs until ``stop()`` is true, sleeping ``idle_s`` when the queue is empty."""
        ran = 0
        while not stop():
            if self.run_once(scope=scope) is None:
                sleep(idle_s)
            else:
                ran += 1
        return ran

    # --- internals ------------------------------------------------------------------------

    def _claim(self, scope: str | None) -> Claim | None:
        with self._open() as uow:
            now = self._clock()
            for item in self._queue.reap_expired(uow.conn(), now=now):
                kind = self._kinds.get(item.kind)
                if kind is not None:
                    kind.expired(uow, item)
            claim = self._queue.claim(
                uow.conn(),
                owner=self.worker_id,
                now=now,
                lease_s=self._lease_s,
                kinds=self.kinds,
                scope=scope,
            )
            if claim is not None:
                self._kinds[claim.kind].started(uow, claim)
            return claim

    def _record_failure(self, kind: JobKind, claim: Claim, failure: JobFailure) -> RunResult:
        log.info("job %s attempt %d failed: %s", claim.job_id, claim.attempt, failure.code)
        now = self._clock()
        delay = self._retry_base_s * claim.attempt
        with self._open() as uow:
            outcome = self._queue.fail(
                uow.conn(),
                claim,
                now=now,
                error=f"{failure.code}: {failure.message}",
                retry_delay_s=delay,
                permanent=not failure.retryable,
            )
            if outcome == "retry" or outcome == "final":
                final = outcome == "final"
                retry_at = None if final else iso_z(now + timedelta(seconds=delay))
                kind.failed(uow, claim, failure, final=final, retry_at=retry_at)
        return RunResult(claim.job_id, claim.kind, claim.attempt, outcome)
