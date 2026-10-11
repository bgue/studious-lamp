"""Clock helpers for the auth package: ISO-8601 UTC text that sorts correctly on both databases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def iso_z(moment: datetime) -> str:
    """ISO-8601 UTC with microseconds and a ``Z`` suffix (``2026-10-11T03:14:07.000000Z``)."""
    if moment.tzinfo is None:
        raise ValueError("iso_z requires a timezone-aware datetime")
    return moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_iso(text: str) -> datetime:
    """Parse the forms this package and the ledger write (``Z`` or ``+00:00``)."""
    return datetime.fromisoformat(text).astimezone(UTC)
