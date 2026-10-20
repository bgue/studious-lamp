"""ScheduleTables: the operational tables of the typed rows of a snapshot (ADR-0015).

``sched_*`` are not projections: no event produces them, a rebuild must never clear them (the rows
come from the source XER file, not from the ledger), and the archive and webhooks never read them.
They still need creating next to every other table, in both dialects, so they ride on a projector
that handles no event types: ``create_schema`` runs its ``ddl``, ``apply`` is never called, and
``reset`` leaves the data alone (the pattern of ``JobQueueTables``). ``reconcile``
(``tl_mod_schedule.rebuild``) writes them again from the source file after a restore.
"""

from __future__ import annotations

from sqlalchemy import Connection
from tl_core.ledger import Event

from tl_mod_schedule.names import TYPED_TABLES
from tl_mod_schedule.projectors._common import ddl_for


class ScheduleTables:
    name = "schedule_snapshot_tables"
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        found: list[str] = []
        for table in TYPED_TABLES.values():
            found.extend(ddl_for(table, dialect))
        return found

    def apply(self, conn: Connection, event: Event) -> None:
        raise ValueError(f"{self.name} handles no events, got {event.event_type}")

    def reset(self, conn: Connection) -> None:
        """Deliberately empty: the typed rows are operational state, not derived from the ledger."""
