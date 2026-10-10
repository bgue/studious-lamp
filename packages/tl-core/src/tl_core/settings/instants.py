"""Instants as the settings code keeps them: microseconds since the epoch, and ``Z`` text."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def to_us(moment: datetime) -> int:
    """Microseconds since the epoch, exactly. A naive datetime is taken as UTC."""
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return (aware - _EPOCH) // timedelta(microseconds=1)


def from_us(microseconds: int) -> datetime:
    """The instant ``microseconds`` after the epoch (UTC), exactly."""
    return _EPOCH + timedelta(microseconds=microseconds)


def to_z(value: str | datetime) -> str:
    """An instant as ``2026-10-10T12:00:00.000000Z`` (UTC)."""
    moment = datetime.fromisoformat(value) if isinstance(value, str) else value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
