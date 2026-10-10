"""Shared helpers: current UTC time, new ULIDs, and the simulated-time override."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from ulid import ULID

_EFFECTIVE_TIME: ContextVar[datetime | None] = ContextVar("tl_effective_time", default=None)


def utcnow() -> datetime:
    """Current time, timezone-aware UTC: datetime.now(UTC)."""
    return datetime.now(UTC)


def new_ulid() -> str:
    """A new ULID as a 26-character string, using python-ulid: str(ULID())."""
    return str(ULID())


def current_effective_time() -> datetime | None:
    """The simulated instant set by the innermost ``effective_time`` block, else ``None``."""
    return _EFFECTIVE_TIME.get()


@contextmanager
def effective_time(at: datetime | None) -> Generator[None]:
    """Stamp ``effective_at = at`` on events appended inside the block (FANOUT D5, brief 29.5).

    The ledger adapters read this when ``NewEvent.effective_at`` is ``None``; an event that sets
    its own ``effective_at`` keeps it, and ``recorded_at`` and the hash chain never change (the
    hash covers ``recorded_at``, not ``effective_at``). The value lives in a context variable, so
    it is per thread and per asyncio task, and a worker thread started inside the block with a
    copied context sees it. ``at`` must be timezone-aware; ``None`` clears an outer override.
    Blocks nest, and the previous value is restored on exit, including on an exception.
    """
    if at is not None and at.tzinfo is None:
        raise ValueError("effective_time needs a timezone-aware datetime")
    token = _EFFECTIVE_TIME.set(at)
    try:
        yield
    finally:
        _EFFECTIVE_TIME.reset(token)
