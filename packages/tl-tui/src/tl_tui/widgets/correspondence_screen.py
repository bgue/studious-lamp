"""Correspondence: the master register, the triage inbox and the response clocks (P1-I5).

A full-size modal opened with ``F5``. Three views of one project's correspondence, chosen with
``1``, ``2`` and ``3`` (or ``Tab``): the **register** lists every item, with the lines of the
domains' register sources (the I2 transmittals) among them; the **triage inbox** lists the items
that arrived and wait for a domain, and ``a`` accepts what the suggestion engine proposes for the
highlighted one; the **clocks** view lists the open response clocks, soonest due first, with the
days left on the project calendar. ``s`` records the warnings and expiries that are due (a
document controller's act; anyone else is refused by the service and told so). Everything is read
through the client, and a letter above the person's clearance is simply not listed (ADR-0016).
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_mod_correspondence.handlers.clocks import SweepClocks
from tl_mod_correspondence.handlers.triage import ConfirmTriage
from tl_mod_correspondence.views import ClockView, RegisterLineView, SuggestionView

from tl_tui.client import ClientInterface
from tl_tui.correspondence_text import (
    CLOCK_COLUMNS,
    MODE_TITLES,
    MODES,
    REGISTER_COLUMNS,
    clock_cells,
    clock_lines,
    item_lines,
    next_mode,
    register_cells,
    suggestion_text,
    summary_line,
)
from tl_tui.errors import CLIENT_ERRORS, describe_error

MAX_LINES = 500


class CorrespondenceScreen(ModalScreen[None]):
    """The correspondence of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "1 register  2 triage inbox  3 clocks  a accept suggestion  c closed clocks  "
        "s sweep  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "mode('register')", "Register", show=False),
        Binding("2", "mode('inbox')", "Triage inbox", show=False),
        Binding("3", "mode('clocks')", "Clocks", show=False),
        Binding("tab", "next_mode", "Next view", show=False),
        Binding("a", "accept", "Accept", show=False),
        Binding("c", "closed", "Closed clocks", show=False),
        Binding("s", "sweep", "Sweep", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    CorrespondenceScreen { background: $surface; }
    CorrespondenceScreen > Vertical { padding: 0 1; }
    CorrespondenceScreen #corr-title { text-style: bold; height: 1; }
    CorrespondenceScreen #corr-table { height: 1fr; min-height: 6; }
    CorrespondenceScreen #corr-detail { height: 12; border-top: solid $accent; padding: 0 1; }
    CorrespondenceScreen #corr-status { height: 1; }
    CorrespondenceScreen #corr-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        actor: str,
        *,
        is_controller: bool = False,
        mode: str = "register",
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.is_controller = is_controller  # an admin or a document controller (ADR-0013)
        self.mode = mode if mode in MODES else "register"
        self.closed_too = False
        self.lines: list[RegisterLineView] = []  # the register or the inbox, as listed
        self.clocks: list[ClockView] = []
        self.suggestion: SuggestionView | None = None  # for the highlighted inbox item

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="corr-title")
            yield DataTable[str](id="corr-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="corr-detail")
            yield Static("", markup=False, id="corr-status")
            yield Static(self.KEY_HINTS, markup=False, id="corr-hints")

    def on_mount(self) -> None:
        self.reload()
        self.query_one("#corr-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the current view again and keep the highlighted row where it is."""
        keep = self._key()
        table = self.query_one("#corr-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*(CLOCK_COLUMNS if self.mode == "clocks" else REGISTER_COLUMNS))
        self.query_one("#corr-title", Static).update(
            f"{MODE_TITLES[self.mode]} of {self.project}   [1 2 3]"
        )
        try:
            if self.mode == "clocks":
                self.clocks = self.client.list_clocks(self.project, open_only=not self.closed_too)
                rows = [(c.id, clock_cells(c)) for c in self.clocks]
            else:
                inbox = self.mode == "inbox"
                self.lines = self.client.list_correspondence(
                    self.project,
                    state="Received" if inbox else None,
                    sources=not inbox,
                    limit=MAX_LINES,
                )
                rows = [(line.id, register_cells(line)) for line in self.lines]
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        for key, cells in rows:
            table.add_row(*(Text(cell) for cell in cells), key=key)
        keys = [key for key, _ in rows]
        if keys:
            table.move_cursor(row=keys.index(keep) if keep in keys else 0)
        self._say(summary_line(self.mode, len(keys), closed_too=self.closed_too))
        self._describe()

    def _key(self) -> str | None:
        table = self.query_one("#corr-table", DataTable)
        rows = self.clocks if self.mode == "clocks" else self.lines
        if not rows or not 0 <= table.cursor_row < len(rows):
            return None
        return rows[table.cursor_row].id

    def current_line(self) -> RegisterLineView | None:
        table = self.query_one("#corr-table", DataTable)
        if self.mode == "clocks" or not 0 <= table.cursor_row < len(self.lines):
            return None
        return self.lines[table.cursor_row]

    def current_clock(self) -> ClockView | None:
        table = self.query_one("#corr-table", DataTable)
        if self.mode != "clocks" or not 0 <= table.cursor_row < len(self.clocks):
            return None
        return self.clocks[table.cursor_row]

    def _describe(self) -> None:
        """Show the highlighted row in full (one read per row)."""
        detail = self.query_one("#corr-detail", Static)
        self.suggestion = None
        clock = self.current_clock()
        if clock is not None:
            detail.update("\n".join(clock_lines(clock)))
            return
        line = self.current_line()
        if line is None:
            detail.update(
                "Nothing here." if self.mode != "inbox" else "Nothing is waiting for triage."
            )
            return
        if line.kind != "item":
            detail.update(f"{line.number}  {line.state}  {line.subject}  ({line.kind})")
            return
        try:
            item = self.client.get_correspondence(self.project, line.number)
            if self.mode == "inbox" and item.state == "Received":
                self.suggestion = self.client.get_correspondence_suggestion(
                    self.project, line.number
                )
        except CLIENT_ERRORS as exc:
            detail.update(describe_error(exc))
            return
        detail.update("\n".join(item_lines(item, self.suggestion)))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#corr-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def action_mode(self, mode: str) -> None:
        if mode in MODES and mode != self.mode:
            self.mode = mode
            self.reload()

    def action_next_mode(self) -> None:
        self.action_mode(next_mode(self.mode))

    def action_accept(self) -> None:
        """Confirm the triage the suggestion engine proposes for the highlighted inbox item."""
        line = self.current_line()
        found = self.suggestion
        if self.mode != "inbox" or line is None or found is None or found.domain is None:
            self._say("Choose an item in the triage inbox that has a suggestion (key 2).")
            return
        try:
            item = self.client.get_correspondence(self.project, line.number)
            self.client.correspondence_command(
                "ConfirmTriage",
                ConfirmTriage(
                    actor=self.actor,
                    source="tui",
                    scope=f"project:{self.project}",
                    stream_id=item.id,
                    expected_version=item.version,
                    domain=found.domain,
                    subtype=found.subtype or "",
                ),
            )
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self.reload()
        self._say(f"Triaged {line.number} as {suggestion_text(found).split(' (')[0]}.")

    def action_closed(self) -> None:
        """Show the met and cancelled clocks too, or hide them again (clocks view)."""
        if self.mode != "clocks":
            return
        self.closed_too = not self.closed_too
        self.reload()

    def action_sweep(self) -> None:
        """Record the warnings and expiries that are due (a controller's act)."""
        try:
            done = self.client.correspondence_command(
                "SweepClocks",
                SweepClocks(actor=self.actor, source="tui", scope=f"project:{self.project}"),
            )
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self.reload()
        self._say(f"Sweep recorded {len(done.events)} event(s).")

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)
