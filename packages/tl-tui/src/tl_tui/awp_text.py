"""The text of the CWP register and of a CWP's panel and Details tab, as pure functions (P2-I1 T05a;
spec §8, skill ``tui-layout``).

The values come from ``tl_mod_awp.views`` and ``tl_api.routes.awp.CwpDetailView`` and nothing else:
no client call, no I/O, and no ``textual`` import, so the web client's CWP page (``tl_web``) can
use the same words. The Details tab and the panel share ``cwp_rows``; ``cwp_page`` is the panel's
page. Hours are shown in space-grouped digits (``4 200``); a figure the engine computed (the hours
of an allocation) is shown as it comes, rounded half-even to 0.01.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Any

from tl_tui.details import TECHNICAL_SECTION, DetailRow, rows_page, table_rows
from tl_tui.display import Labels, actor_label, humanize
from tl_tui.layout import Page, Section, identity_line, join_facts, limited, shown, state_line
from tl_tui.text import EMPTY

if TYPE_CHECKING:
    from tl_api.routes.awp import CwpDetailView
    from tl_mod_awp.views import CwpRow
    from tl_mod_schedule.resolver import ActivityLink

HOURS_UNIT = "h"
CWP_COLUMNS = (
    "Number",
    "Subject",
    "State",
    "Discipline",
    "CWA",
    "Planned start",
    "Budget h",
    "Allocated",
)
CWP_DROP = ("Planned start", "Discipline")  # dropped first at narrow width
CWP_RIGHT = ("Budget h",)

DISCIPLINE_LIST = "discipline"  # the code list the discipline codes are labelled from
CURRENT_STATES = ("current", "as_of")  # an activity resolution that is not stale
SCOPE = "Scope"
ALLOCATION = "Allocation"
REFERENCES = "References"
SCHEDULE = "Schedule"
TIMELINE = "Timeline"
FILES = "Files and links"
SCOPE_COLUMNS = ("Commodity", "Qty", "UOM")
ALLOCATION_COLUMNS = ("WBS node", "%", "Hours")
PACKAGE_COLUMNS = ("Package", "Type", "Status", "Forecast", "Constraint source")
SCHEDULE_COLUMNS = ("Activity", "Name", "Start", "Finish")
TIMELINE_COLUMNS = ("Date", "Who", "Event", "Note")
SCHEDULE_PANEL_LIMIT = 4  # rows of the Schedule table in a panel


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def hours_text(value: Decimal | None) -> str:
    """``4 200``, ``12.5`` (no trailing zeros), ``—`` for none. Digits are grouped by spaces."""
    if value is None:
        return EMPTY
    plain = format(Decimal(value).normalize(), "f")
    sign = ""
    if plain.startswith("-"):
        sign, plain = "-", plain[1:]
    whole, dot, fraction = plain.partition(".")
    return sign + f"{int(whole):,}".replace(",", " ") + (dot + fraction if dot else "")


def date_text(value: str | None) -> str:
    """``2026-11-03`` as it is; ``—`` for none."""
    return value if value else EMPTY


def _hours_with_unit(value: Decimal | None) -> str:
    return EMPTY if value is None else f"{hours_text(value)} {HOURS_UNIT}"


def _discipline(labels: Labels | None, code: str | None) -> str:
    """The discipline's label from the code list; a code with no label reads humanized."""
    if not code:
        return EMPTY
    return _labels(labels).code_labels.get(DISCIPLINE_LIST, {}).get(code) or humanize(code)


def _day(value: str | None) -> str:
    """The day of an ISO date-time (``2026-11-03T08:00:00``); ``—`` for none."""
    return EMPTY if not value else value[:10]


