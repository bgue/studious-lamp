"""The operational tables of webhook delivery, created with the rest of the schema.

``wh_delivery``, ``wh_attempt``, ``wh_secret``, ``wh_health`` and ``wh_cursor`` are not projections:
no event produces them, a rebuild must never clear them (a secret or a retry state cannot be
re-derived from the ledger). They still need creating next to every other table, in both
dialects, so they ride on a projector that handles no event types: ``create_schema`` runs its
``ddl``, ``apply`` is never called, and ``reset`` leaves the data alone.
"""

from __future__ import annotations

from sqlalchemy import Connection
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event

OPERATIONAL_TABLES = ("wh_delivery", "wh_attempt", "wh_secret", "wh_health", "wh_cursor")


class WebhookStateTables:
    name = "webhook_state"
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
        """Deliberately empty: operational state is not rebuilt from the ledger."""
