"""Project calendars: which days are worked, and counting days on them (brief 9 M10: clocks).

A calendar is a fixture file ``<schema dir>/calendars/<code>@<version>.yaml`` (see
``schema/fixtures/calendars/P123-default@1.yaml``). A version never changes: a clock records
``code@version`` in its first event, so the same events always give the same due date. The file
lists the weekly rest days and the holidays, and the first and last date it is complete for. A
count that would touch a date outside that range is **refused** (``CalendarRangeError``); the
engine never assumes that an uncovered day is a working day.

Counting convention: day zero is the start date and is not counted. ``add_days(start, n)`` is the
n-th counted day after ``start``; ``count_days(after, upto)`` is the number of counted days in
``(after, upto]``. A calendar-day count counts every day; a working-day count counts the days
that are not rest days and not holidays. Work is bounded: at most ``MAX_SPAN_DAYS`` days are
walked in any one call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from tl_schema.registry import default_schema_dir

MAX_SPAN_DAYS: Final = 366 * 12  # the longest stretch one call walks (a clock is at most 3650 days)
MAX_HOLIDAYS: Final = 2000
MAX_FILE_BYTES: Final = 1024 * 1024
WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_REF = re.compile(r"([A-Za-z0-9_.-]{1,64})@([1-9][0-9]{0,5})")


class CalendarError(ValueError):
    """A calendar file or reference that cannot be used. The message names the source."""


class CalendarRangeError(CalendarError):
    """A date lies outside the range the calendar is complete for."""


class _Holiday(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    on: date = Field(alias="date")
    name: str = Field(min_length=1, max_length=200)


class _CalendarFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int = Field(ge=1, le=999_999)
    scope: str
    name: str = Field(min_length=1, max_length=200)
    rest_days: list[str]
    covers_from: date
    covers_to: date
    holidays: list[_Holiday] = Field(max_length=MAX_HOLIDAYS)

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if _CODE.fullmatch(value) is None:
            raise ValueError("the calendar id may hold letters, digits and _.- only")
        return value

    @field_validator("scope")
    @classmethod
    def _scope(cls, value: str) -> str:
        if re.fullmatch(r"company|project:[A-Za-z0-9_.-]{1,64}", value) is None:
            raise ValueError("the scope is company or project:<id>")
        return value

    @field_validator("rest_days")
    @classmethod
    def _rest(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(day not in WEEKDAYS for day in value):
            raise ValueError("rest_days are distinct weekdays: " + " ".join(WEEKDAYS))
        if len(value) >= 7:
            raise ValueError("a calendar needs at least one working day in the week")
        return value


@dataclass(frozen=True)
class Calendar:
    """A loaded calendar. ``ref`` is the ``code@version`` that clock events record."""

    code: str
    version: int
    scope: str
    name: str
    rest_weekdays: frozenset[int]  # 0 is Monday
    covers_from: date
    covers_to: date
    holidays: frozenset[date]

    @property
    def ref(self) -> str:
        return f"{self.code}@{self.version}"

    def covers(self, day: date) -> bool:
        return self.covers_from <= day <= self.covers_to

    def _require(self, *days: date) -> None:
        for day in days:
            if not self.covers(day):
                raise CalendarRangeError(
                    f"{day.isoformat()} is outside the range calendar {self.ref} covers "
                    f"({self.covers_from.isoformat()} to {self.covers_to.isoformat()})"
                )

    def is_working(self, day: date) -> bool:
        """True when ``day`` is worked. Raises ``CalendarRangeError`` outside the covered range."""
        self._require(day)
        return day.weekday() not in self.rest_weekdays and day not in self.holidays

    def add_days(self, start: date, count: int, day_type: str) -> date:
        """The ``count``-th counted day after ``start`` (``count`` 0 gives ``start``).

        ``day_type`` is ``calendar`` or ``working``. Raises ``ValueError`` for a negative count,
        a count over ``MAX_SPAN_DAYS`` or another day type, and ``CalendarRangeError`` when the
        walk leaves the covered range (a calendar-day count needs no calendar and never raises it).
        """
        if day_type not in ("calendar", "working"):
            raise ValueError(f"day_type is calendar or working, not {day_type!r}")
        if count < 0 or count > MAX_SPAN_DAYS:
            raise ValueError(f"a count is 0 to {MAX_SPAN_DAYS} days, not {count}")
        if day_type == "calendar":
            return start + timedelta(days=count)
        self._require(start)
        current, remaining = start, count
        for _ in range(MAX_SPAN_DAYS * 2):
            if remaining == 0:
                return current
            current += timedelta(days=1)
            self._require(current)
            if self.is_working(current):
                remaining -= 1
        raise ValueError("the count did not end within the walk bound")

    def count_days(self, after: date, upto: date, day_type: str) -> int:
        """The number of counted days in ``(after, upto]``; 0 when ``upto`` is not later.

        Raises like ``add_days`` (a span over ``MAX_SPAN_DAYS`` days is a ``ValueError``).
        """
        if day_type not in ("calendar", "working"):
            raise ValueError(f"day_type is calendar or working, not {day_type!r}")
        span = (upto - after).days
        if span <= 0:
            return 0
        if span > MAX_SPAN_DAYS:
            raise ValueError(f"a span is at most {MAX_SPAN_DAYS} days, not {span}")
        if day_type == "calendar":
            return span
        self._require(after, upto)
        return sum(1 for i in range(1, span + 1) if self.is_working(after + timedelta(days=i)))


def parse_calendar(text: str, *, source: str = "<string>") -> Calendar:
    """Parse and check calendar YAML. Raises ``CalendarError`` starting with ``source``."""
    try:
        data = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError, ValueError) as exc:
        raise CalendarError(f"{source}: the calendar is not readable YAML") from exc
    if not isinstance(data, dict):
        raise CalendarError(f"{source}: a calendar file must be a YAML mapping")
    try:
        parsed = _CalendarFile.model_validate(data)
    except ValidationError as exc:
        lines = [
            f"{source}: {'.'.join(str(p) for p in e['loc']) or '(document)'}: {e['msg']}"
            for e in exc.errors()
        ]
        raise CalendarError("\n".join(lines)) from exc
    if parsed.covers_to < parsed.covers_from:
        raise CalendarError(f"{source}: covers_to is before covers_from")
    if (parsed.covers_to - parsed.covers_from).days > 366 * 30:
        raise CalendarError(f"{source}: a calendar covers at most 30 years")
    days = [h.on for h in parsed.holidays]
    if len(set(days)) != len(days):
        raise CalendarError(f"{source}: a holiday is listed twice")
    outside = [d for d in days if not parsed.covers_from <= d <= parsed.covers_to]
    if outside:
        raise CalendarError(f"{source}: holiday {outside[0].isoformat()} is outside covers_from/to")
    return Calendar(
        code=parsed.id,
        version=parsed.version,
        scope=parsed.scope,
        name=parsed.name,
        rest_weekdays=frozenset(WEEKDAYS.index(d) for d in parsed.rest_days),
        covers_from=parsed.covers_from,
        covers_to=parsed.covers_to,
        holidays=frozenset(days),
    )


def split_ref(ref: str) -> tuple[str, int]:
    """``("P123-default", 1)`` from ``"P123-default@1"``. Raises ``CalendarError`` otherwise."""
    match = _REF.fullmatch(ref)
    if match is None:
        raise CalendarError(f"{ref!r} is not a calendar reference (code@version)")
    return match.group(1), int(match.group(2))


def load_calendar(ref: str, directory: Path | None = None) -> Calendar:
    """The calendar ``ref`` (``code@version``) from ``<directory>/calendars/``.

    ``directory`` defaults to the schema directory (``TL_SCHEMA_DIR`` or ``schema/fixtures``).
    The reference is checked before it becomes a file name, the file is read up to
    ``MAX_FILE_BYTES``, and its own ``id`` and ``version`` must equal the reference.
    """
    code, version = split_ref(ref)
    path = (directory or default_schema_dir()) / "calendars" / f"{code}@{version}.yaml"
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise CalendarError(f"no calendar {ref}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise CalendarError(f"calendar {ref} is larger than {MAX_FILE_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CalendarError(f"calendar {ref} is not UTF-8") from exc
    calendar = parse_calendar(text, source=path.name)
    if (calendar.code, calendar.version) != (code, version):
        raise CalendarError(f"calendar file {path.name} declares {calendar.ref}")
    return calendar


def list_calendars(directory: Path | None = None) -> list[str]:
    """The references of the calendars in the directory, sorted (``code@version``)."""
    folder = (directory or default_schema_dir()) / "calendars"
    if not folder.is_dir():
        return []
    found = [p.stem for p in folder.glob("*.yaml") if _REF.fullmatch(p.stem)]
    return sorted(found)