def cwp_cells(row: CwpRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a register row, in the order of ``CWP_COLUMNS``. Allocated is ``✓`` or
    ``—``; the state is humanized; the discipline is its label from the code list."""
    return (
        row.number,
        shown(row.title),
        humanize(row.state),
        _discipline(labels, row.discipline),
        shown(row.cwa),
        date_text(row.planned_start),
        hours_text(row.budget_hours),
        "✓" if row.allocated else EMPTY,
    )


def _window(start: str | None, finish: str | None) -> str:
    if start and finish:
        return f"{start} to {finish}"
    if start:
        return f"from {start}"
    return f"to {finish}" if finish else ""


def _summary(d: CwpDetailView, labels: Labels | None) -> str:
    """``Piping · CWA 12 · 2026-11-03 to 2027-01-29 · 4 200 h``; the facts that are absent are
    left out."""
    return join_facts(
        _discipline(labels, d.discipline) if d.discipline else "",
        f"CWA {d.cwa}" if d.cwa else "",
        _window(d.planned_start, d.planned_finish),
        _hours_with_unit(d.budget_hours) if d.budget_hours is not None else "",
    )


def cwp_summary(d: CwpDetailView) -> str:
    """The panel's summary line: the discipline, the CWA, the planned window and the budget."""
    return _summary(d, None)


def _quantities(value: Any) -> list[dict[str, Any]]:
    """The quantities of a CWP: a list of ``{commodity, qty, uom}`` mappings; anything else is
    none."""
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _share(budget: Decimal | None, percent: Decimal) -> Decimal | None:
    """The hours an allocation takes: budget times percent over 100, half-even to 0.01."""
    if budget is None:
        return None
    return (budget * percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _activity_cells(link: ActivityLink) -> tuple[str, ...]:
    resolution = link.resolution
    activity = resolution.activity
    stale = link.status == "stale" or resolution.state not in CURRENT_STATES
    number = resolution.activity_id + ("!" if stale else "")
    if activity is None:
        return (number, EMPTY, EMPTY, EMPTY)
    return (
        number,
        shown(activity.name),
        _day(activity.early_start),
        _day(activity.early_finish),
    )


def cwp_rows(d: CwpDetailView, labels: Labels | None = None) -> list[DetailRow]:
    """The CWP's facts as Details rows, in sections: Scope, Allocation, References, Schedule,
    Timeline, Files and links, then the technical rows (id and key; technical mode only)."""
    lab = _labels(labels)
    rows: list[DetailRow] = [
        DetailRow("Budget hours", _hours_with_unit(d.budget_hours), section=SCOPE),
        DetailRow("Contractor", shown(d.contractor_text), section=SCOPE),
    ]
    rows += table_rows(
        SCOPE,
        SCOPE_COLUMNS,
        [
            (shown(q.get("commodity")), shown(q.get("qty")), shown(q.get("uom")))
            for q in _quantities(d.quantities)
        ],
    )
    if d.allocations:
        rows += table_rows(
            ALLOCATION,
            ALLOCATION_COLUMNS,
            [
                (
                    allocation.wbs_code,
                    f"{hours_text(allocation.percent)}%",
                    hours_text(_share(d.budget_hours, allocation.percent)),
                )
                for allocation in d.allocations
            ],
        )
    else:
        rows.append(DetailRow("", "Not allocated", section=ALLOCATION))
    if d.packages:
        rows += table_rows(
            REFERENCES,
            PACKAGE_COLUMNS,
            [
                (
                    package.package_no,
                    package.kind,
                    shown(package.status_text),
                    date_text(package.forecast_date),
                    "Yes" if package.constraint_source else "No",
                )
                for package in d.packages
            ],
        )
    else:
        rows.append(DetailRow("", "No packages linked", section=REFERENCES))
    if d.activities:
        rows += table_rows(
            SCHEDULE, SCHEDULE_COLUMNS, [_activity_cells(link) for link in d.activities]
        )
    else:
        rows.append(DetailRow("", "No activities linked", section=SCHEDULE))
    if d.timeline:
        rows += table_rows(
            TIMELINE,
            TIMELINE_COLUMNS,
            [
                (event.date, actor_label(lab, event.who), humanize(event.event), shown(event.note))
                for event in sorted(d.timeline, key=lambda event: event.date)
            ],
        )
    else:
        rows.append(DetailRow("", "No events recorded", section=TIMELINE))
    rows += [
        DetailRow("Files", str(d.file_count), section=FILES),
        DetailRow("Links", str(d.link_count), section=FILES),
        DetailRow("Id", d.id, True, TECHNICAL_SECTION, False),
        DetailRow("Key", d.number, True, TECHNICAL_SECTION, False),
    ]
    return rows


def _cut_schedule(section: Section) -> Section:
    if section.heading != SCHEDULE:
        return section
    return Section(section.heading, limited(section.items, SCHEDULE_PANEL_LIMIT), section.note)


def cwp_page(
    d: CwpDetailView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The CWP as a page: the identity and state lines, then the sections of ``cwp_rows``. A
    panel adds the summary line and cuts the Schedule table to its first rows (the Timeline is
    cut by ``rows_page``)."""
    page = rows_page(
        cwp_rows(d, labels),
        identity=identity_line(d.number, d.title),
        state=state_line(humanize(d.state)),
        summary=_summary(d, labels),
        technical=technical,
        panel=panel,
    )
    if panel:
        page = replace(page, sections=tuple(_cut_schedule(s) for s in page.sections))
    return page


def group_by_cwa(rows: Sequence[CwpRow]) -> list[tuple[str, tuple[CwpRow, ...]]]:
    """The register grouped by CWA code (``c``): the groups in code order with ``—`` last; the
    rows of a group keep their number order."""
    groups: dict[str, list[CwpRow]] = {}
    for row in sorted(rows, key=lambda row: row.number):
        groups.setdefault(row.cwa or EMPTY, []).append(row)
    codes = sorted(groups, key=lambda code: (code == EMPTY, code))
    return [(code, tuple(groups[code])) for code in codes]
