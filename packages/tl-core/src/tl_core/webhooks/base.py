"""Shared small types for the webhook engine."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Protocol

from tl_core.uow import UnitOfWork

Clock = Callable[[], datetime]


class UowFactory(Protocol):
    """Opens an entered unit of work: one transaction, committed on normal exit.

    The SQLite adapter provides ``tl_adapters.sqlite.factory.SqliteUowFactory``; the Postgres
    adapter
    provides the same call shape. ``readonly=True`` may open a read snapshot that refuses appends.
    """

    def __call__(self, *, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(moment: datetime) -> str:
    """ISO-8601 UTC with microseconds and a ``Z`` suffix; sorts and compares correctly as text."""
    if moment.tzinfo is None:
        raise ValueError("iso_z requires a timezone-aware datetime")
    return moment.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_iso(text: str) -> datetime:
    """Parse the ISO forms this package writes (``Z`` or ``+00:00``)."""
    return datetime.fromisoformat(text).astimezone(UTC)
