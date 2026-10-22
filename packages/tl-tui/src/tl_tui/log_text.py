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
