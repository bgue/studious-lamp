"""What the receipts log and the receipt panel show: pure functions (P2-I3-T06b; "Receipts").

The rows and the panel are text built from ``tl_mod_materials.views`` models and nothing else: no
Textual, no client call, no clock, no I/O. The screen mounts these functions and the web twin
(``tl_web/present.py``) calls the same ones, so the two never differ in columns, words or signs.

A missing value is ``—`` (``EMPTY``), never ``None`` and never a bare ``-``. People are named
through ``who``; dates are the day part of the stored value (``day``).
"""

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_materials.views import (
    ReceiptDetailView,
    ReceiptFileView,
    ReceiptLineView,
    ReceiptView,
)

from tl_tui.display import Labels, humanize
from tl_tui.layout import (
    Item,
    Note,
    Page,
    Prop,
    Section,
    TableRow,
    identity_line,
    plain_lines,
    prop,
    state_line,
)
from tl_tui.layout import (
    shown as _shown,
)
from tl_tui.materials_text import day, mtr_mark, qty_text, who
from tl_tui.text import unit_label

RECEIPT_COLUMNS: tuple[str, ...] = (
    "Number",
    "Subject",
    "State",
    "Received",
    "Location",
    "Lines",
    "MTR",
)
RECEIPT_DROP: tuple[str, ...] = ("Lines", "Location", "MTR", "Received")  # least needed first
RIGHT: frozenset[str] = frozenset({"Lines"})
KEYS = "o open only  m missing MTR  / filter  F5 reload  Esc close"

LINE_COLUMNS: tuple[str, ...] = ("Line", "Item", "Qty", "UOM", "Heat", "Condition")
FILE_COLUMNS: tuple[str, ...] = ("Slot", "File", "Status")
MTR_SLOT = "mtr"
MTR_NOTE = "MTR required to accept"
REJECTED = "Rejected"
NO_FILES = "No files"
RECEIVING_INSPECTION = ("Receiving inspection", "n/a until quality inspections exist")
ALWAYS_SHOWN: tuple[str, ...] = ("Number", "Subject", "State")


# --- the log ----------------------------------------------------------------


def columns_for(rows: Sequence[ReceiptView]) -> tuple[str, ...]:
    """``RECEIPT_COLUMNS`` without each column whose cell is the same in every row.

    Number, Subject and State always stay (the log keeps them). A column is left out only when two
    or more rows agree on it, the rule the log screen applies to its shown rows; one row or none
    keeps every column.
    """
    if len(rows) < 2:
        return RECEIPT_COLUMNS
    drop = {
        column
        for column in RECEIPT_COLUMNS
        if column not in ALWAYS_SHOWN and len({_row_cell(v, column) for v in rows}) <= 1
    }
    return tuple(column for column in RECEIPT_COLUMNS if column not in drop)


