"""The text of the IWP log and of an IWP's screen, as pure functions (P2-I2 T07b; spec §8, skill
``tui-layout``).

The values come from ``tl_mod_awp.iwp_views`` (``IwpRow``, ``IwpDetail``, ``ScopeRow``) and nothing
else: no client call, no I/O, and no ``textual`` import, so the web client can use the same words.
Hours and dates are formatted by ``tl_tui.awp_text`` (``hours_text``, ``date_text``); this module
does not copy them. The log has no Ready or Constraints column and the IWP page has no Readiness
or Constraints tab (D33): ``IwpRow`` carries neither, and a read per row is not allowed. The
constraint count on the page is the detail's ``open_constraints``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from tl_tui.awp_text import DISCIPLINE_LIST, date_text, hours_text
from tl_tui.display import Labels, actor_label, humanize, type_label
from tl_tui.layout import (
    EMPTY,
    Item,
    Page,
    Section,
    TableRow,
    identity_line,
    join_facts,
    limited,
    prop,
    shown,
    state_line,
)

if TYPE_CHECKING:
    from tl_mod_awp.iwp_views import IwpDetail, IwpRow, ScopeRow

IWP_COLUMNS = (
    "Number",
    "Subject",
    "State",
    "Discipline",
    "Foreman",
    "Planned start",
    "Scope",
    "Hours",
)
IWP_DROP = ("Planned start", "Foreman", "Discipline")  # dropped first at narrow width
IWP_RIGHT = ("Scope", "Hours")

SCOPE = "Scope"
SIGNOFFS = "Sign-offs"
DRAWINGS = "Drawings"
CONSTRAINTS = "Constraints"
SCOPE_ROW_COLUMNS = ("Number", "Type", "Commodity", "Description", "Qty")
SIGNOFF_COLUMNS = ("Who", "Role", "When")
PANEL_SCOPE_ROWS = 10  # scope rows in a panel; the page shows 50
PAGE_SCOPE_ROWS = 50
IWP_NOUN = "IWP"


def _labels(labels: Labels | None) -> Labels:
    return Labels() if labels is None else labels


def _discipline(labels: Labels | None, code: str | None) -> str:
    """The discipline's label from the code list; a code with no label reads humanized."""
    if not code:
        return EMPTY
    return _labels(labels).code_labels.get(DISCIPLINE_LIST, {}).get(code) or humanize(code)


def _count(n: int) -> str:
    return f"{n} {IWP_NOUN}" if n == 1 else f"{n} {IWP_NOUN}s"


def _span(start: str | None, finish: str | None) -> str:
    """``2026-12-01 to 2026-12-15``; a single side when only one is set, ``""`` for neither."""
    if start and finish:
        return f"{start} to {finish}"
    if start:
        return f"from {start}"
    return f"to {finish}" if finish else ""


def iwp_cells(row: IwpRow, labels: Labels | None = None) -> tuple[str, ...]:
    """The eight cells of a log row, in the order of ``IWP_COLUMNS``. The state is humanized, the
    discipline is its label from the code list, the foreman is a name, the hours are
    ``hours_text`` (``—`` for none)."""
    return (
        row.number,
        shown(row.title),
        humanize(row.state),
        _discipline(labels, row.discipline),
        actor_label(_labels(labels), row.foreman) if row.foreman else EMPTY,
        date_text(row.planned_start),
        str(row.scope_count),
        hours_text(row.estimated_hours),
    )


def iwp_summary(
    total: int, shown: int, *, state: str | None = None, foreman: str | None = None
) -> str:
    """``7 IWPs``; with a filter ``3 of 7 IWPs, state Ready`` (the foreman is named by name)."""
    if state is None and foreman is None:
        return _count(total)
    named: list[str] = []
    if state is not None:
        named.append(f"state {humanize(state)}")
    if foreman is not None:
        named.append(f"foreman {actor_label(Labels(), foreman)}")
    return ", ".join([f"{shown} of {_count(total)}", *named])


def _scope_items(
    detail: IwpDetail, scope_rows: Sequence[ScopeRow], labels: Labels, cap: int
) -> tuple[Item, ...]:
    """The counts by record type (one property line each), then the scope rows up to ``cap``."""
    counts: list[Item] = [
        prop(type_label(labels, kind), str(count))
        for kind, count in sorted(detail.scope_by_type.items())
    ]
    rows: list[Item] = [
        TableRow(
            SCOPE_ROW_COLUMNS,
            (
                shown(row.number),
                type_label(labels, row.type),
                shown(row.commodity),
                shown(row.description),
                hours_text(row.qty),
            ),
        )
        for row in scope_rows
    ]
    return (*counts, *limited(rows, cap))


def _signoff_items(
    signoffs: Sequence[dict[str, Any]], labels: Labels, technical: bool
) -> tuple[Item, ...]:
    """Who signed, the role and the day (``YYYY-MM-DD``); the record hash is never shown."""
    items: list[Item] = []
    for entry in signoffs:
        by = entry.get("by")
        who = EMPTY if not by else (str(by) if technical else actor_label(labels, str(by)))
        role = entry.get("role")
        items.append(
            TableRow(
                SIGNOFF_COLUMNS,
                (who, humanize(str(role)) if role else EMPTY, _day(entry.get("at"))),
            )
        )
    return tuple(items)


def _day(value: object) -> str:
    """The day of an ISO date-time (``2026-11-03T08:00:00+00:00``); ``—`` for none."""
    return EMPTY if not value else str(value)[:10]


def iwp_page(
    detail: IwpDetail,
    scope_rows: Sequence[ScopeRow],
    labels: Labels | None = None,
    technical: bool = False,
    panel: bool = False,
) -> Page:
    """The IWP as a page: the identity and state lines, the summary line, then the sections Scope
    (by type, then up to 10 rows when a panel, else 50), Sign-offs (who, when), Drawings
    (``<n> pinned``) and Constraints (``<n> open``). ``technical`` shows a sign-off's actor by its
    id; the record hash is never shown."""
    lab = _labels(labels)
    cap = PANEL_SCOPE_ROWS if panel else PAGE_SCOPE_ROWS
    scope = _scope_items(detail, scope_rows, lab, cap)
    signoffs = _signoff_items(detail.signoffs, lab, technical)
    summary = join_facts(
        _discipline(lab, detail.discipline) if detail.discipline else "",
        f"crew {detail.crew_text}" if detail.crew_text else "",
        _span(detail.planned_start, detail.planned_finish),
        f"{hours_text(detail.estimated_hours)} h" if detail.estimated_hours is not None else "",
    )
    return Page(
        identity=identity_line(detail.number, detail.title),
        state=state_line(humanize(detail.state)),
        summary=summary,
        sections=(
            Section(SCOPE, scope, note="No scope"),
            Section(SIGNOFFS, signoffs, note="No sign-offs"),
            Section(DRAWINGS, (f"{detail.pin_count} pinned",)),
            Section(CONSTRAINTS, (f"{detail.open_constraints} open",)),
        ),
    )
