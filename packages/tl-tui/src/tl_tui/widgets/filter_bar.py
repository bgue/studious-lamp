"""Filter bar: query-language text above the grid, with its result line (brief 10.2, P0-I4).

STUB (P0-I4-T60): names, signatures and docstrings are final; the bodies raise
``NotImplementedError``. Remove this paragraph when you implement it.

The bar only collects text and shows a result. `Enter` posts `FilterSubmitted(text)`; `Esc` posts
`FilterClosed`. The app sends the text to `RecordGrid.apply_filter` and hands the `FilterResult`
back through `show_result`: a count, or the parser's message with a caret under the character it
stopped at. The bar does not parse anything.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Input

from tl_tui.widgets.grid import FilterResult

INPUT_OFFSET = 1  # cells between the bar's left edge and the first character of the text
PLACEHOLDER = "status:open  title~bevel  linked:NCR  psets.nde.method=RT   (Enter applies)"


def result_line(result: FilterResult) -> str:
    """ "" for a cleared filter, "3 matches", or "✗ <message> (position n)"."""
    raise NotImplementedError("STUB (P0-I4-T60)")


def caret_line(text: str, position: int | None) -> str:
    """Spaces up to the column of ``text[position]`` in the input, then ``^``; "" without one."""
    raise NotImplementedError("STUB (P0-I4-T60)")


class FilterBar(Vertical):
    """An input line, a result line and a caret line. Hidden until `show_bar()`."""

    KEY_HINTS: ClassVar[str] = "Enter apply  Esc close  blank clears the filter"

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close_bar", show=False)]

    DEFAULT_CSS = """
    FilterBar { height: auto; display: none; background: $panel; }
    FilterBar Input, FilterBar Input:focus { border: none; padding: 0 1; height: 1; }
    FilterBar Static { height: auto; }
    """

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(id=id)
        self._text = ""

    def compose(self) -> ComposeResult:
        raise NotImplementedError("STUB (P0-I4-T60)")

    @property
    def value(self) -> str:
        """The text in the input."""
        raise NotImplementedError("STUB (P0-I4-T60)")

    def set_text(self, text: str) -> None:
        raise NotImplementedError("STUB (P0-I4-T60)")

    def show_bar(self) -> None:
        """Show the bar and put the cursor in the input."""
        raise NotImplementedError("STUB (P0-I4-T60)")

    def hide_bar(self) -> None:
        """Hide the bar (the text and the last result stay for the next `show_bar`)."""
        raise NotImplementedError("STUB (P0-I4-T60)")

    def show_result(self, result: FilterResult) -> None:
        """Show the count, or the error with a caret under the character the parser stopped at."""
        raise NotImplementedError("STUB (P0-I4-T60)")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raise NotImplementedError("STUB (P0-I4-T60)")

    def action_close_bar(self) -> None:
        raise NotImplementedError("STUB (P0-I4-T60)")
