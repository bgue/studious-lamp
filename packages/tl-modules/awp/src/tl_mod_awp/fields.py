"""Checks of the typed fields of a package (CWP, owner packages): dates, hours, quantities.

Plain functions that raise ``ValueError`` with a fixed message and never repeat the value, so a
command model can call them from a pydantic validator and a handler can call them again on the
values it merges. Decimals are text with ASCII digits only (``[0-9]``, never ``\\d``).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from tl_core.text import clean_text

from tl_mod_awp.limits import MAX_QUANTITIES

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_HOURS = re.compile(r"[0-9]{1,8}(?:\.[0-9])?")
_QTY = re.compile(r"[0-9]{1,12}(?:\.[0-9]{1,3})?")
MAX_HOURS = Decimal("10000000.0")


def parse_date(value: str) -> str:
    """``YYYY-MM-DD`` that is a real day."""
    if _DATE.fullmatch(value) is None:
        raise ValueError("a date is written YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError("a date is written YYYY-MM-DD") from None
    return value


def parse_hours(value: str) -> str:
    """Budget hours from 0 to 10 000 000 with at most one decimal, as text with one decimal."""
    if _HOURS.fullmatch(value) is None:
        raise ValueError("budget hours is a number with at most one decimal")
    hours = Decimal(value)
    if hours > MAX_HOURS:
        raise ValueError("budget hours is from 0 to 10000000")
    return f"{hours:.1f}"


def parse_quantity(value: str) -> str:
    """A quantity: a number with at most three decimals, ASCII digits."""
    if _QTY.fullmatch(value) is None:
        raise ValueError("a quantity is a number with at most three decimals")
    return value


def check_period(start: str | None, finish: str | None) -> None:
    """``planned_finish`` is not before ``planned_start`` (when both are set)."""
    if start is not None and finish is not None and finish < start:
        raise ValueError("the planned finish is before the planned start")


def check_quantity_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """At most 50 rows of ``{commodity, qty, uom}``, each text one line."""
    if len(rows) > MAX_QUANTITIES:
        raise ValueError("a package holds at most 50 quantity rows")
    out: list[dict[str, str]] = []
    for row in rows:
        out.append(
            {
                "commodity": clean_text(row["commodity"]),
                "qty": parse_quantity(row["qty"]),
                "uom": clean_text(row["uom"]),
            }
        )
    return out


def as_rows(value: Any) -> list[dict[str, str]] | None:
    """The stored ``quantities_json`` list, or ``None``."""
    if value is None:
        return None
    return [dict(r) for r in value]
