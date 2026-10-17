# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""The comparison of two snapshots of a schedule: what moved, eroded and changed (P1-I4).

A full-size modal opened from the schedule screen with ``c``. The header says which snapshots
are compared and how far the data date and the project finish moved; below it, one section of the
comparison at a time (added, removed, date shifts, float, logic, progress, durations, critical),
with the full count of every section in the tab line. ``Right``/``Left`` (or ``n``/``b``) move to
the next or previous section, ``Esc`` closes. Everything is read through the client; the screen
shows what the module found and decides nothing.


STUB (P1-I4-T09a2): `reload` and `_show` are `NotImplementedError`; the layout, the bindings, the
actions and the text helpers (`tl_tui/schedule_text.py`) are written. The ticket fills the two
bodies by their STEPS comments.
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
        # STEPS
        # 1. Read `self.comparison = self.client.compare_snapshots(self.project,
        #    self.code, new=self.new, old=self.old)`.
        # 2. On `CLIENT_ERRORS`: set `self.comparison = None`, clear `#cp-header` and
        #    `#cp-tabs`, write `describe_error(exc)` to `#cp-body` and (as an error) to
        #    the status line, and return.
        # 3. Otherwise call `self._show()`.
        raise NotImplementedError

    def _show(self) -> None:
        """The header, the tab line (the section on view in brackets) and the section's rows."""
        # STEPS
        # 1. With no `self.comparison` return. Write `compare_header_lines(c)` joined by
        #    newlines to `#cp-header`.
        # 2. The tab line: `compare_tabs(c)` with the label of the section on view
        #    (`self.section`) in square brackets, joined by two spaces, written to
        #    `#cp-tabs`.
        # 3. `name, title = COMPARE_SECTIONS[self.section]`; write `title` and a colon
        #    on a first line, then `compare_section_lines(c, name)`, joined by newlines,
        #    to `#cp-body`.
        # 4. Say `section <n> of <how many>` (n counts from 1), followed by `  (the
        #    lists were cut; the counts are exact)` when `c.cut`.
        raise NotImplementedError

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
