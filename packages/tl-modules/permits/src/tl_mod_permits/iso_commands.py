"""The six isolation and gas test commands (P2-PTW S3).

The API builds one ``POST /commands/<Name>`` route per row of ``module.COMMANDS``. Every model is
``extra="forbid"``: the person who applied, verified or removed an isolation and the person who took
a gas test, is the actor of the command, never a field; the ``result`` of a gas test is computed
(``rules.gas_result``), so a ``result`` field is refused as unknown. Every text has a length and is
cleaned with ``tl_core.text``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, field_validator, model_validator
from tl_core.services.commands import Command
from tl_core.text import clean_text

MAX_POINT = 120
MAX_METHOD = 120
MAX_TAG = 40
MAX_INSTRUMENT = 64
MAX_NOTE = 300
MAX_ID = 40
MAX_PERCENT = Decimal(100)
MAX_PPM = Decimal(100000)
READING_PLACES = 3

EnergyKind = Literal["electrical", "mechanical", "process", "other"]


def _text(value: str) -> str:
    """A one-line text with something in it, with no control or direction characters."""
    if not clean_text(value).strip():
        raise ValueError("text must not be blank")
    return value


def _decimal_text(value: object) -> object:
    """A reading sent as a number is read as its decimal text (never through a binary float)."""
    if isinstance(value, bool):
        raise ValueError("a reading is a decimal number")
    if isinstance(value, int | float | Decimal):
        return str(value)
    return value


#: A reading as decimal text (``"20.9"``): at most six whole digits and three places, as the event
#: carries it. It is text so that the command table does not read it as an amount of money; the
#: handler reads it as a ``Decimal``.
Reading = Annotated[str, BeforeValidator(_decimal_text)]


def _bounded(value: str | None, ceiling: Decimal) -> str | None:
    """``value`` as plain decimal text between 0 and ``ceiling``, with at most three places."""
    if value is None:
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        raise ValueError("a reading is a decimal number") from None
    if not number.is_finite() or number < 0 or number > ceiling:
        raise ValueError(f"a reading is between 0 and {ceiling}")
    if int(number.normalize().as_tuple().exponent) < -READING_PLACES:
        raise ValueError(f"a reading has at most {READING_PLACES} decimal places")
    return format(number.normalize() if number else Decimal(0), "f")


class _Strict(Command):
    model_config = ConfigDict(extra="forbid")


class ApplyIsolation(_Strict):
    """Record a lockout of one point of one kind of energy (state Applied, key ``P123-ISL-0001``).
    ``applied_by`` is the actor. ``point_record_id`` names a tag or equipment record, if any."""

    point_text: str = Field(min_length=1, max_length=MAX_POINT)
    energy: EnergyKind
    method: str = Field(min_length=1, max_length=MAX_METHOD)
    lock_number: str = Field(min_length=1, max_length=MAX_TAG)
    tag_number: str = Field(min_length=1, max_length=MAX_TAG)
    point_record_id: str | None = Field(default=None, min_length=1, max_length=MAX_ID)

    @field_validator("point_text", "method", "lock_number", "tag_number")
    @classmethod
    def _one_line(cls, value: str) -> str:
        return _text(value)


class _OnIsolation(_Strict):
    isolation: str = Field(min_length=1, max_length=MAX_ID)
    expected_version: int | None = Field(default=None, ge=1)


class VerifyIsolation(_OnIsolation):
    """Applied to Verified, by a controller other than the person who applied it."""


class RemoveIsolation(_OnIsolation):
    """Applied or Verified to Removed, while no Approved, Active or Suspended permit needs it."""


class _Link(_Strict):
    permit: str = Field(min_length=1, max_length=MAX_ID)
    isolation: str = Field(min_length=1, max_length=MAX_ID)


class LinkIsolation(_Link):
    """The permit depends on the isolation (not while the permit is Active or Lapsed)."""


class UnlinkIsolation(_Link):
    """The permit no longer depends on the isolation (not while the permit is Active or Lapsed)."""


class RecordGasTest(_Strict):
    """One gas test of a permit. At least one reading; the result is computed from the project's
    limits. A failing test suspends an Active or Lapsed permit of a type that needs a gas test."""

    permit: str = Field(min_length=1, max_length=MAX_ID)
    instrument_text: str = Field(min_length=1, max_length=MAX_INSTRUMENT)
    taken_at: datetime | None = None
    o2_pct: Reading | None = None
    lel_pct: Reading | None = None
    h2s_ppm: Reading | None = None
    co_ppm: Reading | None = None
    note: str | None = Field(default=None, min_length=1, max_length=MAX_NOTE)

    @field_validator("o2_pct", "lel_pct")
    @classmethod
    def _percent(cls, value: str | None) -> str | None:
        return _bounded(value, MAX_PERCENT)

    @field_validator("h2s_ppm", "co_ppm")
    @classmethod
    def _ppm(cls, value: str | None) -> str | None:
        return _bounded(value, MAX_PPM)

    @field_validator("instrument_text", "note")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return None if value is None else _text(value)

    @field_validator("taken_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("taken_at must carry a time zone")
        try:
            return value.astimezone(UTC)
        except OverflowError:
            raise ValueError("taken_at is outside the dates that can be stored") from None

    @model_validator(mode="after")
    def _some_reading(self) -> RecordGasTest:
        if all(r is None for r in (self.o2_pct, self.lel_pct, self.h2s_ppm, self.co_ppm)):
            raise ValueError("a gas test needs at least one reading")
        return self


__all__ = [
    "ApplyIsolation",
    "LinkIsolation",
    "RecordGasTest",
    "RemoveIsolation",
    "UnlinkIsolation",
    "VerifyIsolation",
]
