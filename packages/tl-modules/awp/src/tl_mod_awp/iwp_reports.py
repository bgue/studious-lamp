"""The IWP and constraint reports (P2-I2-T09a): functions over the views, never over tables.

Each takes a connection and a project scope and reads through ``iwp_views.iwp_list``,
``readiness.views.readiness`` and ``tl_core.constraints.list_constraints``, so the viewer's class
filter (ADR-0016) applies to every figure. ``to_csv`` and ``format_value`` are the CWP reports'
(``reports.py``). A readiness row names checks and their states only: never ``resolve_via``,
counts or ids (D32).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection
from tl_core.constraints.queries import ConstraintView, list_constraints
from tl_core.constraints.review import review_groups

from tl_mod_awp import iwp_views
from tl_mod_awp.names import (
    IWP_CANCELLED,
    IWP_CHECK,
    IWP_CLOSED,
    IWP_DEVELOPMENT,
    IWP_DRAFT,
    IWP_FIELD_COMPLETE,
    IWP_IN_PROGRESS,
    IWP_ISSUED,
    IWP_ON_HOLD,
    IWP_READY,
    IWP_SPLIT_STATE,
)
from tl_mod_awp.readiness import views as readiness_views
from tl_mod_awp.readiness.engine import PASSING
from tl_mod_awp.reports import NONE_TEXT, ZERO

IWP_REPORT_NAMES: Final = (
    "iwp_status",
    "iwp_readiness",
    "constraint_log",
    "constraints_by_category",
    "constraints_by_owner",
    "constraints_by_age",
)
#: The workflow order of the IWP states; any other state follows, by name.
IWP_STATE_ORDER: Final = (
    IWP_DRAFT,
    IWP_DEVELOPMENT,
    IWP_CHECK,
    IWP_READY,
    IWP_ISSUED,
    IWP_IN_PROGRESS,
    IWP_FIELD_COMPLETE,
    IWP_CLOSED,
    IWP_ON_HOLD,
    IWP_SPLIT_STATE,
    IWP_CANCELLED,
)
#: The IWP and constraint lists are read at this limit (the view clamps to 500).
LIST_LIMIT: Final = 500
NOT_EVALUATED: Final = "not evaluated"
#: The state text of the total row (last).
TOTAL_STATE: Final = "total"
READY_YES: Final = "yes"
READY_NO: Final = "no"
_NO_CHECKS: Final = NONE_TEXT


class IwpStatusRow(BaseModel):
    """One state and discipline of the IWPs, with their count and estimated hours."""

    state: str
    discipline: str
    count: int
    estimated_hours: Decimal


class IwpReadinessRow(BaseModel):
    """One IWP's last evaluation: ``ready`` yes, no or not evaluated; the checks by state."""

    number: str
    ready: str
    passing: str
    total: str
    blocked: str


class ConstraintLogRow(BaseModel):
    """One constraint a reader may see, by key."""

    key: str
    state: str
    category: str
    severity: str
    owner: str
    phase: str
    due: str
    age_days: int
    aging: bool


class GroupRow(BaseModel):
    """One group of constraints: its label, count, blocking count and aging count (no keys)."""

    label: str
    count: int
    blocking: int
    aging: int


def _state_key(state: str) -> tuple[int, str]:
    if state in IWP_STATE_ORDER:
        return (IWP_STATE_ORDER.index(state), "")
    return (len(IWP_STATE_ORDER), state)


def iwp_status(conn: Connection, scope: str) -> list[IwpStatusRow]:
    """The IWPs of ``scope`` by state (workflow order) and discipline, with a total row last."""
    count: dict[tuple[str, str], int] = defaultdict(int)
    hours: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    for iwp in iwp_views.iwp_list(conn, scope, limit=LIST_LIMIT):
        key = (iwp.state, iwp.discipline or NONE_TEXT)
        count[key] += 1
        hours[key] += iwp.estimated_hours or ZERO
    ordered = sorted(count, key=lambda k: (_state_key(k[0]), k[1] == NONE_TEXT, k[1]))
    rows = [
        IwpStatusRow(state=s, discipline=d, count=count[(s, d)], estimated_hours=hours[(s, d)])
        for s, d in ordered
    ]
    rows.append(
        IwpStatusRow(
            state=TOTAL_STATE,
            discipline=NONE_TEXT,
            count=sum(count.values()),
            estimated_hours=sum(hours.values(), ZERO),
        )
    )
    return rows


def iwp_readiness(conn: Connection, scope: str) -> list[IwpReadinessRow]:
    """Each visible IWP of ``scope`` in number order, with its last readiness evaluation."""
    rows: list[IwpReadinessRow] = []
    for iwp in sorted(iwp_views.iwp_list(conn, scope, limit=LIST_LIMIT), key=lambda v: v.number):
        evaluation = readiness_views.readiness(conn, scope, iwp.number)
        if evaluation is None:
            rows.append(
                IwpReadinessRow(
                    number=iwp.number,
                    ready=NOT_EVALUATED,
                    passing=NONE_TEXT,
                    total=NONE_TEXT,
                    blocked=NONE_TEXT,
                )
            )
            continue
        blocked = [c.name for c in evaluation.checks if c.state == "blocked"]
        rows.append(
            IwpReadinessRow(
                number=iwp.number,
                ready=READY_YES if evaluation.ready else READY_NO,
                passing=str(sum(1 for c in evaluation.checks if c.state in PASSING)),
                total=str(len(evaluation.checks)),
                blocked=", ".join(blocked) if blocked else NONE_TEXT,
            )
        )
    return rows


def _constraints(conn: Connection, scope: str) -> list[ConstraintView]:
    return list_constraints(conn, scope, limit=LIST_LIMIT)


def constraint_log(conn: Connection, scope: str) -> list[ConstraintLogRow]:
    """The constraints of ``scope`` the viewer may read, by key."""
    return [
        ConstraintLogRow(
            key=view.key,
            state=view.state,
            category=view.category,
            severity=view.severity,
            owner=view.owner or NONE_TEXT,
            phase=view.phase,
            due=view.due_at.split("T")[0] if view.due_at else NONE_TEXT,
            age_days=view.age_days,
            aging=view.aging,
        )
        for view in _constraints(conn, scope)
    ]


def constraint_groups_report(conn: Connection, scope: str, by: str) -> list[GroupRow]:
    """The constraints of ``scope`` grouped by ``by`` (``category``, ``owner`` or ``age``)."""
    return [
        GroupRow(label=group.label, count=group.count, blocking=group.blocking, aging=group.aging)
        for group in review_groups(_constraints(conn, scope), by)
    ]
