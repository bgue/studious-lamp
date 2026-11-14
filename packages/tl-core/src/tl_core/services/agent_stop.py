"""The per-agent stop switch (P2-X2). Seam stub: S3 fills it. ADR-0029 decision 6 calls ``is_stopped``."""

from __future__ import annotations

from sqlalchemy import Connection


def is_stopped(conn: Connection, agent: str) -> bool:
    """True while ``Agent.Stopped`` has no later ``Agent.Resumed`` for ``agent``. Stub: False."""
    return False


def require_not_stopped(conn: Connection, agent: str) -> None:
    """Refuse (fixed text, no counts) a filing or an accept for a stopped agent. Stub: allows all."""
    return None
