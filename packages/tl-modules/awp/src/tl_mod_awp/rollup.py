"""Request the budget rollup of a project (spec m3-wbs-cwp section 4; contracts section 7).

``request`` only queues: job id ``rollup:<scope>``, kind ``awp.rollup``. The run (read the ledger,
compute, append ``WBSNode.BudgetRolledUp``) is S5's. Every handler that changes an allocation or
retires a node or area calls ``request`` in its own unit of work, so the queue row and the
ledger events are one transaction.

One row per scope: the job id is the primary key. A row that is ``queued`` already asks for a
run, so a second request changes nothing. A row that finished (``done``, ``failed``,
``cancelled``) is put back in the queue. A row that is ``running`` is left alone: the run read
the ledger when it started, so the run must look at the ledger head when it settles and queue
itself again when it moved (S5).
"""

from __future__ import annotations

from sqlalchemy import text
from tl_adapters.queue import job_queue_for
from tl_core.jobs import DEFAULT_MAX_ATTEMPTS, iso_z
from tl_core.jobs.types import CANCELLED, DONE, FAILED, QUEUED
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_mod_awp.names import JOB_KIND_ROLLUP, ROLLUP_JOB_PREFIX

_REQUEUE_SQL = text(
    "UPDATE job_queue SET state = :queued, attempt = 0, run_after = :now, lease_owner = NULL, "
    "lease_until = NULL, started_at = NULL, finished_at = NULL, last_error = NULL, "
    "enqueued_at = :now WHERE job_id = :job_id AND state IN (:done, :failed, :cancelled)"
)


def job_id(scope: str) -> str:
    return f"{ROLLUP_JOB_PREFIX}{scope}"


def request(uow: UnitOfWork, scope: str) -> bool:
    """Queue the rollup of ``scope`` unless one is queued. ``True`` when this call queued it."""
    conn = uow.conn()
    queue = job_queue_for(conn)
    made = job_id(scope)
    now = utcnow()
    found = queue.get(conn, made)
    if found is None:
        queue.enqueue(
            conn,
            job_id=made,
            kind=JOB_KIND_ROLLUP,
            scope=scope,
            now=now,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
        )
        return True
    if found.state == QUEUED:
        return False
    return (
        conn.execute(
            _REQUEUE_SQL,
            {
                "queued": QUEUED,
                "done": DONE,
                "failed": FAILED,
                "cancelled": CANCELLED,
                "now": iso_z(now),
                "job_id": made,
            },
        ).rowcount
        == 1
    )
