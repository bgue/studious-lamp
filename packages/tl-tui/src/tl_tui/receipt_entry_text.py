"""What the new-receipt form shows and checks: pure functions (P2-I3-T06e; "Receipts").

The form's field list, the hint lines under the PO line and Location fields, the validation of the
header and of one line, the status-line texts and the command the form sends. No Textual, no
client call, no clock (the date is a parameter), no I/O. The screen mounts these functions and the
web twin calls the same ones, so the two never differ in fields, words or the command they send.

A missing value is ``—`` (``EMPTY``), never ``None`` and never a bare ``-``.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from datetime import date
from decimal import Decimal

from tl_mod_materials.handlers.receipts import CONDITIONS, CreateReceipt, ReceiptLineIn
from tl_mod_materials.views import LocationView, MaterialItemView, PoLineView

from tl_tui.display import humanize
from tl_tui.materials_text import qty_text
from tl_tui.text import EMPTY, unit_label

#: The header fields as ``(key, label)``, in the order the form shows them.
HEADER_FIELDS: tuple[tuple[str, str], ...] = (
    ("po_line", "PO line"),
    ("supplier", "Supplier"),
    ("delivery_ref", "Delivery ref"),
    ("received_on", "Received on"),
    ("location", "Location"),
)
#: The entry row's fields as ``(key, label)``; UOM is read from the item, not typed.
LINE_FIELDS: tuple[tuple[str, str], ...] = (
    ("item", "Item"),
    ("qty", "Qty"),
    ("heat", "Heat"),
    ("condition", "Condition"),
)
#: The most lines a receipt holds (the command model's ``lines`` maximum).
MAX_LINES = 50
#: The most PO line or location hint lines shown under a field.
HINT_LIMIT = 5
DEFAULT_CONDITION = "good"
KEYS = "Ctrl+S save  Enter add line  Ctrl+D remove line  Esc close"

ITEM_REQUIRED_MESSAGE = "Pick an item of this project."
LOCATION_MESSAGE = "Pick a location of this project."
DATE_MESSAGE = "Received on must be a date, YYYY-MM-DD."
FUTURE_DATE_MESSAGE = "Received on is after today."
QTY_MESSAGE = "Quantity must be a positive number."
NO_LINES_MESSAGE = "Add at least one line."
MAX_LINES_MESSAGE = f"A receipt holds at most {MAX_LINES} lines."
NOT_SAVED_TEXT = "Not saved. Fix the marked fields and save again."
MTR_SENTENCE = "Attach the MTR on the receipt (tl file put, slot mtr)."

#: Quantity text: digits, at most three decimals (the command's rule), above zero.
_QTY_TEXT = re.compile(r"[0-9]+(\.[0-9]{1,3})?")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def item_message(code: str) -> str:
    """``Item FLG-150 is not in this project's library.``"""
    return f"Item {code} is not in this project's library."


def condition_message() -> str:
    """The condition message, with the list in words: ``Condition must be one of: good, ...``."""
    words = ", ".join(humanize(name) for name in CONDITIONS)
    return f"Condition must be one of: {words}."


def saved_text(number: str) -> str:
    """The status line after a receipt is booked: it names what is left (the MTR, D42)."""
    return f"Saved {number}. {MTR_SENTENCE}"


def added_text(code: str) -> str:
    """The status line after a line is added to the list."""
    return f"Added line {code}."


# --- hints -------------------------------------------------------------------------------------


def po_line_hints(po_lines: Sequence[PoLineView]) -> list[str]:
    """One hint line per PO line of the completion, at most ``HINT_LIMIT``: key, item and the
    quantity still open (ordered less received, never below zero)."""
    return [_po_hint(po) for po in po_lines[:HINT_LIMIT]]


def _po_hint(po: PoLineView) -> str:
    open_qty = max(Decimal(0), po.qty_ordered - po.qty_received)
    unit = unit_label(po.uom)
    title = " ".join(part for part in (po.item_code, po.item_title) if part.strip())
    qty = f"{qty_text(open_qty)} {unit}".rstrip()
    return f"{po.key}  {title}  {qty} open"


def po_line_chosen(po_lines: Sequence[PoLineView], key: str) -> PoLineView | None:
    """The PO line whose key is typed exactly, else ``None``: a chosen line fills the supplier."""
    wanted = key.strip()
    for po in po_lines:
        if po.key == wanted:
            return po
    return None


def location_hints(locations: Sequence[LocationView], text: str) -> list[str]:
    """Locations whose code starts with ``text`` or whose title holds it (any case), as
    ``code  title`` lines, at most ``HINT_LIMIT``. Empty text lists the first of them."""
    wanted = text.strip().casefold()
    shown: list[str] = []
    for location in locations:
        if wanted and not (
            location.code.casefold().startswith(wanted) or wanted in location.title.casefold()
        ):
            continue
        shown.append(_location_hint(location))
        if len(shown) == HINT_LIMIT:
            break
    return shown


