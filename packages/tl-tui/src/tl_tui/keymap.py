"""The key map as data: every documented key, the widget that implements it, and the help text.

The help screen (`F1`, `?`) renders `help_text()`. The tests check that each entry with an owner
names a real binding on that owner's class, so the documented keys cannot drift from the code
(P0-I2-T17b; brief 10.3 and 10.4).
"""

from __future__ import annotations

from dataclasses import dataclass

CONTEXTS: tuple[str, ...] = ("App", "Grid", "Record view", "Forms")


@dataclass(frozen=True)
class KeyEntry:
    """One documented key. ``owner`` is the class that implements it, or ``None`` for keys
    Textual provides; ``binding`` is that class's binding key string, or ``None``."""

    context: str
    keys: str
    description: str
    owner: str | None = None
    binding: str | None = None


KEYMAP: tuple[KeyEntry, ...] = (
    KeyEntry("App", "F1  ?", "Show this key map", "TlApp", "f1"),
    KeyEntry("App", "F2", "Show or hide the navigation panel", "TlApp", "f2"),
    KeyEntry("App", "F3", "Show or hide the context panel", "TlApp", "f3"),
    KeyEntry("App", "F6  Shift+F6", "Move focus between panels", "TlApp", "f6"),
    KeyEntry("App", "n", "New record", "TlApp", "n"),
    KeyEntry("App", "Esc", "Close an open side panel (narrow terminals)", "TlApp", "escape"),
    KeyEntry("App", "Ctrl+Q", "Quit"),
    KeyEntry(
        "Grid",
        "Up Down PgUp PgDn Home End",
        "Move the cursor",
        "RecordGrid",
        "up",
    ),
    KeyEntry("Grid", "Left Right", "Choose the column to sort by", "RecordGrid", "left"),
    KeyEntry("Grid", "Space", "Select or unselect the row", "RecordGrid", "space"),
    KeyEntry(
        "Grid",
        "Shift+Up Shift+Down",
        "Extend the selection",
        "RecordGrid",
        "shift+down",
    ),
    KeyEntry("Grid", "Ctrl+A", "Select all loaded rows", "RecordGrid", "ctrl+a"),
    KeyEntry("Grid", "Enter", "Open the record", "RecordGrid", "enter"),
    KeyEntry(
        "Grid",
        "s",
        "Sort by the chosen column (again: descending, then off)",
        "RecordGrid",
        "s",
    ),
    KeyEntry("Grid", "c", "Choose columns", "RecordGrid", "c"),
    KeyEntry("Grid", "y", "Copy the selection as TSV", "RecordGrid", "y"),
    KeyEntry("Grid", "r", "Reload the rows", "RecordGrid", "r"),
    KeyEntry("Record view", "Esc", "Back to the grid", "RecordView", "escape"),
    KeyEntry(
        "Record view",
        "[  ]",
        "Previous or next record in the list",
        "RecordView",
        "left_square_bracket",
    ),
    KeyEntry("Record view", "h", "Show the History tab", "RecordView", "h"),
    KeyEntry("Record view", "e", "Edit the record", "RecordView", "e"),
    KeyEntry("Forms", "Tab  Shift+Tab", "Next or previous field"),
    KeyEntry(
        "Forms",
        "Ctrl+S",
        "Save (edit form) or create (new record)",
        "EditForm",
        "ctrl+s",
    ),
    KeyEntry("Forms", "Esc", "Cancel", "EditForm", "escape"),
)


def help_text() -> str:
    """Plain-text key map: a heading per context, one indented line per entry, blank lines
    between contexts."""
    blocks: list[str] = []
    for context in CONTEXTS:
        lines = [context]
        lines.extend(
            f"  {entry.keys:<30}{entry.description}" for entry in KEYMAP if entry.context == context
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
