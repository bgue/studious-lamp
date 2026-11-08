"""Insights tab of the record view (P2-INS): a stub pane that T03 fills.

For now it shows the word "Insights" and keeps the record it was given; nothing else.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class InsightsTab(Vertical):
    """Holds the record shown in the record view; the body is filled by a later ticket."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(id=id)
        self.record: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Static("Insights", id="insights-body", markup=False)

    def show_record(self, record: dict[str, Any]) -> None:
        """Remember the record; nothing is drawn yet."""
        self.record = record
