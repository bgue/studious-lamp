"""What the stock log, the movement log and the lot panel show: pure functions (P2-I3-T06a; D25).

The rows, the panel and the summary lines are text built from ``tl_mod_materials.views`` models
and nothing else: no Textual, no client call, no clock (``today`` is a parameter), no I/O. The
screens mount these functions and the web twins (``tl_web/present.py``) call the same ones, so the
two never differ in columns, words or signs.

Quantities are ``Decimal`` in and text out (``qty_text``). A missing value is ``—`` (``EMPTY``),
never ``None`` and never a bare ``-``. The ``For`` columns and the reservation ``For`` are not here
(D26): they wait for the S5 view keys.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from tl_mod_materials.views import LotDetailView, MovementView, StockRowView

from tl_tui.display import Labels, actor_label, humanize
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
from tl_tui.text import unit_label

RIGHT: frozenset[str] = frozenset({"On hand", "Reserved", "Available"})

STOCK_COLUMNS: tuple[str, ...] = (
    "Lot",
    "Subject",
    "Location",
    "On hand",
    "Reserved",
    "Available",
    "UOM",
)
STOCK_DROP: tuple[str, ...] = ("UOM", "Location")  # least needed first
MOVEMENT_COLUMNS: tuple[str, ...] = ("Date", "Kind", "Lot", "Item", "Qty", "From", "To", "By")
MOVEMENT_DROP: tuple[str, ...] = ("By", "Item", "To", "From")  # least needed first

KIND_WORDS: Mapping[str, str] = {
    "issue": "Issue",
    "transfer": "Transfer",
    "return": "Return",
    "adjust": "Adjust",
    "scrap": "Scrap",
    "receive": "Receipt",  # the ledger's kind for a receipt (tl_mod_materials.names.RECEIVE)
    "reserve": "Reserve",
    "unreserve": "Release",
}
PERIODS: tuple[str, ...] = ("all", "7 days", "30 days", "this month")

STOCK_KEYS = "/ filter  l lot  i item  h heat  z subtree  F5 reload  Esc close"
MOVEMENT_KEYS = "k kind  p period  F5 reload  Esc close"

LOT_QUANTITY_COLUMNS: tuple[str, ...] = ("Location", "On hand", "Reserved", "Available")
LOT_RESERVATION_COLUMNS: tuple[str, ...] = ("MTO line", "Location", "Qty")
LOT_MOVEMENT_COLUMNS: tuple[str, ...] = ("Date", "Kind", "Qty", "From", "To", "By")
LAST_MOVEMENTS = 10  # the lot panel's movement table

_THREE_DECIMALS = Decimal("0.001")
_MTR_MARKS: Mapping[str, str] = {"present": "✓", "missing": "—", "n/a": "n/a"}
_PERIOD_DAYS: Mapping[str, int] = {"7 days": 7, "30 days": 30}
_PERIOD_WORDS: Mapping[str, str] = {
    "7 days": "last 7 days",
    "30 days": "last 30 days",
    "this month": "this month",
}


# --- shared -----------------------------------------------------------------


def qty_text(value: Decimal) -> str:
    """``1 234 567.5``: rounded to at most three decimals, trailing zeros dropped, the integer part
    grouped by plain spaces, ``0`` for zero."""
    with localcontext() as ctx:
        ctx.prec = 60
        rounded = value.quantize(_THREE_DECIMALS, rounding=ROUND_HALF_UP)
    if rounded == 0:
        return "0"
    sign = "-" if rounded < 0 else ""
    whole, _, fraction = format(abs(rounded), "f").partition(".")
    fraction = fraction.rstrip("0")
    grouped = f"{int(whole):,}".replace(",", " ")
    return f"{sign}{grouped}.{fraction}" if fraction else f"{sign}{grouped}"


def mtr_mark(state: str | None) -> str:
    """``✓`` for a present MTR file, ``—`` for a missing one, ``n/a`` when none is needed."""
    if not state:
        return EMPTY
    return _MTR_MARKS.get(state, state)


def day(iso: str | None) -> str:
    """The date part of an ISO timestamp (its first ten characters); ``—`` when absent."""
    if iso is None:
        return EMPTY
    return _shown(iso[:10])


def who(labels: Labels | None, actor: str | None) -> str:
    """A person by name (``user:`` cut), an agent by name (``agent:`` cut), a service by its label;
    ``—`` when there is no actor."""
    if actor is None or not actor.strip():
        return EMPTY
    if actor.startswith("svc:"):
        return actor_label(labels if labels is not None else Labels(), actor)
    for prefix in ("user:", "agent:"):
        if actor.startswith(prefix):
            return actor[len(prefix) :]
    return actor


def _kind_word(kind: str) -> str:
    return _shown(KIND_WORDS.get(kind) or humanize(kind))


def next_kind(current: str | None, kinds: Sequence[str]) -> str | None:
    """The kind filter after ``current``: ``None`` (all), then each kind in order, then ``None``."""
    cycle: list[str | None] = [None, *kinds]
    if current not in cycle:
        return None
    return cycle[(cycle.index(current) + 1) % len(cycle)]


def next_period(current: str) -> str:
    """The period after ``current`` in ``PERIODS``; ``all`` after the last one."""
    if current not in PERIODS:
        return PERIODS[0]
    return PERIODS[(PERIODS.index(current) + 1) % len(PERIODS)]


def period_range(period: str, today: str) -> tuple[str | None, str | None]:
    """The ISO dates a period covers, both days included, ending on ``today`` (``YYYY-MM-DD``).
    ``7 days`` and ``30 days`` start that many days back, counting today; ``this month`` starts on
    the first of the month; ``all`` has no bounds."""
    if period == "all":
        return (None, None)
    end = date.fromisoformat(today)
    if period == "this month":
        return (end.replace(day=1).isoformat(), end.isoformat())
    if period not in _PERIOD_DAYS:
        raise ValueError(f"unknown period {period!r}")
    start = end - timedelta(days=_PERIOD_DAYS[period] - 1)
    return (start.isoformat(), end.isoformat())


# --- stock log --------------------------------------------------------------


def stock_columns_for(rows: Sequence[StockRowView]) -> tuple[str, ...]:
    """``STOCK_COLUMNS`` without UOM and Location when every row has the same one."""
    drop: set[str] = set()
    if len({r.uom for r in rows}) <= 1:
        drop.add("UOM")
    if len({r.location for r in rows}) <= 1:
        drop.add("Location")
    return tuple(column for column in STOCK_COLUMNS if column not in drop)


def stock_cells(
    view: StockRowView,
    columns: Sequence[str],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> tuple[str, ...]:
    """The cells of one stock row in the order of ``columns``. ``labels`` and ``technical`` do not
    change a stock cell (the stock log has no technical-only column)."""
    return tuple(_stock_cell(view, column) for column in columns)


def _stock_cell(view: StockRowView, column: str) -> str:
    if column == "Lot":
        return _shown(view.heat_no or view.lot)
    if column == "Subject":
        return _shown(view.item_title)
    if column == "Location":
        return _shown(view.location_title or view.location)
    if column == "On hand":
        return qty_text(view.on_hand)
    if column == "Reserved":
        return qty_text(view.reserved)
    if column == "Available":
        return qty_text(view.available)
    if column == "UOM":
        return _shown(unit_label(view.uom))
    raise ValueError(f"no stock column {column!r}")


def stock_summary(
    shown: int,
    total: int,
    *,
    item: str | None = None,
    location: str | None = None,
    heat: str | None = None,
    lot: str | None = None,
    subtree: bool = False,
) -> str:
    """``Showing 12 of 40 stock rows · item X · location Y``; only set filters are named."""
    parts = [f"Showing {shown} of {total} stock rows"]
    if item:
        parts.append(f"item {item}")
    if location:
        parts.append(f"location {location}" + (" and below" if subtree else ""))
    if heat:
        parts.append(f"heat {heat}")
    if lot:
        parts.append(f"lot {lot}")
    return " · ".join(parts)


# --- lot panel --------------------------------------------------------------


def lot_page(
    detail: LotDetailView,
    row: StockRowView | None = None,
    labels: Labels | None = None,
    *,
    mtr: str | None = None,
    technical: bool = False,
) -> Page:
    """The lot panel: identity ``heat · item title``, the line ``Lot <key> · receipt <number>``, the
    summary of the selected row, then Quantities, Reservations, Movements (last ten) and
    Traceability. ``technical`` adds the seq to each movement date and the lot id.
    """
    summary = ""
    if row is not None:
        summary = join_facts(
            _shown(row.location_title or row.location),
            f"{qty_text(row.on_hand)} on hand",
            f"{qty_text(row.reserved)} reserved",
            f"{qty_text(row.available)} available",
        )
    titles = {q.location: q.location_title for q in detail.quantities}
    quantities = Section(
        "Quantities",
        tuple(
            TableRow(
                LOT_QUANTITY_COLUMNS,
                (
                    _shown(q.location_title or q.location),
                    qty_text(q.on_hand),
                    qty_text(q.reserved),
                    qty_text(q.available),
                ),
            )
            for q in detail.quantities
        ),
        note="" if detail.quantities else "No stock on hand",
    )
    reservations = Section(
        "Reservations",
        tuple(
            TableRow(
                LOT_RESERVATION_COLUMNS,
                (
                    _shown(r.mto_line),
                    _shown(titles.get(r.location) or r.location),
                    qty_text(r.qty),
                ),
            )
            for r in detail.reservations
        ),
        note="" if detail.reservations else "No reservations",
    )
    movements = Section(
        "Movements",
        tuple(
            TableRow(
                LOT_MOVEMENT_COLUMNS,
                movement_cells(m, LOT_MOVEMENT_COLUMNS, labels, technical=technical),
            )
            for m in detail.movements[:LAST_MOVEMENTS]
        ),
        note="" if detail.movements else "No movements",
    )
    traceability: list[Prop] = [
        prop("Receipt", detail.receipt),
        prop("PO line", detail.po_line),
        prop("Heat", detail.heat_no),
        prop("MTR", mtr),
    ]
    if technical:
        traceability.append(prop("Id", detail.id))
    return Page(
        identity=identity_line(detail.heat_no or detail.key, detail.item_title),
        state=f"Lot {_shown(detail.key)} · receipt {_shown(detail.receipt)}",
        sections=(
            quantities,
            reservations,
            movements,
            Section("Traceability", tuple(traceability)),
        ),
        summary=summary,
    )


def lot_lines(
    detail: LotDetailView,
    row: StockRowView | None = None,
    labels: Labels | None = None,
    *,
    mtr: str | None = None,
    technical: bool = False,
    width: int | None = None,
) -> list[str]:
    """The lot panel as plain lines."""
    return plain_lines(lot_page(detail, row, labels, mtr=mtr, technical=technical), width=width)


# --- movement log -----------------------------------------------------------


def movement_columns_for(rows: Sequence[MovementView]) -> tuple[str, ...]:
    """``MOVEMENT_COLUMNS`` without By, Item, To and From where every row has the same value."""
    constant = {
        "By": {r.actor for r in rows},
        "Item": {r.item_code for r in rows},
        "To": {r.to_location for r in rows},
        "From": {r.from_location for r in rows},
    }
    drop = {name for name, values in constant.items() if len(values) <= 1}
    return tuple(column for column in MOVEMENT_COLUMNS if column not in drop)


def movement_cells(
    view: MovementView,
    columns: Sequence[str],
    labels: Labels | None = None,
    *,
    technical: bool = False,
) -> tuple[str, ...]:
    """The cells of one movement in the order of ``columns``. ``technical`` adds ``#<seq>`` after
    the date."""
    return tuple(_movement_cell(view, column, labels, technical) for column in columns)


def _movement_cell(view: MovementView, column: str, labels: Labels | None, technical: bool) -> str:
    if column == "Date":
        text = day(view.recorded_at)
        return f"{text} #{view.seq}" if technical else text
    if column == "Kind":
        return _kind_word(view.kind)
    if column == "Lot":
        return _shown(view.heat_no or view.lot)
    if column == "Item":
        return _shown(view.item_code)
    if column == "Qty":
        return _signed_qty(view)
    if column == "From":
        return _shown(view.from_location)
    if column == "To":
        return _shown(view.to_location)
    if column == "By":
        return who(labels, view.actor)
    raise ValueError(f"no movement column {column!r}")


def _signed_qty(view: MovementView) -> str:
    """``+12`` for a receipt in, ``-3`` for an issue out, unsigned when no direction."""
    magnitude = qty_text(abs(view.qty))
    if magnitude == "0":
        return magnitude
    if view.direction == "in":
        return f"+{magnitude}"
    if view.direction == "out":
        return f"-{magnitude}"
    return qty_text(view.qty)


def movement_summary(
    shown: int,
    total: int,
    *,
    kind: str | None = None,
    period: str = "all",
    lot: str | None = None,
) -> str:
    """``Showing 4 of 40 movements · Issue · last 30 days``; only set filters are named."""
    parts = [f"Showing {shown} of {total} movements"]
    if kind:
        parts.append(_kind_word(kind))
    if period != "all":
        parts.append(_PERIOD_WORDS.get(period, period))
    if lot:
        parts.append(f"lot {lot}")
    return " · ".join(parts)
