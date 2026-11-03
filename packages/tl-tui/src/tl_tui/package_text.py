"""The external packages log: the EWPs and PWPs a project keeps, as pure functions (P2-I1 T05f;
spec §8 "External packages", skill ``tui-layout``).

The values come from ``tl_mod_awp.views.PackageRow`` and nothing else: no client call, no I/O,
and no ``textual`` import, so the web client can use the same words. This is the project's
package log, not the package table inside a CWP page (``awp_text.PACKAGE_COLUMNS``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tl_tui.details import TECHNICAL_SECTION, DetailRow, rows_page
from tl_tui.layout import Page, identity_line, join_facts, shown, state_line
from tl_tui.text import EMPTY

if TYPE_CHECKING:
    from tl_mod_awp.views import PackageRow

PACKAGE_COLUMNS = (
    "Number",
    "Subject",
    "Type",
    "Status",
    "Forecast",
    "Actual",
    "Constraint source",
    "CWPs",
)
TYPES: tuple[str | None, ...] = (None, "EWP", "PWP")  # the ``t`` key cycles through these
DATES = "Dates"
SOURCE = "Source"
CWPS = "CWPs"
NO_CWPS = "No CWPs require it"


def _date(value: str | None) -> str:
    """``2026-11-20`` as it is; ``—`` for none."""
    return value if value else EMPTY


def next_type(kind: str | None) -> str | None:
    """The type the ``t`` key shows next: all, then EWP, then PWP, then all again."""
    return TYPES[(TYPES.index(kind) + 1) % len(TYPES)]


def package_cells(row: PackageRow) -> tuple[str, ...]:
    """The eight cells of a log row, in the order of ``PACKAGE_COLUMNS``. The constraint source
    reads ``Yes`` or ``—``; the CWPs cell is the count of CWPs that require the package."""
    return (
        row.package_no,
        shown(row.title),
        row.kind,
        shown(row.status_text),
        _date(row.forecast_date),
        _date(row.actual_date),
        "Yes" if row.constraint_source else EMPTY,
        str(len(row.cwps)),
    )


def package_summary(row: PackageRow) -> str:
    """``EWP · forecast 2026-11-20 · required by 3 CWPs``; the facts that are absent are left
    out."""
    count = len(row.cwps)
    required = ""
    if count:
        required = f"required by {count} CWP" + ("" if count == 1 else "s")
    return join_facts(
        row.kind,
        f"forecast {row.forecast_date}" if row.forecast_date else "",
        required,
    )


def package_page(row: PackageRow, *, panel: bool = False, technical: bool = False) -> Page:
    """The package as a page: the identity and status lines, then the Dates, Source and CWPs
    sections. A panel adds the summary line; technical mode adds the record id."""
    heading = f"{CWPS} ({len(row.cwps)})" if row.cwps else CWPS
    rows: list[DetailRow] = [
        DetailRow("Forecast", _date(row.forecast_date), section=DATES),
        DetailRow("Actual", _date(row.actual_date), section=DATES),
        DetailRow("Source system", shown(row.source_system), section=SOURCE),
    ]
    if row.cwps:
        rows += [DetailRow("", number, section=heading) for number in row.cwps]
    else:
        rows.append(DetailRow("", NO_CWPS, section=heading))
    rows.append(DetailRow("Id", row.id, True, TECHNICAL_SECTION, False))
    return rows_page(
        rows,
        identity=identity_line(row.package_no, row.title),
        state=state_line(shown(row.status_text)),
        summary=package_summary(row),
        technical=technical,
        panel=panel,
    )


def summary_line(
    shown_rows: int,
    total: int,
    *,
    kind: str | None,
    constraints_only: bool,
    text: str,
) -> str:
    """The count line under the log: ``12 packages``, or ``3 of 12 packages`` with the filters
    named (``EWP  constraint sources only  filter "tray"``)."""
    stripped = text.strip()
    filtered = kind is not None or constraints_only or bool(stripped)
    head = f"{shown_rows} of {total} packages" if filtered else f"{shown_rows} packages"
    parts = [head]
    if kind is not None:
        parts.append(kind)
    if constraints_only:
        parts.append("constraint sources only")
    if stripped:
        parts.append(f'filter "{stripped}"')
    return "  ".join(parts)
