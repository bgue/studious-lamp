"""The work order backlog and the text of one work order, as pure functions (P2-I4A T07b; spec §8,
skill ``tui-layout``).

The values come from ``WorkOrderRow`` (``tl_mod_requisitions.api``) and ``WorkOrderDetailBody``
(``tl_api.routes.requisitions``) and nothing else: no client call, no I/O, and no ``textual``
import. Hours are shown with ``awp_text.hours_text`` and dates as they are (``—`` when unset). The
panel and the screen share ``wo_page``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from tl_tui.awp_text import date_text, hours_text
from tl_tui.details import TECHNICAL_SECTION, DetailRow, rows_page
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import Page, identity_line, join_facts, state_line
from tl_tui.text import EMPTY

if TYPE_CHECKING:
    from tl_api.routes.requisitions import WorkOrderDetailBody
    from tl_mod_requisitions.api import WorkOrderRow

WO_COLUMNS = ("Number", "Kind", "State", "Assigned", "Planned start", "Planned finish", "Hours")
WO_DROP = ("Hours", "Planned finish", "Assigned")  # dropped first at narrow width
WO_RIGHT = ("Hours",)

WORK = "Work"
DATES_AND_HOURS = "Dates and hours"
WORK_ORDERS = "work order"


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def _hours(value: str | None) -> Decimal | None:
    """The hours a work order carries as text (``"48"``); none when unset."""
    return None if not value else Decimal(value)


def _assigned(labels: Labels | None, assigned_to: str | None) -> str:
    return EMPTY if not assigned_to else actor_label(_labels(labels), assigned_to)


def wo_cells(row: WorkOrderRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The seven cells of a backlog row, in the order of ``WO_COLUMNS``. The kind and the state
    are humanized; Assigned is the actor's label; unset dates and hours are ``—``."""
    return (
        row.key,
        humanize(row.work_kind),
        humanize(row.state),
        _assigned(labels, row.assigned_to),
        date_text(row.planned_start),
        date_text(row.planned_finish),
        hours_text(_hours(row.hours_planned)),
    )


def wo_summary(
    total: int,
    shown: int,
    *,
    state: str | None = None,
    assigned_to: str | None = None,
) -> str:
    """``4 work orders``; with a filter, ``2 of 4 work orders, state Scheduled``."""
    noun = WORK_ORDERS if total == 1 else f"{WORK_ORDERS}s"
    if state is None and assigned_to is None:
        return f"{total} {noun}"
    parts = [f"{shown} of {total} {noun}"]
    if state is not None:
        parts.append(f"state {humanize(state)}")
    if assigned_to is not None:
        parts.append(f"assigned to {actor_label(Labels(), assigned_to)}")
    return ", ".join(parts)


def _window(start: str | None, finish: str | None) -> str:
    if start and finish:
        return f"{start} to {finish}"
    if start:
        return f"from {start}"
    return f"to {finish}" if finish else ""


def _summary(row: WorkOrderRow, labels: Labels | None) -> str:
    """``Labor · Uma · 2026-11-02 to 2026-11-13 · 48 h``; the facts that are absent are left out."""
    hours = _hours(row.hours_planned)
    return join_facts(
        humanize(row.work_kind),
        _assigned(labels, row.assigned_to) if row.assigned_to else "",
        _window(row.planned_start, row.planned_finish),
        f"{hours_text(hours)} h" if hours is not None else "",
    )


def wo_page(
    detail: WorkOrderDetailBody,
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """One work order as a page. The identity is ``<key> · <requisition key>``; the state line is
    the humanized state. Sections: Work (kind, assigned), Dates and hours (planned and actual
    dates, hours planned and actual). Technical: the id."""
    row = detail.row
    rows: list[DetailRow] = [
        DetailRow("Kind", humanize(row.work_kind), section=WORK),
        DetailRow("Assigned", _assigned(labels, row.assigned_to), section=WORK),
        DetailRow("Planned start", date_text(row.planned_start), section=DATES_AND_HOURS),
        DetailRow("Planned finish", date_text(row.planned_finish), section=DATES_AND_HOURS),
        DetailRow("Actual start", date_text(row.actual_start), section=DATES_AND_HOURS),
        DetailRow("Actual finish", date_text(row.actual_finish), section=DATES_AND_HOURS),
        DetailRow("Hours planned", hours_text(_hours(row.hours_planned)), section=DATES_AND_HOURS),
        DetailRow("Hours actual", hours_text(_hours(row.hours_actual)), section=DATES_AND_HOURS),
        DetailRow("Id", row.id, True, TECHNICAL_SECTION, False),
    ]
    return rows_page(
        rows,
        identity=identity_line(row.key, detail.requisition_key),
        state=state_line(humanize(row.state)),
        summary=_summary(row, labels),
        technical=technical,
        panel=panel,
    )