def row_cells(
    view: ReceiptView,
    columns: Sequence[str],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> tuple[str, ...]:
    """The cells of one receipt row in the order of ``columns``. ``labels`` and ``technical`` do not
    change a row cell (the log has no technical-only column)."""
    return tuple(_row_cell(view, column) for column in columns)


def _row_cell(view: ReceiptView, column: str) -> str:
    if column == "Number":
        return _shown(view.number)
    if column == "Subject":
        return _shown(view.title)
    if column == "State":
        return _shown(humanize(view.state))
    if column == "Received":
        return day(view.received_on)
    if column == "Location":
        return _shown(view.location)
    if column == "Lines":
        return str(view.lines)
    if column == "MTR":
        return mtr_mark(view.mtr)
    raise ValueError(f"no receipt column {column!r}")


def summary_line(
    shown: int,
    total: int,
    *,
    open_only: bool = False,
    missing_mtr: bool = False,
    text: str = "",
) -> str:
    """``Showing 3 of 12 receipts · open only · missing MTR``; only the set filters are named."""
    parts = [f"Showing {shown} of {total} receipts"]
    if open_only:
        parts.append("open only")
    if missing_mtr:
        parts.append("missing MTR")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return " · ".join(parts)


# --- the panel --------------------------------------------------------------


def receipt_page(
    detail: ReceiptDetailView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> Page:
    """The receipt panel: identity ``number · title``, the state with the day of the last decision
    (else inspection, else receipt), the summary, then Lines, Delivery, Inspection and Files.
    ``technical`` adds the receipt id to Delivery."""
    since = day(detail.decided_on or detail.inspected_on or detail.received_on)
    return Page(
        identity=identity_line(detail.number, detail.title),
        state=state_line(_shown(humanize(detail.state)), since),
        sections=(
            _lines_section(detail),
            _delivery_section(detail, labels, technical=technical),
            _inspection_section(detail, labels),
            _files_section(detail),
        ),
        summary=f"PO {_shown(detail.po_line)} · {detail.lines} lines · {_shown(detail.location)}",
    )


def receipt_lines(
    detail: ReceiptDetailView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
    width: int | None = None,
) -> list[str]:
    """The receipt panel as plain lines."""
    return plain_lines(receipt_page(detail, labels, technical=technical), width=width)


def _lines_section(detail: ReceiptDetailView) -> Section:
    """The receipt's lines as one table; UOM is left out when every line has the same one."""
    lines = detail.line_rows
    columns = LINE_COLUMNS
    if len({line.uom for line in lines}) <= 1:
        columns = tuple(column for column in LINE_COLUMNS if column != "UOM")
    return Section(
        "Lines",
        tuple(TableRow(columns, _line_cells(line, columns)) for line in lines),
    )


def _line_cells(line: ReceiptLineView, columns: Sequence[str]) -> tuple[str, ...]:
    return tuple(_line_cell(line, column) for column in columns)


def _line_cell(line: ReceiptLineView, column: str) -> str:
    if column == "Line":
        return str(line.line_no)
    if column == "Item":
        return _shown(" ".join(part for part in (line.item_code, line.item_title) if part.strip()))
    if column == "Qty":
        return qty_text(line.qty)
    if column == "UOM":
        return _shown(unit_label(line.uom))
    if column == "Heat":
        return _shown(line.heat_no)
    if column == "Condition":
        return _shown(humanize(line.condition))
    raise ValueError(f"no receipt line column {column!r}")


def _delivery_section(
    detail: ReceiptDetailView, labels: Labels | None, *, technical: bool
) -> Section:
    items: list[Prop] = [
        prop("Supplier", detail.supplier_text),
        prop("PO line", detail.po_line),
        prop("Delivery ref", detail.delivery_ref),
        prop("Received on", day(detail.received_on)),
        prop("Received by", who(labels, detail.received_by)),
    ]
    if technical:
        items.append(prop("Id", detail.id))
    return Section("Delivery", tuple(items))


def _inspection_section(detail: ReceiptDetailView, labels: Labels | None) -> Section:
    items: list[Item] = [
        prop("Inspected by", who(labels, detail.inspected_by)),
        prop("Inspected on", day(detail.inspected_on)),
        prop("Decided by", who(labels, detail.decided_by)),
        prop("Decided on", day(detail.decided_on)),
    ]
    if detail.state == REJECTED:
        items.append(prop("Rejection reason", detail.rejection_reason))
    items.append(Prop(*RECEIVING_INSPECTION))
    return Section("Inspection", tuple(items))


def _files_section(detail: ReceiptDetailView) -> Section:
    """The files as one table, the MTR slot first. An MTR the receipt needs and lacks is one plain
    line before the table, in the waiting colour; it is not a file row, since no file exists. With
    no files the section reads ``No files`` (plain: the layout shows a section note only when the
    section has no items)."""
    items: list[Item] = []
    if detail.mtr_required and detail.mtr == "missing":
        items.append(Note(MTR_NOTE))
    items.extend(TableRow(FILE_COLUMNS, _file_cells(file)) for file in _mtr_first(detail.files))
    return Section("Files", tuple(items), note="" if detail.files else NO_FILES)


def _mtr_first(files: Sequence[ReceiptFileView]) -> list[ReceiptFileView]:
    return sorted(files, key=lambda file: file.slot != MTR_SLOT)  # stable: the MTR slot first


def _file_cells(file: ReceiptFileView) -> tuple[str, str, str]:
    return (_shown(file.slot), _shown(file.filename), _shown(file.status))
