"""Psets tab: values grouped by layer with enforcement markers (brief 6.3, sketch 2).

STUB (P0-I2-T15): the constructor and `show_record` are final; the content is replaced by the
ticket.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from tl_tui.client import ClientInterface


class PsetsTab(VerticalScroll, can_focus=True):
    """Rendered inside the record view's Psets tab. ``show_record`` (re)loads it for a record."""

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        yield Static("Psets", id="psets-body", markup=False)

    def show_record(self, record: dict[str, Any]) -> None:
        self.record = record
