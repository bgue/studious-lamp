"""Connection banner: one line under the header while the ledger or server cannot be reached.

Hidden when the connection is live (it takes no space then). The meaning is in the words and the
leading symbol, never in the colour alone (brief 10.3).
"""

from __future__ import annotations

from textual.widgets import Static

from tl_tui.messages import ConnectionState

_TEXT: dict[ConnectionState, str] = {
    "live": "",
    "reconnecting": "! Connection lost; reconnecting. Changes made meanwhile show when it is back",
    "unreachable": "✗ Server unreachable; retrying. What is shown may be out of date.",
}


def banner_text(state: ConnectionState, detail: str = "") -> str:
    """The banner line for ``state`` (empty for ``live``), with ``detail`` appended when given."""
    text = _TEXT[state]
    if text and detail:
        text = f"{text} ({detail})"
    return text


class ConnectionBanner(Static):
    """Shows `banner_text` and hides itself while the connection is live."""

    DEFAULT_CSS = """
    ConnectionBanner { dock: top; height: 1; background: $error 60%; color: $text; display: none; }
    """

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__("", markup=False, id=id)
        self.state: ConnectionState = "live"

    def show(self, state: ConnectionState, detail: str = "") -> None:
        self.state = state
        text = banner_text(state, detail)
        self.update(text)
        self.display = bool(text)
