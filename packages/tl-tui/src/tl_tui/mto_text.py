"""What the MTO lines log and its line panel show: pure functions (P2-I3-T06d; D25).

The rows, the panel and the summary line are text built from ``tl_mod_materials.views`` and
``views_detail`` models and nothing else: no Textual, no client call, no clock, no I/O. The
``MtoLinesScreen`` mounts these functions and the web twin (``tl_web/present.py``) calls the same
ones, so the two never differ in columns, words or figures.

Quantities are ``Decimal`` in and text out (``materials_text.qty_text``). A missing value is ``—``
(``EMPTY``), never ``None`` and never a bare ``-``.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from tl_mod_materials.views import MtoLineView
from tl_mod_materials.views_detail import MtoLineDetailView

from tl_tui.display import Labels
from tl_tui.layout import (
    EMPTY,
    Page,
    Prop,
    Section,
    TableRow,
    identity_line,
    join_facts,
    plain_lines,
    prop,
)
from tl_tui.layout import (
    shown as _shown,
)
from tl_tui.materials_text import day, qty_text
from tl_tui.text import unit_label

MTO_COLUMNS: tuple[str, ...] = (
    "Number",
    "Subject",
    "For",
    "Required",
    "Reserved",
    "Issued",
    "Short",
    "Need by",
)
MTO_DROP: tuple[str, ...] = ("Need by", "Issued", "For")  # least needed first
RIGHT: frozenset[str] = frozenset({"Required", "Reserved", "Issued", "Short"})

KEYS = "1 all lines  2 short only  / filter  F5 reload  Esc close"

RESERVATION_COLUMNS: tuple[str, ...] = ("Lot", "Location", "Qty")
RECEIPT_COLUMNS: tuple[str, ...] = ("Receipt", "State", "Received on", "Qty")


# --- the log ----------------------------------------------------------------


def columns_for(rows: Sequence[MtoLineView]) -> tuple[str, ...]:
    """``MTO_COLUMNS`` without For when every row has the same work package, and without Need by
    when every row has the same need-by date (none, for now)."""
    drop: set[str] = set()
    if len({r.work_package for r in rows}) <= 1:
        drop.add("For")
    if len({r.need_by for r in rows}) <= 1:
        drop.add("Need by")
    return tuple(column for column in MTO_COLUMNS if column not in drop)


def row_cells(
    view: MtoLineView,
    columns: Sequence[str],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> tuple[str, ...]:
    """The cells of one take-off line in the order of ``columns``. ``labels`` and ``technical`` do
    not change a cell (the log has no coded value and no technical-only column)."""
    return tuple(_cell(view, column) for column in columns)


def _cell(view: MtoLineView, column: str) -> str:
    if column == "Number":
        return _shown(view.key)
    if column == "Subject":
        return _shown(view.item_title)
    if column == "For":
        return _shown(view.work_package)
    if column == "Required":
        return qty_text(view.required)
    if column == "Reserved":
        return qty_text(view.reserved)
    if column == "Issued":
        return qty_text(view.issued)
    if column == "Short":
        return qty_text(view.short)
    if column == "Need by":
        return day(view.need_by)
    raise ValueError(f"no MTO column {column!r}")


def summary_line(
    shown: int,
    total: int,
    *,
    short_only: bool = False,
    work_package: str | None = None,
    text: str = "",
) -> str:
    """``Showing 2 of 3 lines · short only · for P123-CWP-PIP-0001``; only set filters are named."""
    parts = [f"Showing {shown} of {total} lines"]
    if short_only:
        parts.append("short only")
    if work_package:
        parts.append(f"for {work_package}")
    stripped = text.strip()
    if stripped:
        parts.append(f'filter "{stripped}"')
    return " · ".join(parts)


# --- the line panel ---------------------------------------------------------


def _document(key: str) -> tuple[str, str]:
    """``ISO-1234`` and ``A`` from ``ISO-1234@A/MTO/001``; ``—`` twice when there is no ``@``."""
    if "@" not in key:
        return EMPTY, EMPTY
    document, _, rest = key.partition("@")
    revision = rest.partition("/")[0]
    return _shown(document), _shown(revision)


def _with_unit(value: Decimal, uom: str) -> str:
    """``12 m``; the number alone when the unit is unknown."""
    return f"{qty_text(value)} {unit_label(uom)}".rstrip()


def mto_page(
    detail: MtoLineDetailView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> Page:
    """The line panel: identity ``<key> · <item title>``, the state ``Short N <UOM>`` or
    ``Covered``, the summary (work package, required, short), then Source, Coverage, Reservations
    and Open receipts. ``technical`` adds the line id to Source."""
    document, revision = _document(detail.key)
    source: list[Prop] = [
        prop("MTO", detail.mto),
        prop("Document", document),
        prop("Revision", revision),
    ]
    if technical:
        source.append(prop("Id", detail.id))
    reservations = Section(
        "Reservations",
        tuple(
            TableRow(
                RESERVATION_COLUMNS,
                (_shown(r.lot), _shown(r.location), qty_text(r.qty)),
            )
            for r in detail.reservations
        ),
        note="" if detail.reservations else "No reservations",
    )
    receipts = Section(
        "Open receipts",
        tuple(
            TableRow(
                RECEIPT_COLUMNS,
                (
                    _shown(r.number),
                    _shown(r.state),
                    day(r.received_on),
                    qty_text(r.qty),
                ),
            )
            for r in detail.open_receipts
        ),
        note="" if detail.open_receipts else "No open receipts",
    )
    coverage = Section(
        "Coverage",
        (
            prop("Required", _with_unit(detail.required, detail.uom)),
            prop("Reserved", _with_unit(detail.reserved, detail.uom)),
            prop("Issued", _with_unit(detail.issued, detail.uom)),
            prop("Short", _with_unit(detail.short, detail.uom)),
        ),
    )
    state = f"Short {_with_unit(detail.short, detail.uom)}" if detail.short > 0 else "Covered"
    return Page(
        identity=identity_line(detail.key, detail.item_title),
        state=state,
        sections=(
            Section("Source", tuple(source)),
            coverage,
            reservations,
            receipts,
        ),
        summary=join_facts(
            f"For {_shown(detail.work_package)}",
            f"required {qty_text(detail.required)}",
            f"short {qty_text(detail.short)}",
        ),
    )


def mto_lines(
    detail: MtoLineDetailView,
    labels: Labels | None = None,
    *,
    technical: bool = False,
    width: int | None = None,
) -> list[str]:
    """The line panel as plain lines."""
    return plain_lines(mto_page(detail, labels, technical=technical), width=width)