def _location_hint(location: LocationView) -> str:
    return "  ".join(part for part in (location.code, location.title) if part.strip())


# --- validation --------------------------------------------------------------------------------


def check_header(
    values: Mapping[str, str], locations: Collection[str], today: date
) -> list[tuple[str, str]]:
    """The header's problems as ``(field, message)``: the Location must be a code of the project,
    Received on a calendar date written YYYY-MM-DD and not after ``today``. The PO line, supplier
    and delivery reference are not checked here (the service refuses an unknown PO line)."""
    errors: list[tuple[str, str]] = []
    received = _text(values, "received_on")
    if not _ISO_DATE.fullmatch(received):
        errors.append(("received_on", DATE_MESSAGE))
    else:
        try:
            parsed = date.fromisoformat(received)
        except ValueError:
            errors.append(("received_on", DATE_MESSAGE))
        else:
            if parsed > today:
                errors.append(("received_on", FUTURE_DATE_MESSAGE))
    if _text(values, "location") not in locations:
        errors.append(("location", LOCATION_MESSAGE))
    return errors


def check_line(
    values: Mapping[str, str], items: Mapping[str, MaterialItemView]
) -> list[tuple[str, str]]:
    """One line's problems as ``(field, message)``: the item is a code of the project's library,
    the quantity a positive decimal of at most three places, the condition one of the list (a
    blank condition is ``good``). The heat number is not checked here (the service checks it)."""
    errors: list[tuple[str, str]] = []
    code = _text(values, "item")
    if not code:
        errors.append(("item", ITEM_REQUIRED_MESSAGE))
    elif code not in items:
        errors.append(("item", item_message(code)))
    if not _is_positive_qty(_text(values, "qty")):
        errors.append(("qty", QTY_MESSAGE))
    condition = _text(values, "condition") or DEFAULT_CONDITION
    if condition not in CONDITIONS:
        errors.append(("condition", condition_message()))
    return errors


def check_count(count: int) -> list[tuple[str, str]]:
    """The line count's problem as ``(field, message)``: one to ``MAX_LINES`` lines per receipt."""
    if count < 1:
        return [("lines", NO_LINES_MESSAGE)]
    if count > MAX_LINES:
        return [("lines", MAX_LINES_MESSAGE)]
    return []


def _is_positive_qty(text: str) -> bool:
    if _QTY_TEXT.fullmatch(text) is None:
        return False
    return Decimal(text) > 0


# --- the line row and the command --------------------------------------------------------------


def line_summary(line: Mapping[str, str], uom: str | None) -> str:
    """One line of the list: ``FLG-150  12 EA  heat H-7781  good``. The unit is the item's
    (``uom``, shown through ``unit_label``); a missing heat number reads ``—``."""
    item = _text(line, "item") or EMPTY
    unit = unit_label(uom)
    qty = _qty_text_or_raw(_text(line, "qty"))
    heat = _text(line, "heat") or EMPTY
    condition = humanize(_text(line, "condition") or DEFAULT_CONDITION)
    quantity = f"{qty} {unit}".rstrip()
    return f"{item}  {quantity}  heat {heat}  {condition}"


def _qty_text_or_raw(text: str) -> str:
    if _is_positive_qty(text):
        return qty_text(Decimal(text))
    return text or EMPTY


def build_command(
    header: Mapping[str, str],
    lines: Sequence[Mapping[str, str]],
    *,
    actor: str,
    project: str,
) -> CreateReceipt:
    """The ``CreateReceipt`` the form sends (source ``tui``). Blank optional fields are sent as
    ``None``; a blank condition is ``good``; the unit is not sent (the service takes the item's)."""
    return CreateReceipt(
        actor=actor,
        source="tui",
        scope=f"project:{project}",
        po_line=_none_if_blank(header, "po_line"),
        supplier_text=_text(header, "supplier"),
        delivery_ref=_none_if_blank(header, "delivery_ref"),
        received_on=_text(header, "received_on"),
        location_code=_text(header, "location"),
        lines=[_line_in(line) for line in lines],
    )


def _line_in(line: Mapping[str, str]) -> ReceiptLineIn:
    return ReceiptLineIn(
        item_code=_text(line, "item"),
        qty=_text(line, "qty"),
        uom=None,
        heat_no=_none_if_blank(line, "heat"),
        condition=_text(line, "condition") or DEFAULT_CONDITION,
        serials_text=None,
    )


def _text(values: Mapping[str, str], key: str) -> str:
    return values.get(key, "").strip()


def _none_if_blank(values: Mapping[str, str], key: str) -> str | None:
    return _text(values, key) or None
