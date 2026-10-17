"""The operational table of the job queue, created with the rest of the schema (ADR-0014).

``job_queue`` is not a projection: no event produces it, a rebuild must never clear it (a lease
and a retry time cannot be re-derived from the ledger). It still needs creating next to every other
table, in both dialects, so it rides on a projector that handles no event types: ``create_schema``
runs its ``ddl``, ``apply`` is never called, and ``reset`` leaves the data alone (the pattern of
``WebhookStateTables`` and ``AuthStateTables``).
"""

from __future__ import annotations

from sqlalchemy import Connection
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event

OPERATIONAL_TABLES = ("job_queue",)


class JobQueueTables:
    name = "job_queue_state"
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        if dialect != "sqlite" and dialect != "postgres":
            raise ValueError(f"unsupported dialect: {dialect}")
        found: list[str] = []
        for table in OPERATIONAL_TABLES:
            found.extend(statements(table, dialect))
        return found

    def apply(self, conn: Connection, event: Event) -> None:
        raise ValueError(f"{self.name} handles no events, got {event.event_type}")

    def reset(self, conn: Connection) -> None:
        """Deliberately empty: the queue is operational state, not derived from the ledger."""
