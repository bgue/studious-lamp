"""Messages that widgets post and the app (or a parent widget) handles (brief 10.1, 10.3).

Widgets never call each other directly. A widget posts one of these; the message bubbles up the
DOM, and `TlApp` (or the nearest interested ancestor) handles it with `on_<snake_case_name>`.
"""

from __future__ import annotations

from typing import Any, Literal

from textual.message import Message

Severity = Literal["info", "warning", "error"]


class OpenRecord(Message):
    """The user asked to open a record (Enter or double-click on a grid row)."""

    def __init__(self, scope: str, key: str) -> None:
        super().__init__()
        self.scope = scope
        self.key = key


class RecordHighlighted(Message):
    """The grid cursor moved to a record (or to nothing, ``record is None``)."""

    def __init__(self, record: dict[str, Any] | None) -> None:
        super().__init__()
        self.record = record


class SelectionChanged(Message):
    """The set of multi-selected grid rows changed."""

    def __init__(self, record_ids: frozenset[str]) -> None:
        super().__init__()
        self.record_ids = record_ids

    @property
    def count(self) -> int:
        return len(self.record_ids)


class RecordChanged(Message):
    """A command succeeded for this record; views showing it should reload."""

    def __init__(self, record_id: str) -> None:
        super().__init__()
        self.record_id = record_id


class CloseRecord(Message):
    """Leave the record view and go back to the grid (Esc)."""


class StepRecord(Message):
    """Open the previous (``delta = -1``) or next (``delta = 1``) record of the grid's list."""

    def __init__(self, delta: int) -> None:
        super().__init__()
        self.delta = delta


class StatusMessage(Message):
    """Text for the footer status area. Errors from the client are posted this way."""

    def __init__(self, text: str, severity: Severity = "info") -> None:
        super().__init__()
        self.text = text
        self.severity: Severity = severity


class NavSelected(Message):
    """The user chose an entry of the navigation tree; ``view_id`` is the entry's data."""

    def __init__(self, view_id: str) -> None:
        super().__init__()
        self.view_id = view_id
