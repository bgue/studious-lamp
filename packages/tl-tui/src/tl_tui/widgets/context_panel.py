"""Context panel (right panel): follows the grid cursor and shows the record's summary (sketch 1).

STUB (P0-I2-T12b): the public interface is final; the content is replaced by the ticket.
"""

from __future__ import annotations

from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Static


class ContextPanel(VerticalScroll, can_focus=True):
    """Shows the record passed to `show_record`, or an empty hint when it is ``None``."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(id=id)
        self.record: dict[str, Any] | None = None

    def compose(self):  # noqa: ANN201
        yield Static("No record", id="context-body")

    def show_record(self, record: dict[str, Any] | None) -> None:
        self.record = record
        text = "No record" if record is None else f"{record['key']}  v{record['version']}"
        self.query_one("#context-body", Static).update(text)
