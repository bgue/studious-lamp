"""``X-TL-Effective-At``: simulated time for simulation scopes only (FANOUT D5, brief 29.5).

A simulator stamps the events it writes with the day it is playing. The header is honoured on
``POST /commands/*`` and only when the command's scope is ``project:sim-<run>``; any other scope
gets HTTP 400 so a client cannot back-date a real project. The value becomes the ``effective_at``
of the events the command appends (``tl_core.util.effective_time``). ``recorded_at``, the hash
chain and the command models are not touched.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from tl_api.errors import ApiError

EFFECTIVE_AT_HEADER = "X-TL-Effective-At"
SIM_SCOPE = re.compile(r"project:sim-[A-Za-z0-9_.-]+")
MIN_YEAR = 1970  # a sanity bound: a simulation plays real calendar dates, not the ends of time
MAX_YEAR = 2100


def resolve_effective_at(value: str | None, scope: str) -> datetime | None:
    """The instant to stamp, or ``None`` when the header is absent.

    Raises ``ApiError`` 400 ``effective_time_forbidden`` when the scope is not a simulation scope
    and ``invalid_effective_time`` when the value is not an ISO-8601 instant with a UTC offset
    (``2026-11-02T08:00:00Z`` or ``+00:00``) or falls outside the years 1970 to 2100 (also when
    the conversion to UTC overflows). The value is returned in UTC.
    """
    if value is None:
        return None
    if SIM_SCOPE.fullmatch(scope) is None:
        raise ApiError(
            400,
            "effective_time_forbidden",
            f"{EFFECTIVE_AT_HEADER} is only accepted for simulation scopes (project:sim-<run>), "
            f"not {scope!r}",
        )
    problem = ApiError(
        400,
        "invalid_effective_time",
        f"{EFFECTIVE_AT_HEADER} must be an ISO-8601 instant with an offset between "
        f"{MIN_YEAR} and {MAX_YEAR}, for example 2026-11-02T08:00:00Z",
    )
    try:
        parsed = datetime.fromisoformat(value.strip())
        if parsed.tzinfo is None:
            raise problem
        utc = parsed.astimezone(UTC)  # OverflowError at the ends of the calendar
    except (ValueError, OverflowError):
        raise problem from None
    if not MIN_YEAR <= utc.year <= MAX_YEAR:
        raise problem
    return utc
