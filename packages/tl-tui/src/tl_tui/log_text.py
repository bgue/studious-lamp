"""Text of the shared log screen: the breadcrumb, the actions bar and the width rule (P1-UX2-S2).

Pure functions. ``LogAction`` (in ``widgets/log_screen.py``) is only read through the two
attributes the bar needs, so this module imports nothing from the widgets.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from rich.cells import cell_len, set_cell_size

WIDE_COLUMNS = 160  # at this width and above the panel sits to the right of the list
SEPARATOR = " › "
OPEN_ACTION = "[Enter] Open record"

_NAMES = {
    "enter": "Enter",
    "escape": "Esc",
    "slash": "/",
    "question_mark": "?",
    "space": "Space",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Del",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "home": "Home",
    "end": "End",
}
_MODIFIERS = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "meta": "Meta", "super": "Super"}
_FUNCTION_KEY = re.compile(r"f\d{1,2}")


class ActionLike(Protocol):
    """What the bar reads of an action: its textual key name and its plain label."""

    @property
    def key(self) -> str: ...

    @property
    def label(self) -> str: ...


def is_wide(columns: int) -> bool:
    """True when a terminal ``columns`` wide shows the panel beside the list."""
    return columns >= WIDE_COLUMNS


def key_label(key: str) -> str:
    """A textual key name as a person reads it: ``ctrl+e`` is ``Ctrl+E``, ``f6`` is ``F6``."""
    parts = key.split("+")
    shown: list[str] = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part in _MODIFIERS and not last:
            shown.append(_MODIFIERS[part])
        elif part in _NAMES:
            shown.append(_NAMES[part])
        elif _FUNCTION_KEY.fullmatch(part):
            shown.append(part.upper())
        elif len(part) == 1:
            shown.append(part.upper() if len(parts) > 1 else part)
        else:
            shown.append(part[:1].upper() + part[1:])
    return "+".join(shown)


def breadcrumb_text(
    project: str, log: str, number: str | None, title: str | None, width: int
) -> str:
    """``P123 › RFI Log › P123-RFI-0328: Conflict in piling/...``, or ``P123 › RFI Log`` alone.

    When the line is wider than ``width`` cells only the title is shortened (ending in ``…``, and
    dropped when not even that fits). The project, the log and the number are never cut, so the
    line may stay wider than ``width`` rather than lose them. It never raises.
    """
    head = f"{project}{SEPARATOR}{log}"
    if not number:
        return head
    head = f"{head}{SEPARATOR}{number}"
    title = " ".join((title or "").split())
    if not title:
        return head
    full = f"{head}: {title}"
    if cell_len(full) <= width:
        return full
    room = width - cell_len(head) - len(": ")
    if room < 1:
        return head
    return f"{head}: {set_cell_size(title, room - 1).rstrip()}…"


def actions_text(actions: Sequence[ActionLike], *, can_open: bool) -> str:
    """``[a] Answer  [c] Close  [Enter] Open record``; ``""`` for no action and no open."""
    cells = [f"[{key_label(action.key)}] {action.label}" for action in actions]
    if can_open:
        cells.append(OPEN_ACTION)
    return "  ".join(cells)


# --- columns (P1-UX3; skill tui-layout, "Logs") ---------------------------------------------

FLEX_NAMES = ("Subject", "Title")  # the column that takes the remaining width and shortens
CELL_PADDING = 2  # a table cell has one cell of padding on each side
SCROLLBAR = 2  # room kept for the table's vertical scrollbar
MIN_FLEX = 24  # the flexible column never shortens below this many cells
CRUMB_PADDING_CELLS = 4  # the screen's one-cell padding and the frame, each side


def flex_index(names: Sequence[str]) -> int | None:
    """The position of the Subject (or Title) column, ``None`` when the log has none."""
    for name in FLEX_NAMES:
        if name in names:
            return list(names).index(name)
    return None


def visible_columns(
    names: Sequence[str], rows: Sequence[Sequence[str]], keep: Sequence[str] = ()
) -> list[int]:
    """The positions of the columns to show: every column, except one that holds the same value
    in every one of two or more rows (``Kind`` when each RFI is a request for information).

    ``keep`` names the columns that always show (the number, the subject, the state). One row, or
    none, hides nothing: a single row has no variation to report.
    """
    everything = list(range(len(names)))
    if len(rows) < 2:
        return everything
    shown_ = [
        index
        for index in everything
        if names[index] in keep or len({row[index] for row in rows}) > 1
    ]
    return shown_ or everything


def fit_cell(text: str, width: int) -> str:
    """``text`` shortened to ``width`` cells with a closing ``…``; as it is when it fits."""
    if cell_len(text) <= width:
        return text
    return set_cell_size(text, max(width - 1, 1)).rstrip() + "…"


def flex_width(total: int, names: Sequence[str], rows: Sequence[Sequence[str]], flex: int) -> int:
    """The cells the flexible column may use in a table ``total`` cells wide: what is left after
    the other columns (each as wide as its widest cell or its heading), at least ``MIN_FLEX``."""
    used = SCROLLBAR + CELL_PADDING  # the flexible column's own padding
    for index, name in enumerate(names):
        if index == flex:
            continue
        used += CELL_PADDING + max([cell_len(name), *(cell_len(row[index]) for row in rows)])
    return max(total - used, MIN_FLEX)


def table_width(screen_width: int, *, wide: bool) -> int:
    """Roughly the cells the list gets: the screen less its padding, three fifths of that when
    the panel sits beside it (``log_text.is_wide``)."""
    inner = max(screen_width - CRUMB_PADDING_CELLS, 1)
    return inner * 3 // 5 if wide else inner
