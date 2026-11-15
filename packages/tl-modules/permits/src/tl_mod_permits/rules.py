"""Pure permit rules: shift end, effective state, gas result, issue blockers.

Everything here is a pure function. No database, no clock (the caller passes ``now``), no settings
read (the caller passes the values) and no import from ``tl_core`` or another module. A limit is
never a constant here.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

_SHIFT_START = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")


@dataclass(frozen=True)
class GasLimits:
    o2_min_pct: Decimal
    o2_max_pct: Decimal
    lel_max_pct: Decimal
    h2s_max_ppm: Decimal
    co_max_ppm: Decimal


def _require_aware(value: datetime, what: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{what} must be a timezone-aware datetime")


def shift_end(at: datetime, shift_start: str = "06:00", shift_hours: int = 12) -> datetime:
    """Return the exclusive end of the shift that contains ``at``.

    Shifts are blocks of ``shift_hours`` counted from the most recent ``shift_start`` at or before
    ``at`` (same wall clock and tzinfo as ``at``). The last block before the next ``shift_start`` is
    cut short when ``shift_hours`` does not divide 24.
    """
    _require_aware(at, "at")
    match = _SHIFT_START.fullmatch(shift_start) if isinstance(shift_start, str) else None
    if match is None:
        raise ValueError("shift_start must be HH:MM, 24-hour, two digits")
    if isinstance(shift_hours, bool) or not isinstance(shift_hours, int):
        raise ValueError("shift_hours must be an integer from 4 to 24")
    if not 4 <= shift_hours <= 24:
        raise ValueError("shift_hours must be an integer from 4 to 24")

    hour, minute = int(match.group(1)), int(match.group(2))
    day_start = at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    anchor = day_start if at >= day_start else day_start - timedelta(days=1)
    block = timedelta(hours=shift_hours)
    index = (at - anchor) // block
    end = anchor + (index + 1) * block
    next_start = anchor + timedelta(days=1)
    return min(end, next_start)


def effective_state(state: str, valid_until: datetime | None, now: datetime) -> str:
    """Show an Active permit whose validity has ended, or has no end, as Lapsed.

    Every other state is returned unchanged.
    """
    _require_aware(now, "now")
    if valid_until is not None:
        _require_aware(valid_until, "valid_until")
    if state == "Active" and (valid_until is None or valid_until <= now):
        return "Lapsed"
    return state


def gas_result(
    limits: GasLimits,
    *,
    o2: Decimal | None = None,
    lel: Decimal | None = None,
    h2s: Decimal | None = None,
    co: Decimal | None = None,
) -> Literal["pass", "fail"]:
    """Judge gas readings against the caller's limits. Unmeasured (None) readings are not tested."""
    readings = {"o2": o2, "lel": lel, "h2s": h2s, "co": co}
    measured = {name: value for name, value in readings.items() if value is not None}
    if not measured:
        raise ValueError("gas_result needs at least one reading")
    if any(value < 0 for value in measured.values()):
        raise ValueError("a gas reading cannot be negative")

    if o2 is not None and (o2 < limits.o2_min_pct or o2 > limits.o2_max_pct):
        return "fail"
    if lel is not None and lel > limits.lel_max_pct:
        return "fail"
    if h2s is not None and h2s > limits.h2s_max_ppm:
        return "fail"
    if co is not None and co > limits.co_max_ppm:
        return "fail"
    return "pass"


def issue_blockers(
    *,
    needs_gas_test: bool,
    needs_isolation: bool,
    required_precautions: Sequence[str],
    ticked_precautions: Sequence[str],
    gas_tests: Sequence[tuple[datetime, str]],
    isolation_states: Sequence[str],
    gas_valid_minutes: int,
    now: datetime,
) -> list[str]:
    """Return the codes that refuse an issue, in order: gas, isolation, unticked precautions."""
    _require_aware(now, "now")
    blockers: list[str] = []

    if needs_gas_test:
        if not gas_tests:
            blockers.append("gas_test_missing")
        else:
            for when, result in gas_tests:
                _require_aware(when, "gas test time")
                if result not in ("pass", "fail"):
                    raise ValueError("a gas test result is 'pass' or 'fail'")
            newest = max(when for when, _result in gas_tests)
            results_at_newest = {result for when, result in gas_tests if when == newest}
            if "fail" in results_at_newest:
                blockers.append("gas_test_failed")
            elif now - newest > timedelta(minutes=gas_valid_minutes):
                blockers.append("gas_test_stale")

    if needs_isolation:
        live = [state for state in isolation_states if state != "Removed"]
        if not live:
            blockers.append("isolation_missing")
        elif any(state != "Verified" for state in live):
            blockers.append("isolation_unverified")

    ticked = set(ticked_precautions)
    for precaution_id in required_precautions:
        if precaution_id not in ticked:
            blockers.append(f"precaution_unticked:{precaution_id}")

    return blockers
