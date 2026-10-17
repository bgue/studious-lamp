"""The comparison of two snapshots of a schedule: what moved, eroded and changed (P1-I4).

A full-size modal opened from the schedule screen with ``c``. The header says which snapshots
are compared and how far the data date and the project finish moved; below it, one section of the
comparison at a time (added, removed, date shifts, float, logic, progress, durations, critical),
with the full count of every section in the tab line. ``Right``/``Left`` (or ``n``/``b``) move to
the next or previous section, ``Esc`` closes. Everything is read through the client; the screen
shows what the module found and decides nothing.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static
from tl_mod_schedule.compare import Comparison

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schedule_text import (
    COMPARE_SECTIONS,
    compare_header_lines,
    compare_section_lines,
    compare_tabs,
)


class CompareScreen(ModalScreen[None]):
    """``new`` against the snapshot before it (``old`` names another one) of schedule ``code``."""

    KEY_HINTS: ClassVar[str] = "Right/n next section  Left/b previous  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("right,n", "next_section", "Next", show=False),
        Binding("left,b", "previous_section", "Previous", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    CompareScreen { background: $surface; }
    CompareScreen > Vertical { padding: 0 1; }
    CompareScreen #cp-title { text-style: bold; height: 1; }
    CompareScreen #cp-header { height: 3; }
    CompareScreen #cp-tabs { height: 1; }
    CompareScreen #cp-body { height: 1fr; border-top: solid $accent; padding: 0 1; }
    CompareScreen #cp-status { height: 1; }
    CompareScreen #cp-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        code: str,
        new: int,
        old: int | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.code = code
        self.new = new
        self.old = old
        self.section = 0  # an index into COMPARE_SECTIONS
        self.comparison: Comparison | None = None

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Comparison of {self.code}#{self.new}", markup=False, id="cp-title")
            yield Static("", markup=False, id="cp-header")
            yield Static("", markup=False, id="cp-tabs")
            with VerticalScroll(id="cp-scroll"):
                yield Static("", markup=False, id="cp-body")
            yield Static("", markup=False, id="cp-status")
            yield Static(self.KEY_HINTS, markup=False, id="cp-hints")

    def on_mount(self) -> None:
        self.reload()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the comparison again and show the section the screen was on."""
        try:
            self.comparison = self.client.compare_snapshots(
                self.project, self.code, new=self.new, old=self.old
            )
        except CLIENT_ERRORS as exc:
            self.comparison = None
            self.query_one("#cp-header", Static).update("")
            self.query_one("#cp-tabs", Static).update("")
            message = describe_error(exc)
            self.query_one("#cp-body", Static).update(message)
            self._say(message, error=True)
            return
        self._show()

    def _show(self) -> None:
        """The header, the tab line (the section on view in brackets) and the section's rows."""
        c = self.comparison
        if c is None:
            return
        self.query_one("#cp-header", Static).update("\n".join(compare_header_lines(c)))
        labels = compare_tabs(c)
        labels[self.section] = f"[{labels[self.section]}]"
        self.query_one("#cp-tabs", Static).update("  ".join(labels))
        name, title = COMPARE_SECTIONS[self.section]
        rows = [f"{title}:", *compare_section_lines(c, name)]
        self.query_one("#cp-body", Static).update("\n".join(rows))
        position = f"section {self.section + 1} of {len(COMPARE_SECTIONS)}"
        if c.cut:
            position += "  (the lists were cut; the counts are exact)"
        self._say(position)

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#cp-status", Static).update(("! " if error else "") + text)

    # --- actions -------------------------------------------------------------------------

    def action_next_section(self) -> None:
        self.section = (self.section + 1) % len(COMPARE_SECTIONS)
        self._show()

    def action_previous_section(self) -> None:
        self.section = (self.section - 1) % len(COMPARE_SECTIONS)
        self._show()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)
