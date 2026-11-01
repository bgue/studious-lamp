"""Properties tab: values grouped by layer with enforcement markers (brief 6.3, sketch 2).

Reads only ``ClientInterface.form_metadata`` (with the record id, so the sets the record's class
binds are listed) and ``ClientInterface.conformance``. The text is built by ``psets_text`` (a pure
function, tested on its own); ``PsetsTab`` shows it. The schema hash shows in technical mode only.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
from tl_schema.forms import ConformanceReport, FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import StatusMessage
from tl_tui.properties_text import (  # noqa: F401 - the moved names stay importable from here
    _PLACEHOLDER,
    ADD_LINE,
    CUSTOM_RULE,
    HEADER,
    LEGEND,
    _name_of,
    _placeholder_value,
    _shown,
    adhoc_lines,
    psets_text,
    rule_text,
    unit_text,
    value_text,
)

__all__ = [
    "ADD_LINE",
    "CUSTOM_RULE",
    "HEADER",
    "LEGEND",
    "PsetsTab",
    "adhoc_lines",
    "psets_text",
    "rule_text",
    "unit_text",
    "value_text",
]


class PsetsTab(VerticalScroll, can_focus=True):
    """Rendered inside the record view's Properties tab. ``show_record`` (re)loads it."""

    DEFAULT_CSS = """
    PsetsTab { overflow-x: auto; padding: 0 1; }
    PsetsTab > #psets-body { width: auto; }
    PsetsTab > #psets-add { height: 1; color: $accent; }
    """
    KEY_HINTS: ClassVar[str] = "↑↓ scroll  Esc back"

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
        self.text: str = ""
        self._loaded: tuple[FormMetadata, ConformanceReport] | None = None

    def compose(self) -> ComposeResult:
        yield Static(ADD_LINE, id="psets-add", markup=False)
        yield Static("", id="psets-body", markup=False)

    def show_record(self, record: dict[str, Any]) -> None:
        """Load the form metadata and conformance for ``record`` and render the tab."""
        self.record = record
        self._loaded = None
        try:
            meta = self.client.form_metadata(self.scope, record["type"], record["id"])
            report = self.client.conformance(record["id"])
        except NotImplementedError:
            text = "Properties unavailable: the property services are not installed yet"
        except CLIENT_ERRORS as exc:
            text = f"Properties unavailable: {describe_error(exc)}"
            self.post_message(StatusMessage(describe_error(exc), "error"))
        else:
            self._loaded = (meta, report)
            text = psets_text(meta, record, report, technical=mode_of(self.app).technical)
        self._show(text)

    def refresh_for_display_mode(self) -> None:
        """Draw the same tab again with the current display mode; no client call."""
        if self.record is not None and self._loaded is not None:
            meta, report = self._loaded
            self._show(psets_text(meta, self.record, report, technical=mode_of(self.app).technical))

    def _show(self, text: str) -> None:
        self.text = text
        self.query_one("#psets-body", Static).update(text)
