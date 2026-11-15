"""The pure rules of the scaffold module: tag colour, next due, due state, the dismantle check.

No database and no clock: values in, values out, so the handlers, the inspections-due job and any
readiness check share them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Final

#: A result and the tag colour it gives.
TAGS: Final = {"pass": "green", "conditional": "yellow", "fail": "red"}
MIN_INTERVAL_DAYS: Final = 1
MAX_INTERVAL_DAYS: Final = 90

#: States in which an inspection may be recorded (a scaffold that stands, or is being built).
INSPECTABLE_STATES: Final = frozenset({"Erecting", "Inspected", "In Use", "Modify"})
#: States in which the next inspection can be late: the scaffold stands.
STANDING_STATES: Final = frozenset({"Inspected", "In Use", "Modify"})
#: IWP states in which a work package holds the scaffold it requires.
HOLDING_IWP_STATES: Final = frozenset({"Issued", "In progress", "On hold"})


def tag_for(result: str) -> str:
    """The tag colour an inspection result gives; ``ValueError`` for anything else."""
    try:
        return TAGS[result]
    except KeyError:
        raise ValueError(f"unknown inspection result: {result!r}") from None


def next_due(inspected_on: date, interval_days: int) -> date:
    """The day the next inspection falls due; ``ValueError`` unless the interval is 1 to 90 days."""
    if not MIN_INTERVAL_DAYS <= interval_days <= MAX_INTERVAL_DAYS:
        raise ValueError(
            f"the inspection interval is {MIN_INTERVAL_DAYS} to {MAX_INTERVAL_DAYS} days"
        )
    return inspected_on + timedelta(days=interval_days)


def due_state(state: str, last_inspected_on: date | None, today: date, interval_days: int) -> str:
    """``n_a`` unless the scaffold stands; else ``ok`` before the due day, ``due`` on it and
    ``overdue`` after it. A standing scaffold that was never inspected is ``overdue``."""
    if state not in STANDING_STATES:
        return "n_a"
    if last_inspected_on is None:
        return "overdue"
    due = next_due(last_inspected_on, interval_days)
    if today < due:
        return "ok"
    return "due" if today == due else "overdue"


def dismantle_blockers(
    iwp_states: Mapping[str, str], other_open_requests: Sequence[str]
) -> list[str]:
    """The reasons not to dismantle: one per requiring work package that holds the scaffold, one
    per other scaffold request of such a package still open. Empty means go ahead."""
    reasons = [
        f"work package {number} is {state} and requires this scaffold"
        for number, state in sorted(iwp_states.items())
        if state in HOLDING_IWP_STATES
    ]
    reasons.extend(
        f"scaffold request {number} is still open" for number in sorted(other_open_requests)
    )
    return reasons
