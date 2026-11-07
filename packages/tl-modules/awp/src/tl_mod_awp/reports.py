"""The three awp reports (spec m3-wbs-cwp section 5): functions over the views, never over tables.

Each takes a connection and a project scope and reads through ``tl_mod_awp.views``, so the viewer's
class filter (ADR-0016) applies to every figure. The cost system's hours are passed in by the caller
as ``cost`` (this module does not depend on the cost module). ``to_csv`` renders any report's rows.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_awp import views
from tl_mod_awp.names import ST_DEVELOPMENT, ST_PLANNED, ST_RELEASED

REPORT_NAMES: Final = ("cwp_status", "wbs_vs_cost_code", "cwa_sequence")
#: The workflow order of the states; any other state follows, by name.
STATE_ORDER: Final = (ST_PLANNED, ST_DEVELOPMENT, ST_RELEASED)
#: Shown where a value is not known or does not apply (a discipline, a name, a cost figure).
NONE_TEXT: Final = "-"
#: Shown where the cost system stated no hours for a code.
UNSTATED: Final = "—"
UNALLOCATED: Final = "Unallocated"
TOTAL: Final = "Total"
ZERO: Final = Decimal("0")
ONE_DP: Final = Decimal("0.1")


class CostFigure(BaseModel):
    """A cost code's title and the budget hours the cost system states for it (None: not stated)."""

    title: str
    hours_budget: Decimal | None


class StatusRow(BaseModel):
    """One state and discipline of the CWPs, with their count and budget hours."""

    state: str
    discipline: str
    count: int
    budget_hours: Decimal


class CostRow(BaseModel):
    """One cost code: the awp budget against the cost system's (None: not stated, no difference)."""

    code: str
    name: str
    awp_budget_hours: Decimal
    cost_budget_hours: Decimal | None
    difference: Decimal | None


class SequenceRow(BaseModel):
    """One step of the path of construction, with the CWPs under its area and their budget hours."""

    position: int
    cwa: str
    cwa_title: str
    cwps: int
    budget_hours: Decimal


def format_value(value: object) -> str:
    """One value as a report shows it: ``—`` for None, a Decimal to one decimal place."""
    if value is None:
        return UNSTATED
    if isinstance(value, Decimal):
        return str(value.quantize(ONE_DP, rounding=ROUND_HALF_UP))
    return str(value)


def _state_key(state: str) -> tuple[int, str]:
    if state in STATE_ORDER:
        return (STATE_ORDER.index(state), "")
    return (len(STATE_ORDER), state)


def cwp_status(conn: Connection, scope: str) -> list[StatusRow]:
    """The CWPs of ``scope`` by state (workflow order) and discipline, with a total row last."""
    count: dict[tuple[str, str], int] = defaultdict(int)
    hours: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    for cwp in views.cwp_list(conn, scope):
        key = (cwp.state, cwp.discipline or NONE_TEXT)
        count[key] += 1
        hours[key] += cwp.budget_hours or ZERO
    ordered = sorted(count, key=lambda k: (_state_key(k[0]), k[1] == NONE_TEXT, k[1]))
    rows = [
        StatusRow(state=s, discipline=d, count=count[(s, d)], budget_hours=hours[(s, d)])
        for s, d in ordered
    ]
    rows.append(
        StatusRow(
            state=TOTAL,
            discipline=NONE_TEXT,
            count=sum(count.values()),
            budget_hours=sum(hours.values(), ZERO),
        )
    )
    return rows


def wbs_vs_cost_code(conn: Connection, scope: str, cost: Mapping[str, CostFigure]) -> list[CostRow]:
    """The awp budget per cost code against the cost system's, by code, then the Unallocated row.

    The awp budget of a code is the sum of ``by_cost_code`` over the root nodes (no parent); the
    Unallocated budget is the roots' totals less all their ``by_cost_code``. A cost code is listed
    when the awp or the cost system names it; a difference is awp budget minus cost-system budget.
    """
    roots = [node for node in views.wbs_tree(conn, scope) if node.parent_code is None]
    awp: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for node in roots:
        for code, hours in node.by_cost_code.items():
            awp[code] += hours
    total = sum((node.total_hours or ZERO for node in roots), ZERO)
    rows: list[CostRow] = []
    for code in sorted(set(awp) | set(cost)):
        figure = cost.get(code)
        cost_hours = None if figure is None else figure.hours_budget
        rows.append(
            CostRow(
                code=code,
                name=NONE_TEXT if figure is None else figure.title,
                awp_budget_hours=awp.get(code, ZERO),
                cost_budget_hours=cost_hours,
                difference=None if cost_hours is None else awp.get(code, ZERO) - cost_hours,
            )
        )
    rows.append(
        CostRow(
            code=UNALLOCATED,
            name=NONE_TEXT,
            awp_budget_hours=total - sum(awp.values(), ZERO),
            cost_budget_hours=None,
            difference=None,
        )
    )
    return rows


def cwa_sequence(conn: Connection, scope: str) -> list[SequenceRow]:
    """The current path of construction: one row per step, with the CWPs of its area and their
    budget hours. A step whose area the viewer may not read is shown with ``-``. No path: ``[]``."""
    path = views.path(conn, scope)
    if path is None:
        return []
    titles = {area.code: area.title for area in views.cwa_list(conn, scope)}
    count: dict[str, int] = defaultdict(int)
    hours: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for cwp in views.cwp_list(conn, scope):
        if cwp.cwa is not None:
            count[cwp.cwa] += 1
            hours[cwp.cwa] += cwp.budget_hours or ZERO
    rows: list[SequenceRow] = []
    for step in path.steps:
        if step.cwa is None:
            rows.append(
                SequenceRow(
                    position=step.position,
                    cwa=NONE_TEXT,
                    cwa_title=NONE_TEXT,
                    cwps=0,
                    budget_hours=ZERO,
                )
            )
            continue
        rows.append(
            SequenceRow(
                position=step.position,
                cwa=step.cwa,
                cwa_title=titles.get(step.cwa, NONE_TEXT),
                cwps=count[step.cwa],
                budget_hours=hours[step.cwa],
            )
        )
    return rows


def to_csv(rows: Sequence[BaseModel]) -> str:
    """The rows as CSV: a header of the field names, then one line per row, ``\\n`` line ends.
    Decimals are one-decimal text and None is ``—``. No rows gives ``""`` (no names to show)."""
    if not rows:
        return ""
    names = list(type(rows[0]).model_fields)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(names)
    for row in rows:
        writer.writerow([format_value(getattr(row, name)) for name in names])
    return buffer.getvalue()
