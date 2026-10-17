"""The worker of the snapshot queue: one runner over a ledger and a file service (ADR-0014, 0015).

``tl xer worker`` and the demo build their worker here, so the wiring (which job kind, which queue
for which database, the envelope's limits) lives in one place.
"""

from __future__ import annotations

from tl_adapters.db import DbTarget, make_uow_factory
from tl_adapters.queue import job_queue_for
from tl_core.files.service import FileService
from tl_core.jobs import JobRunner
from tl_core.jobs.types import Clock, UowFactory
from tl_core.util import utcnow

from tl_mod_schedule.build import make_kinds
from tl_mod_schedule.limits import BUILD_LEASE_S


class Worker:
    """A job runner and the engine it owns. Use as a context manager or call :meth:`close`."""

    def __init__(self, runner: JobRunner, open_uow: UowFactory) -> None:
        self.runner = runner
        self._open_uow = open_uow

    def close(self) -> None:
        dispose = getattr(self._open_uow, "dispose", None)
        if callable(dispose):
            dispose()

    def __enter__(self) -> Worker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def build_worker(
    target: DbTarget,
    files: FileService,
    *,
    worker_id: str | None = None,
    timeout_s: float | None = None,
    memory_limit_mb: int | None = None,
    lease_s: float = BUILD_LEASE_S,
    clock: Clock = utcnow,
) -> Worker:
    """A worker that serves the ``schedule.build`` jobs of the ledger at ``target``."""
    open_uow = make_uow_factory(target)
    with open_uow() as uow:
        queue = job_queue_for(uow.conn())
    runner = JobRunner(
        open_uow,
        queue,
        make_kinds(files, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb),
        worker_id=worker_id,
        lease_s=lease_s,
        clock=clock,
    )
    return Worker(runner, open_uow)
