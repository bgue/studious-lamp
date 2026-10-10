"""Date and time values in queries: literals, relative dates, and the day windows they compile to.

A *window* is a half-open interval ``[start, end)`` of UTC instants. ``created_at<=2026-10-09``
means "before the end of that day", ``=`` means "inside the day", so every comparison reduces to
a bound on a window edge (the compiler does that).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone

from tl_core.ledger import iso_utc
from tl_core.query.ast import RelativeDate
from tl_core.query.clock import QueryClock

MAX_RELATIVE_DAYS = 36500  # about a century; keeps date arithmetic far from the calendar limits

_RELATIVE_RE = re.compile(r"^([+-])(\d{1,6})d\Z")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\Z")
_DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?"
    r"(Z|z|[+-]\d{2}:\d{2})?\Z"
)


@dataclass(frozen=True)
class DayLiteral:
    """A calendar date such as ``2026-10-09`` (a day in the project time zone)."""

    day: date


@dataclass(frozen=True)
class InstantLiteral:
    """A date-time such as ``2026-10-09T12:30:00Z``; ``end`` is one unit of precision later."""

    start: datetime
    end: datetime


def parse_relative(raw: str) -> RelativeDate | None:
    """``+7d``, ``-3d`` and ``today`` as a :class:`RelativeDate`; ``None`` for anything else.

    Raises ``ValueError`` when the offset is larger than :data:`MAX_RELATIVE_DAYS`.
    """
    if raw.lower() == "today":
        return RelativeDate(0)
    match = _RELATIVE_RE.match(raw)
    if match is None:
        return None
    days = int(match.group(2))
    if days > MAX_RELATIVE_DAYS:
        raise ValueError(f"a relative date may not be more than {MAX_RELATIVE_DAYS} days away")
    return RelativeDate(-days if match.group(1) == "-" else days)


def parse_literal(raw: str) -> DayLiteral | InstantLiteral | None:
    """A date or date-time literal; ``None`` when ``raw`` does not look like one.

    Raises ``ValueError`` when it looks like one but is not a real date (``2026-13-40``).
    A date-time without an offset is read as UTC.
    """
    match = _DATE_RE.match(raw)
    if match is not None:
        return DayLiteral(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    match = _DATETIME_RE.match(raw)
    if match is None:
        return None
    year, month, day, hour, minute = (int(match.group(n)) for n in range(1, 6))
    second = int(match.group(6)) if match.group(6) else 0
    fraction = match.group(7)
    micro = int(fraction.ljust(6, "0")) if fraction else 0
    zone = match.group(8)
    if zone is None or zone in ("Z", "z"):
        offset = timedelta(0)
    else:
        sign = -1 if zone[0] == "-" else 1
        offset = sign * timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
        if abs(offset) >= timedelta(hours=24):
            raise ValueError(f"invalid UTC offset {zone!r}")
    start = datetime(year, month, day, hour, minute, second, micro, tzinfo=timezone(offset))
    if fraction:
        unit = timedelta(microseconds=1)
    elif match.group(6):
        unit = timedelta(seconds=1)
    else:
        unit = timedelta(minutes=1)
    return InstantLiteral(start.astimezone(UTC), (start + unit).astimezone(UTC))


def day_window(day: date, clock: QueryClock) -> tuple[datetime, datetime]:
    """The UTC instants at which ``day`` starts and ends in the project time zone.

    Raises ``OverflowError`` for a day too close to the calendar's limits.
    """
    start = datetime.combine(day, time.min, tzinfo=clock.tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=clock.tz).astimezone(UTC)
    return start, end


def relative_day(value: RelativeDate, clock: QueryClock) -> date:
    """The calendar date ``value.days`` from today. Raises ``OverflowError`` out of range."""
    return clock.today() + timedelta(days=value.days)


def iso_window(
    value: RelativeDate | DayLiteral | InstantLiteral, clock: QueryClock
) -> tuple[str, str]:
    """``(start, end)`` of a temporal value as ISO strings in the stored column format."""
    if isinstance(value, InstantLiteral):
        return iso_utc(value.start), iso_utc(value.end)
    day = relative_day(value, clock) if isinstance(value, RelativeDate) else value.day
    start, end = day_window(day, clock)
    return iso_utc(start), iso_utc(end)
