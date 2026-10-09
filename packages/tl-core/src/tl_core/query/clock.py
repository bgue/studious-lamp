"""The injectable clock that resolves relative dates (``+7d``, ``today``) in queries.

Relative dates mean "this many days from today in the project time zone". The default clock is
the system clock in UTC. Tests, and later the project's time-zone setting, install another one
with :func:`use_clock`. The setting is per context (``ContextVar``), so a worker thread that
wants a non-default clock installs it itself.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo
from zoneinfo import ZoneInfo

from tl_core.util import utcnow


@dataclass(frozen=True)
class QueryClock:
    """``now`` gives a timezone-aware instant; ``tz`` is the project time zone."""

    now: Callable[[], datetime] = utcnow
    tz: tzinfo = UTC

    def today(self) -> date:
        """The calendar date in the project time zone."""
        moment = self.now()
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("the query clock must return timezone-aware datetimes")
        return moment.astimezone(self.tz).date()


_current: ContextVar[QueryClock | None] = ContextVar("tl_query_clock", default=None)
_DEFAULT = QueryClock()


def current_clock() -> QueryClock:
    """The clock in force in this context."""
    return _current.get() or _DEFAULT


@contextmanager
def use_clock(
    now: Callable[[], datetime] | datetime | None = None,
    tz: tzinfo | str = UTC,
) -> Generator[QueryClock]:
    """Install a clock for the block. ``now`` may be a fixed aware datetime; ``tz`` a zone name."""
    source: Callable[[], datetime]
    if now is None:
        source = utcnow
    elif isinstance(now, datetime):
        fixed = now

        def source() -> datetime:
            return fixed

    else:
        source = now
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    clock = QueryClock(now=source, tz=zone)
    token = _current.set(clock)
    try:
        yield clock
    finally:
        _current.reset(token)
