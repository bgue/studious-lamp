"""The worker of the derivation queue: one runner over a ledger and a file service (ADR-0014).

``tl derive worker`` and the demo build their worker here, so the wiring (which job kinds, which
queue for which database, the extractors' limits) lives in one place. Extractor plugins run in a
child process; ``timeout_s`` and ``memory_limit_mb`` bound each one.
"""

from __future__ import annotations

from tl_adapters.db import DbTarget, make_uow_factory
from tl_adapters.queue import job_queue_for
from tl_core.derivation.isolated import DEFAULT_MEMORY_LIMIT_MB, DEFAULT_TIMEOUT_S
from tl_core.files.service import FileService
from tl_core.jobs import JobRunner
from tl_core.jobs.types import DEFAULT_LEASE_S, Clock, UowFactory
from tl_core.util import utcnow

from tl_mod_documents.derivation.jobs import make_kinds, reconcile_orphans


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
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
    lease_s: float = DEFAULT_LEASE_S,
    factory: str | None = None,
    clock: Clock = utcnow,
) -> Worker:
    """A worker that serves the ``extract`` and ``validate`` jobs of the ledger at ``target``.

    ``factory`` names the extractor factory the child process loads (default: the registry built
    from entry points). ``worker.runner`` has ``run_once``, ``run_until_idle`` and ``serve``.
    """
    open_uow = make_uow_factory(target)
    with open_uow() as uow:
        queue = job_queue_for(uow.conn())
    runner = JobRunner(
        open_uow,
        queue,
        make_kinds(files, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, factory=factory),
        worker_id=worker_id,
        lease_s=lease_s,
        clock=clock,
    )
    return Worker(runner, open_uow)


def requeue_orphans(target: DbTarget) -> int:
    """Queue again the jobs the ledger holds that the queue lost (after a restore); the count."""
    open_uow = make_uow_factory(target)
    try:
        with open_uow() as uow:
            return reconcile_orphans(uow.conn())
    finally:
        open_uow.dispose()
