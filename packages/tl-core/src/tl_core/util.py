"""Shared helpers: current UTC time and new ULIDs."""

from __future__ import annotations

from datetime import UTC, datetime

from ulid import ULID


def utcnow() -> datetime:
    """Current time, timezone-aware UTC: datetime.now(UTC)."""
    return datetime.now(UTC)


def new_ulid() -> str:
    """A new ULID as a 26-character string, using python-ulid: str(ULID())."""
    return str(ULID())
