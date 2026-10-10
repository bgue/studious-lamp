"""Messages that widgets post and the app (or a parent widget) handles (brief 10.1, 10.3).

Widgets never call each other directly. A widget posts one of these; the message bubbles up the
DOM, and `TlApp` (or the nearest interested ancestor) handles it with `on_<snake_case_name>`.
"""

from __future__ import annotations

from typing import Any, Literal

from textual.message import Message
from tl_core.ledger import Event

Severity = Literal["info", "warning", "error"]
ConnectionState = Literal["live", "reconnecting", "unreachable"]


class OpenRecord(Message):
    """The user asked to open a record (Enter or double-click on a grid row).

    ``follow`` is true when the user followed a reference (Links tab, trace, palette): the app then
    extends the back/forward trail instead of starting a new one.
    """

    def __init__(self, scope: str, key: str, *, follow: bool = False) -> None:
        super().__init__()
        self.scope = scope
        self.key = key
        self.follow = follow


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


class LiveEvents(Message):
    """Committed events from the change feed, oldest first (posted from the feed thread)."""

    def __init__(self, events: list[Event]) -> None:
        super().__init__()
        self.events = events


class ConnectionChanged(Message):
    """The link to the ledger or server changed: ``live``, ``reconnecting`` or ``unreachable``."""

    def __init__(self, state: ConnectionState, detail: str = "") -> None:
        super().__init__()
        self.state: ConnectionState = state
        self.detail = detail


class LedgerReset(Message):
    """The server's ledger is behind what this client had seen (replaced or restored)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__()
        self.detail = detail


class FilterSubmitted(Message):
    """The user pressed Enter in the filter bar with this query text (blank clears the filter)."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class FilterClosed(Message):
    """The user left the filter bar (Esc); focus returns to the grid."""
