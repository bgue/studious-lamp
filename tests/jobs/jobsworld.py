"""Helpers for the job queue tests (the name is unique on purpose: L-P1-I0A-1).

``Clock`` is the real clock plus an offset, so it never falls behind what the database stamps.
``World`` owns a unit-of-work factory and the queue of the database under test. ``Kind`` is a job
kind that records what the runner asked of it and does a configurable piece of work.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tl_adapters.db import make_uow_factory
from tl_adapters.queue import job_queue_for
from tl_core.jobs import Claim, Expired, JobFailure, JobQueue, JobRunner, QueueRow
from tl_core.uow import UnitOfWork

SCOPE = "project:P123"


class Clock:
    def __init__(self) -> None:
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return datetime.now(UTC) + self.offset

    def advance(self, **kwargs: float) -> None:
        self.offset += timedelta(**kwargs)


@dataclass
class Kind:
    """A job kind that counts calls. ``work`` is what ``run`` does; it may raise."""

    kind: str = "fake"
    work: Callable[[Any], Any] | None = None
    prepare_error: JobFailure | None = None
    settle_error: Exception | None = None
    expired_error: Exception | None = None
    #: jobs whose record is gone: ``started`` refuses them, as the documents module does
    missing: set[str] = field(default_factory=set[str])
    calls: list[tuple[str, str, int]] = field(default_factory=list[tuple[str, str, int]])

    def started(self, uow: UnitOfWork, claim: Claim) -> None:
        self.calls.append(("started", claim.job_id, claim.attempt))
        if claim.job_id in self.missing:
            raise JobFailure("job_missing", "the job record does not exist", retryable=False)

    def prepare(self, uow: UnitOfWork, claim: Claim) -> Any:
        self.calls.append(("prepare", claim.job_id, claim.attempt))
        if self.prepare_error is not None:
            raise self.prepare_error
        return claim

    def run(self, work: Any) -> Any:
        self.calls.append(("run", work.job_id, work.attempt))
        return self.work(work) if self.work is not None else "result"

    def settle(self, uow: UnitOfWork, claim: Claim, outcome: Any) -> None:
        self.calls.append(("settle", claim.job_id, claim.attempt))
        if self.settle_error is not None:
            raise self.settle_error

    def failed(
        self,
        uow: UnitOfWork,
        claim: Claim,
        failure: JobFailure,
        *,
        final: bool,
        retry_at: str | None,
    ) -> None:
        self.calls.append(("final" if final else "retry", claim.job_id, claim.attempt))

    def expired(self, uow: UnitOfWork, item: Expired) -> None:
        self.calls.append(("expired", item.job_id, item.attempt))
        if self.expired_error is not None:
            raise self.expired_error

    def count(self, what: str, job_id: str | None = None) -> int:
        return sum(1 for c in self.calls if c[0] == what and job_id in (None, c[1]))


class World:
    def __init__(self, db: str | Path, clock: Clock) -> None:
        self.db = db
        self.clock = clock
        self.factory = make_uow_factory(db)
        with self.factory() as uow:
            self.queue: JobQueue = job_queue_for(uow.conn())

    def dispose(self) -> None:
        self.factory.dispose()

    def enqueue(self, job_id: str, *, kind: str = "fake", **kwargs: Any) -> None:
        with self.factory() as uow:
            self.queue.enqueue(
                uow.conn(),
                job_id=job_id,
                kind=kind,
                scope=kwargs.pop("scope", SCOPE),
                now=self.clock(),
                **kwargs,
            )

    def row(self, job_id: str) -> QueueRow:
        with self.factory(readonly=True) as uow:
            found = self.queue.get(uow.conn(), job_id)
        assert found is not None
        return found

    def claim(self, owner: str = "w1", lease_s: float = 60, **kwargs: Any) -> Claim | None:
        with self.factory() as uow:
            return self.queue.claim(
                uow.conn(), owner=owner, now=self.clock(), lease_s=lease_s, **kwargs
            )

    def runner(self, kind: Kind, worker: str = "w1", **kwargs: Any) -> JobRunner:
        return JobRunner(
            self.factory, self.queue, [kind], worker_id=worker, clock=self.clock, **kwargs
        )
