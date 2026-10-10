"""The simulated clock and the working calendar.

``SimClock`` holds the instant the next write is stamped with. The HTTP client copies it into the
``X-TL-Effective-At`` header of every request (``client.install_stamp``) and moves it on by
``STEP`` before each write, so the events of one day are ordered and distinct. ``working_date``
maps a day index (0, 1, 2, ...) to the calendar date of that working day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

STEP = timedelta(minutes=1)
WORKDAY_START_HOUR = 7
SEED_HOUR = 6  # the template is loaded an hour before the first actor starts
ACTOR_STAGGER = timedelta(minutes=30)  # each actor starts half an hour after the previous one

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class SimClock:
    """A mutable instant. ``stamp`` is what the next request carries."""

    def __init__(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("SimClock needs a timezone-aware datetime")
        self._now = now.astimezone(UTC)

    @property
    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("SimClock needs a timezone-aware datetime")
        self._now = now.astimezone(UTC)

    def tick(self) -> datetime:
        """Move on by one step and return the new instant (called before each write)."""
        self._now = self._now + STEP
        return self._now

    def stamp(self) -> str:
        """The header value: the current instant, ISO-8601 UTC with an explicit ``+00:00``."""
        return self._now.isoformat()


def working_date(start: date, day: int, working_days: tuple[str, ...]) -> date:
    """The calendar date of working day number ``day`` (0-based), counting from ``start``.

    ``start`` itself counts as day 0 only when it is a working day; otherwise day 0 is the next
    working day. ``working_days`` holds weekday names from ``WEEKDAYS`` and must not be empty.
    """
    if day < 0:
        raise ValueError("day must be 0 or more")
    allowed = {WEEKDAYS.index(name) for name in working_days}
    if not allowed:
        raise ValueError("working_days must not be empty")
    current = start
    remaining = day
    while True:
        if current.weekday() in allowed:
            if remaining == 0:
                return current
            remaining -= 1
        current += timedelta(days=1)


def day_start(date_: date, slot: int = 0) -> datetime:
    """The instant ``slot`` (0 for the first actor of the day) begins work on ``date_``, in UTC."""
    base = datetime(date_.year, date_.month, date_.day, WORKDAY_START_HOUR, tzinfo=UTC)
    return base + ACTOR_STAGGER * slot


def seed_time(date_: date) -> datetime:
    """When the seed step of a run begins, on the first working day."""
    return datetime(date_.year, date_.month, date_.day, SEED_HOUR, tzinfo=UTC)
