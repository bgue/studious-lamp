"""The backlog tile: backlog weeks per foreman, and the sizing list (P2-I2 T08; spec §8, skill
``tui-layout``; definitions D34).

The values come from ``IwpRow`` rows (``tl_mod_awp.iwp_views``) and the two settings the screen
reads once per load, and nothing else: no client call, no I/O, and no ``textual`` import, so TW3
can reuse the same words. Nothing is refused here; the tile is a view.

Backlog: the IWPs in state ``Ready`` or ``Issued`` of a foreman (``-`` for none). An IWP's weeks
are ``ceil(((planned_finish - planned_start).days + 1) / 7)``, at least 1; an IWP without both
dates adds 0 weeks and counts as undated. A foreman is below target when its weeks are fewer than
``awp.backlog.target_weeks``.

Sizing: an IWP whose estimated hours are outside ``awp.iwp.size_hours`` (``[low, high]``) is
flagged ``oversize`` or ``undersize``; shown as ``over size`` and ``under size``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from tl_mod_awp.iwp_views import IwpRow

from tl_tui.awp_text import hours_text
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import shown
from tl_tui.text import EMPTY

if TYPE_CHECKING:
    from collections.abc import Iterable

BACKLOG_COLUMNS = ("Foreman", "IWPs", "Weeks", "Target", "Status", "Undated")
SIZING_COLUMNS = ("Number", "Subject", "State", "Hours", "Bounds", "Flag")
BACKLOG_TITLE = "Backlog weeks per foreman"
SIZING_TITLE = "IWP sizing"
NO_FOREMAN = "-"
COUNTED_STATES = ("Ready", "Issued")
FLAG_WORDS = {"oversize": "over size", "undersize": "under size"}


@dataclass(frozen=True)
class BacklogRow:
    """One foreman's backlog: the counted IWPs, their weeks, and how many have no dates."""

    foreman: str | None  # None is the ``-`` row: no foreman
    iwps: int
    weeks: int
    undated: int
    target: int

    @property
    def status(self) -> str:
        return "below target" if self.weeks < self.target else "at or above target"


class SizedIwpRow(IwpRow):
    """A flagged IWP: the row, its flag (``oversize`` or ``undersize``) and the bounds it failed."""

    flag: str = ""
    low: Decimal | None = None
    high: Decimal | None = None


def _dated(row: IwpRow) -> bool:
    return bool(row.planned_start and row.planned_finish)


def iwp_weeks(planned_start: str | None, planned_finish: str | None) -> int:
    """The weeks an IWP takes, counting both ends: 0 when a date is missing, else at least 1."""
    if not planned_start or not planned_finish:
        return 0
    start = date.fromisoformat(planned_start[:10])
    finish = date.fromisoformat(planned_finish[:10])
    days = (finish - start).days + 1
    return max(1, math.ceil(days / 7))


def _foreman_order(row: BacklogRow) -> tuple[bool, str]:
    """By name, the ``-`` row last."""
    if row.foreman is None:
        return (True, "")
    return (False, actor_label(Labels(), row.foreman))


def backlog_rows(rows: Iterable[IwpRow], target_weeks: int) -> list[BacklogRow]:
    """One row per foreman with a counted IWP, by name, the ``-`` row last. Draft and other
    states are not counted."""
    groups: dict[str | None, list[IwpRow]] = {}
    for row in rows:
        if row.state in COUNTED_STATES:
            groups.setdefault(row.foreman, []).append(row)
    found = [
        BacklogRow(
            foreman=foreman,
            iwps=len(group),
            weeks=sum(iwp_weeks(r.planned_start, r.planned_finish) for r in group),
            undated=sum(1 for r in group if not _dated(r)),
            target=target_weeks,
        )
        for foreman, group in groups.items()
    ]
    return sorted(found, key=_foreman_order)


def size_flag(hours: Decimal | None, low: Decimal, high: Decimal) -> str:
    """``""`` when the hours are unset or inside ``[low, high]``; ``oversize`` above it;
    ``undersize`` below it."""
    if hours is None:
        return ""
    if hours > high:
        return "oversize"
    if hours < low:
        return "undersize"
    return ""


def sizing_rows(rows: Iterable[IwpRow], low: Decimal, high: Decimal) -> list[SizedIwpRow]:
    """The flagged IWPs only, by number."""
    flagged: list[SizedIwpRow] = []
    for row in rows:
        flag = size_flag(row.estimated_hours, low, high)
        if flag:
            flagged.append(SizedIwpRow(**row.model_dump(), flag=flag, low=low, high=high))
    return sorted(flagged, key=lambda r: r.number)


def backlog_cells(row: BacklogRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The cells of a backlog row, in the order of ``BACKLOG_COLUMNS``."""
    foreman = NO_FOREMAN if row.foreman is None else actor_label(labels or Labels(), row.foreman)
    return (
        foreman,
        str(row.iwps),
        str(row.weeks),
        str(row.target),
        row.status,
        str(row.undated),
    )


def sizing_cells(row: SizedIwpRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The cells of a flagged IWP, in the order of ``SIZING_COLUMNS``. The bounds are the ones the
    row failed; a row with no bounds reads ``—``."""
    del labels  # a sizing row has no name to label
    bounds = (
        EMPTY
        if row.low is None or row.high is None
        else f"{hours_text(row.low)}–{hours_text(row.high)}"
    )
    return (
        row.number,
        shown(row.title),
        humanize(row.state),
        hours_text(row.estimated_hours),
        bounds,
        FLAG_WORDS.get(row.flag, EMPTY),
    )


def backlog_summary(rows: Iterable[IwpRow], target_weeks: int) -> str:
    """``3 foremen, 2 below the 4-week target``: the rows of ``backlog_rows``, the ``-`` row
    included."""
    found = backlog_rows(rows, target_weeks)
    below = sum(1 for row in found if row.weeks < target_weeks)
    noun = "foreman" if len(found) == 1 else "foremen"
    return f"{len(found)} {noun}, {below} below the {target_weeks}-week target"


def sizing_summary(rows: Iterable[IwpRow], low: Decimal, high: Decimal) -> str:
    """``2 IWPs outside 60–850 h``: the flagged IWPs of ``sizing_rows``."""
    count = len(sizing_rows(rows, low, high))
    noun = "IWP" if count == 1 else "IWPs"
    return f"{count} {noun} outside {hours_text(low)}–{hours_text(high)} h"


def backlog_panel(rows: Sequence[IwpRow], target_weeks: int) -> str:
    """The heading and the summary of the backlog, as the panel shows them."""
    return f"{BACKLOG_TITLE}\n{backlog_summary(rows, target_weeks)}"


def sizing_panel(rows: Sequence[IwpRow], low: Decimal, high: Decimal) -> str:
    """The heading and the summary of the sizing list, as the panel shows them."""
    return f"{SIZING_TITLE}\n{sizing_summary(rows, low, high)}"
