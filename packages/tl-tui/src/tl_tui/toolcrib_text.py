"""The toolcrib line: what it reads, checks and sends (P2-I4B-T06; brief §10.5, §M4).

One typed line, ``<tool> <person> [xN]``: the tool is a lot key or an item code with one lot in the
crib, the person is who takes the tool (required for an issue), ``xN`` is the count (one when
absent). The line becomes one ``IssueStock`` or ``ReturnStock`` with one movement at the crib. No
Textual, no client call: the screen reads the crib's stock rows and posts the command it builds.

The message constants are plain words; a missing value is never typed as a dash.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from tl_mod_materials.handlers.movements import IssueStock, Movement, ReturnStock
from tl_mod_materials.views import LocationView, StockRowView

#: The two modes, in the order the status keys name them.
MODES: tuple[str, ...] = ("issue", "return")
KEYS = "Enter send  F2 issue  F3 return  Ctrl+R return  Esc close"

NEED_TOOL = "Type the tool: its lot key, or its item code when the crib holds one lot of it."
NEED_PERSON = "Type the person who takes the tool, after the tool."
BAD_QTY = "The count after x must be a positive number of at most three decimals."
BAD_MODE = "The mode must be issue or return."

_QTY_TEXT = re.compile(r"[0-9]+(\.[0-9]{1,3})?")
_TITLES: dict[str, str] = {"issue": "Issue a tool", "return": "Return a tool"}


class ToolcribError(Exception):
    """A tool the line cannot name; the message goes to the status line as typed."""


@dataclass(frozen=True)
class ToolLine:
    """The line split into its parts: the count is the text after ``x`` (``"1"`` when absent)."""

    tool: str
    person: str
    qty: str


def parse_line(text: str) -> ToolLine:
    """Split ``<tool> <person> [xN]``; words are separated by spaces, the person keeps its inner
    spaces (``Ana Ruiz``). A trailing ``xN`` word is the count, whatever it holds."""
    words = text.split()
    qty = "1"
    if len(words) >= 2 and words[-1].startswith("x"):
        qty = words.pop()[1:]
    tool = words[0] if words else ""
    person = " ".join(words[1:])
    return ToolLine(tool=tool, person=person, qty=qty)


def check_line(mode: str, parsed: ToolLine) -> list[tuple[str, str]]:
    """The line's problems as ``(field, message)``: a known mode, a tool, a person for an issue,
    and a positive count of at most three decimals."""
    if mode not in MODES:
        return [("mode", BAD_MODE)]
    if not parsed.tool:
        return [("line", NEED_TOOL)]
    errors: list[tuple[str, str]] = []
    if mode == "issue" and not parsed.person:
        errors.append(("person", NEED_PERSON))
    if not _is_positive_qty(parsed.qty):
        errors.append(("qty", BAD_QTY))
    return errors


def _is_positive_qty(text: str) -> bool:
    if _QTY_TEXT.fullmatch(text) is None:
        return False
    return Decimal(text) > 0


def resolve_tool(tool: str, rows: Sequence[StockRowView]) -> StockRowView:
    """The crib's stock row the tool names: a lot key (any case) first, else the one lot of an
    item code (any case). Several lots of the item, or none, raise ``ToolcribError``."""
    wanted = tool.strip().casefold()
    for row in rows:
        if row.lot.casefold() == wanted:
            return row
    same_item = [row for row in rows if row.item_code.casefold() == wanted]
    if not same_item:
        raise ToolcribError(no_such_tool(tool))
    if len(same_item) > 1:
        raise ToolcribError(several_lots(tool, len(same_item)))
    return same_item[0]


def build_command(
    mode: str,
    *,
    lot: str,
    uom: str,
    qty: str,
    person: str,
    crib: str,
    actor: str,
    project: str,
) -> IssueStock | ReturnStock:
    """The command the line sends (source ``tui``): an issue takes the lot out of the crib to the
    person; a return puts it back into the crib. A blank person is sent as ``None``."""
    who = person.strip() or None
    scope = f"project:{project}"
    if mode == "issue":
        move = Movement(
            lot_key=lot, qty=qty, uom=uom, from_location=crib, to_location=None, person=who
        )
        return IssueStock(actor=actor, source="tui", scope=scope, movements=[move])
    if mode == "return":
        move = Movement(
            lot_key=lot, qty=qty, uom=uom, from_location=None, to_location=crib, person=who
        )
        return ReturnStock(actor=actor, source="tui", scope=scope, movements=[move])
    raise ToolcribError(BAD_MODE)


def done_text(mode: str, qty: str, uom: str, lot: str, person: str) -> str:
    """The status line after a command is posted: ``Issued 2 ea of L-1 to Ana Ruiz.``"""
    if mode == "issue":
        return f"Issued {qty} {uom} of {lot} to {person}."
    if person:
        return f"Took back {qty} {uom} of {lot} from {person}."
    return f"Took back {qty} {uom} of {lot}."


def no_such_tool(tool: str) -> str:
    """The status line when no lot or item of the crib has that name."""
    return f"No tool {tool} is in this crib."


def several_lots(tool: str, n: int) -> str:
    """The status line when an item code has ``n`` lots in the crib: the lot key is needed."""
    return f"{tool} has {n} lots in this crib. Type the lot key instead."


def mode_title(mode: str) -> str:
    """The screen's title for a mode: ``Issue a tool`` or ``Return a tool``."""
    return _TITLES[mode]


def crib_choices(locations: Sequence[LocationView]) -> list[str]:
    """The codes of the project's toolcrib locations that are not retired, sorted."""
    return sorted(loc.code for loc in locations if loc.kind == "toolcrib" and not loc.retired)
