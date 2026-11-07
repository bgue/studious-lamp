"""Six read-only reports of the materials module, built from its views (P2-I3-T05a).

A report holds no SQL and no schema of its own: each one is the rows a view returns, summed or
joined in Python. ``build_report`` is the one entry point; ``tl mat report``, the API route and
the web twins call it with the same arguments. The views filter every read by the caller's
clearance (ADR-0016), so a report never widens what a reader may see.

Every cell is text. A quantity is ``format(Decimal, "f")`` (no exponent); an empty cell is ``""``.
``to_csv`` writes the report with every cell through ``safe_cell``, so a spreadsheet does not run
a cell as a formula.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_materials import views
from tl_mod_materials.common import ZERO
from tl_mod_materials.errors import ReceiptNotFoundError
from tl_mod_materials.limits import MAX_VIEW_ROWS

REPORT_NAMES: Final = (
    "stock_on_hand",
    "movement_log",
    "mto_status",
    "shortages",
    "heat_trace",
    "consumables_by_cost_code",
)

#: The formula rule of the correspondence export (``export.safe_cell``); copied, not imported.
_FORMULA_STARTS: Final = ("=", "+", "-", "@", "|", "\t", "\r")
_NUMBER: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")


class Report(BaseModel):
    """One report: its columns, its rows of text cells, and whether a view hit its bound."""

    name: str
    columns: list[str]
    rows: list[list[str]]
    truncated: bool  # a view returned MAX_VIEW_ROWS rows, so the report may be cut short


@dataclass(frozen=True)
class _Filters:
    since: str | None
    until: str | None
    heat: str | None
    cost_codes: Mapping[str, str] | None


_Rows = tuple[list[list[str]], bool]
_Builder = Callable[[Connection, str, _Filters], _Rows]

_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "stock_on_hand": (
        "Lot",
        "Heat",
        "Item",
        "Description",
        "Location",
        "On hand",
        "Reserved",
        "Available",
        "UOM",
    ),
    "movement_log": (
        "Date",
        "Kind",
        "Lot",
        "Item",
        "Qty",
        "UOM",
        "From",
        "To",
        "By",
        "Reason",
    ),
    "mto_status": ("Work package", "Item", "UOM", "Required", "Received", "Reserved", "Issued"),
    "shortages": (
        "Work package",
        "Line",
        "Item",
        "UOM",
        "Required",
        "Reserved",
        "Issued",
        "Short",
    ),
    "heat_trace": ("Heat", "Lot", "Receipt", "MTR file", "Event", "Date", "Location", "Qty"),
    "consumables_by_cost_code": ("Cost code", "Item", "UOM", "Qty issued"),
}


def safe_cell(value: str | None) -> str:
    """``value`` as a spreadsheet cell: a text that starts like a formula gets a leading quote.
    A plain number is left as it is (``-3`` is a number, not a formula)."""
    text = "" if value is None else value
    if _NUMBER.fullmatch(text):
        return text
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def _qty(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _day(recorded_at: str) -> str:
    return recorded_at[:10]


def _full(found: Sequence[object]) -> bool:
    return len(found) >= MAX_VIEW_ROWS


def _stock_on_hand(conn: Connection, scope: str, _: _Filters) -> _Rows:
    found = views.stock(conn, scope, limit=MAX_VIEW_ROWS)
    rows = [
        [
            s.lot,
            s.heat_no or "",
            s.item_code,
            s.item_title,
            s.location,
            _qty(s.on_hand),
            _qty(s.reserved),
            _qty(s.available),
            s.uom,
        ]
        for s in found
    ]
    return rows, _full(found)


def _movement_log(conn: Connection, scope: str, f: _Filters) -> _Rows:
    found = views.movements(conn, scope, since=f.since, until=f.until, limit=MAX_VIEW_ROWS)
    rows = [
        [
            _day(m.recorded_at),
            m.kind,
            m.lot,
            m.item_code,
            _qty(m.qty),
            m.uom,
            m.from_location or "",
            m.to_location or "",
            m.actor,
            m.reason or "",
        ]
        for m in found
    ]
    return rows, _full(found)


def _mto_status(conn: Connection, scope: str, _: _Filters) -> _Rows:
    lines = views.mto_lines(conn, scope, limit=MAX_VIEW_ROWS)
    pos = views.po_lines(conn, scope, limit=MAX_VIEW_ROWS)
    received: dict[str, Decimal] = {}
    for po in pos:
        received[po.item_code] = received.get(po.item_code, ZERO) + po.qty_received
    sums: dict[tuple[str, str], tuple[str, Decimal, Decimal, Decimal]] = {}
    for line in lines:
        key = (line.work_package or "", line.item_code)
        uom, required, reserved, issued = sums.get(key, (line.uom, ZERO, ZERO, ZERO))
        sums[key] = (
            uom,
            required + line.required,
            reserved + line.reserved,
            issued + line.issued,
        )
    rows = [
        [
            work_package,
            item,
            uom,
            _qty(required),
            _qty(received.get(item, ZERO)),
            _qty(reserved),
            _qty(issued),
        ]
        for (work_package, item), (uom, required, reserved, issued) in sums.items()
    ]
    return rows, _full(lines) or _full(pos)


def _shortages(conn: Connection, scope: str, _: _Filters) -> _Rows:
    found = views.mto_lines(conn, scope, short_only=True, limit=MAX_VIEW_ROWS)
    rows = [
        [
            line.work_package or "",
            line.key,
            line.item_code,
            line.uom,
            _qty(line.required),
            _qty(line.reserved),
            _qty(line.issued),
            _qty(line.short),
        ]
        for line in found
    ]
    return rows, _full(found)


def _mtr_file(conn: Connection, scope: str, receipt: str | None) -> str:
    """The filename of the receipt's MTR file (the last one in the view's order), else ``""``."""
    if receipt is None:
        return ""
    try:
        detail = views.receipt_detail(conn, scope, receipt)
    except ReceiptNotFoundError:
        return ""
    names = [f.filename for f in detail.files if f.slot == views.MTR_SLOT]
    return names[-1] if names else ""


def _heat_trace(conn: Connection, scope: str, f: _Filters) -> _Rows:
    balances = views.stock(conn, scope, heat=f.heat, limit=MAX_VIEW_ROWS)
    truncated = _full(balances)
    by_lot: dict[str, list[views.StockRowView]] = {}
    for balance in balances:
        by_lot.setdefault(balance.lot, []).append(balance)
    rows: list[list[str]] = []
    for lot, lot_rows in by_lot.items():
        heat_no = lot_rows[0].heat_no or ""
        detail = views.lot_detail(conn, scope, lot)
        receipt = detail.receipt or ""
        mtr = _mtr_file(conn, scope, detail.receipt)
        for balance in lot_rows:
            rows.append(
                [
                    heat_no,
                    lot,
                    receipt,
                    mtr,
                    "On hand",
                    "",
                    balance.location,
                    _qty(balance.on_hand),
                ]
            )
        issues = views.movements(conn, scope, lot=lot, kind="issue", limit=MAX_VIEW_ROWS)
        truncated = truncated or _full(issues)
        for issue in issues:
            rows.append(
                [
                    heat_no,
                    lot,
                    receipt,
                    mtr,
                    "Issued",
                    _day(issue.recorded_at),
                    issue.from_location or "",
                    _qty(issue.qty),
                ]
            )
    return rows, truncated


def _consumables_by_cost_code(conn: Connection, scope: str, f: _Filters) -> _Rows:
    issues = views.movements(
        conn, scope, kind="issue", since=f.since, until=f.until, limit=MAX_VIEW_ROWS
    )
    consumable = {
        item.code
        for item in views.items(conn, project=scope, limit=MAX_VIEW_ROWS)
        if item.consumable
    }
    labels = f.cost_codes or {}
    totals: dict[tuple[str, str, str], Decimal] = {}
    for issue in issues:
        if issue.cost_code_id is None or issue.item_code not in consumable:
            continue
        key = (labels.get(issue.cost_code_id, issue.cost_code_id), issue.item_code, issue.uom)
        totals[key] = totals.get(key, ZERO) + issue.qty
    rows = [
        [label, item, uom, _qty(qty)]
        for (label, item, uom), qty in sorted(totals.items(), key=lambda kv: kv[0][:2])
    ]
    return rows, _full(issues)


_BUILDERS: Final[dict[str, _Builder]] = {
    "stock_on_hand": _stock_on_hand,
    "movement_log": _movement_log,
    "mto_status": _mto_status,
    "shortages": _shortages,
    "heat_trace": _heat_trace,
    "consumables_by_cost_code": _consumables_by_cost_code,
}


def build_report(
    conn: Connection,
    scope: str,
    name: str,
    *,
    since: str | None = None,
    until: str | None = None,
    heat: str | None = None,
    cost_codes: Mapping[str, str] | None = None,
) -> Report:
    """The report ``name`` of the project ``scope``. ``since`` and ``until`` bound the movement
    reports by day (ISO dates, both included); ``heat`` is the heat ``heat_trace`` traces;
    ``cost_codes`` maps a cost code id to its code. ``ValueError`` for an unknown name, for
    ``heat_trace`` without a heat, and for a date the views cannot read."""
    if name not in REPORT_NAMES:
        raise ValueError(f"unknown report {name!r}; the names are {', '.join(REPORT_NAMES)}")
    if name == "heat_trace" and not heat:
        raise ValueError("heat_trace needs a heat number")
    rows, truncated = _BUILDERS[name](conn, scope, _Filters(since, until, heat, cost_codes))
    return Report(name=name, columns=list(_COLUMNS[name]), rows=rows, truncated=truncated)


def to_csv(report: Report) -> str:
    """The report as CSV: the header row, then the rows, ``\\r\\n`` line ends, every cell through
    ``safe_cell``."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([safe_cell(c) for c in report.columns])
    for row in report.rows:
        writer.writerow([safe_cell(c) for c in row])
    return out.getvalue()
