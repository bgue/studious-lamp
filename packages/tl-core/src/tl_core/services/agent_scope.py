"""What an agent may file (P2-X2). Seam stub: S1 fills ``check_filing``; S2 adds the queue cap here."""

from __future__ import annotations

from sqlalchemy import Connection

from tl_core.services.commands import Command


def check_filing(conn: Connection, agent: str, command: Command) -> None:
    """Refuse a filing the agent has no module ``user`` word for (ADR-0027 F1). Stub: allows all."""
    return None
