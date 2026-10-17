"""The job queue for each database (ADR-0014).

``tl_core.jobs.queue.JobQueue`` holds every rule and all portable SQL. The one thing that differs
by database is the lock the claim takes on its candidate row, so this is all there is here:
Postgres appends ``FOR UPDATE SKIP LOCKED`` (a second claimer skips a row another transaction is
claiming instead of waiting for it), SQLite appends nothing (its write transaction already holds
the single writer lock, so nobody else can be claiming).
"""

from __future__ import annotations

from sqlalchemy import Connection
from tl_core.jobs.queue import JobQueue

#: The clause the Postgres claim appends to its candidate select.
POSTGRES_CLAIM_LOCK = " FOR UPDATE SKIP LOCKED"


class SqliteJobQueue(JobQueue):
    claim_lock = ""


class PostgresJobQueue(JobQueue):
    claim_lock = POSTGRES_CLAIM_LOCK


def job_queue_for(conn: Connection) -> JobQueue:
    """The queue for the database ``conn`` is open on."""
    if conn.dialect.name == "postgresql":
        return PostgresJobQueue()
    return SqliteJobQueue()


def job_queue_for_dialect(dialect: str) -> JobQueue:
    """The queue for ``"sqlite"`` or ``"postgres"``."""
    if dialect == "postgres":
        return PostgresJobQueue()
    if dialect == "sqlite":
        return SqliteJobQueue()
    raise ValueError(f"unsupported dialect: {dialect}")
