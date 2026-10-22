"""Correspondence: the master register, the triage inbox and the response clocks (P1-I5).

A full-size modal opened with ``F5``, a ``LogScreen`` (P1-UX2-S3). Three views of one project's
correspondence, chosen with ``1``, ``2`` and ``3`` (or ``Tab``): the **register** lists every item,
with the lines of the domains' register sources (the I2 transmittals) among them; the **triage
inbox** lists the items that arrived and wait for a domain; the **clocks** view lists the open
response clocks, soonest due first, with the days left on the project calendar. The actions bar
offers what the server says the viewer may do to the highlighted item (``allowed_actions``); in the
triage inbox ``a`` accepts what the suggestion engine proposes. ``s`` records the warnings and
expiries that are due (a document controller's act; anyone else is refused by the service and told
so) and ``m`` shows the met and cancelled clocks too. Everything is read through the client, and a
letter above the person's clearance is simply not listed (ADR-0016).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from rich.text import Text
from textual.binding import Binding, BindingType
from textual.widgets import DataTable, Input
from tl_mod_correspondence.handlers.clocks import SweepClocks
from tl_mod_correspondence.handlers.triage import ConfirmTriage
from tl_mod_correspondence.views import ClockView, ItemView, RegisterLineView, SuggestionView

from tl_tui.client import ClientInterface
from tl_tui.correspondence_text import (
    CLOCK_COLUMNS,
    CLOCK_DROP,
    MODES,
    PLAIN_CLOCK_COLUMNS,
    REGISTER_COLUMNS,
    REGISTER_DROP,
    clock_cells,
    clock_page,
    item_page,
    next_mode,
    register_cells,
    summary_line,
)
from tl_tui.details.correspondence import direction_word
from tl_tui.display import Labels, humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import load_labels
from tl_tui.layout import Page, Section, identity_line, join_facts, prop, render, state_line
from tl_tui.log_actions import (
    ACTION_UI,
    ENVELOPE,
    ActionUi,
    Runner,
    log_actions,
    screen_runner,
    without_keys,
)
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

MAX_LINES = 500
LOG_NAMES = {
    "register": "Correspondence register",
    "inbox": "Triage inbox",
    "clocks": "Response clocks",
}
OWN_KEYS = frozenset({"1", "2", "3", "m", "s"})  # keys the screen binds: no action takes them


class CorrespondenceScreen(LogScreen[RegisterLineView | ClockView]):
    """The correspondence of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = LOG_NAMES["register"]
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("1-3 view", "m closed clocks", "/ filter")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("1  2  3  Tab", "Register, triage inbox, response clocks"),
        ("m", "Clocks: show the met and cancelled ones too"),
        ("s", "Record the warnings and expiries that are due (document controllers)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "mode('register')", "Register", show=False),
        Binding("2", "mode('inbox')", "Triage inbox", show=False),
        Binding("3", "mode('clocks')", "Clocks", show=False),
        Binding("tab", "next_mode", "Next view", show=False),
        Binding("m", "closed", "Closed clocks", show=False),
        Binding("s", "sweep", "Sweep", show=False),
    ]

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
        self.LOG_NAME = LOG_NAMES[self.mode]  # pyright: ignore[reportAttributeAccessIssue]
        self.closed_too = False
        self.lines: list[RegisterLineView] = []  # the register or the inbox, as listed
        self.clocks: list[ClockView] = []
        self.suggestion: SuggestionView | None = None  # for the highlighted inbox item
        self.labels: Labels = Labels()  # the domain and code labels, loaded with the first rows
        self._labelled = False
        self._flash = ""  # a note for the status line that the next reload would otherwise replace
        self._items: dict[str, tuple[ItemView, SuggestionView | None]] = {}
        self._panels: dict[tuple[str, bool], Text] = {}  # panels drawn since the last read

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        if self.mode == "clocks":
            return CLOCK_COLUMNS if mode_of(self.app).technical else PLAIN_CLOCK_COLUMNS
        return REGISTER_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return CLOCK_DROP if self.mode == "clocks" else REGISTER_DROP

    def load_rows(self) -> Sequence[RegisterLineView | ClockView]:
        if not self._labelled:
            self.labels = load_labels(
                self.client, f"project:{self.project}", ("correspondence.Correspondence",)
            )
            self._labelled = True
        self._items = {}
        self._panels = {}
        if self.mode == "clocks":
            self.clocks = self.client.list_clocks(self.project, open_only=not self.closed_too)
            return self.clocks
        inbox = self.mode == "inbox"
        self.lines = self.client.list_correspondence(
            self.project, state="Received" if inbox else None, sources=not inbox, limit=MAX_LINES
        )
        return self.lines

    def row_key(self, row: RegisterLineView | ClockView) -> str:
        return row.id

    def row_cells(self, row: RegisterLineView | ClockView) -> Sequence[str]:
        if isinstance(row, ClockView):
            return clock_cells(row, technical=mode_of(self.app).technical)
        return register_cells(row, self.labels)

    def row_record(self, row: RegisterLineView | ClockView) -> tuple[str, str]:
        if isinstance(row, ClockView):
            return (row.item_number, row.label)
        return (row.number, row.subject)

    def _detail(self, row: RegisterLineView) -> tuple[ItemView, SuggestionView | None]:
        """The item in full and, for a received item in the inbox, the suggested domain."""
        found = self._items.get(row.id)
        if found is None:
            item = self.client.get_correspondence(self.project, row.number)
            suggestion = None
            if self.mode == "inbox" and item.state == "Received":
                suggestion = self.client.get_correspondence_suggestion(self.project, row.number)
            found = self._items[row.id] = (item, suggestion)
        return found

    def panel_text(self, row: RegisterLineView | ClockView | None) -> str | Text:
        """The highlighted row in full (one read per row until the rows are read again)."""
        self.suggestion = None
        technical = mode_of(self.app).technical
        if row is None:
            return "Nothing here." if self.mode != "inbox" else "Nothing is waiting for triage."
        if isinstance(row, ClockView):
            return render(clock_page(row, self.labels, technical=technical))
        if row.kind != "item":
            return render(self._source_page(row))
        try:
            item, self.suggestion = self._detail(row)
            found = self._panels.get((row.id, technical))
            if found is None:
                found = self._panels[(row.id, technical)] = render(
                    item_page(
                        item,
                        self.suggestion,
                        self.labels,
                        technical=technical,
                        client=self.client,
                        project=self.project,
                    )
                )
        except CLIENT_ERRORS as exc:
            return describe_error(exc)
        return found

    @staticmethod
    def _source_page(row: RegisterLineView) -> Page:
        """A register line that is not an item (a transmittal): its few facts."""
        outgoing = row.direction == "out"
        with_ = f"{'to' if outgoing else 'from'} {row.counterparty}" if row.counterparty else ""
        facts = Section("Key facts", (prop("Kind", humanize(row.kind)), prop("Date", row.on)))
        return Page(
            identity_line(row.number, row.subject),
            state_line(humanize(row.state)),
            (facts,),
            join_facts(direction_word(row.direction), with_),
        )

    def actions_for(self, row: RegisterLineView | ClockView) -> Sequence[LogAction]:
        if isinstance(row, ClockView) or row.kind != "item":
            return []  # a clock or a register source line is not an item with actions
        offers = self.client.allowed_actions(row.id)
        item, found = self._detail(row)
        ui = without_keys(ACTION_UI, OWN_KEYS)
        if self.mode == "inbox" and found is not None and found.domain is not None:
            domain, subtype = found.domain, found.subtype or ""
            ui["ConfirmTriage"] = ActionUi(
                "a",
                build=lambda values, record_id, version: ConfirmTriage(
                    **ENVELOPE,
                    stream_id=record_id,
                    expected_version=version,
                    domain=domain,
                    subtype=subtype,
                ),
            )
        return log_actions(offers, ui, self._runner(), version=item.version)

    def _runner(self) -> Runner:
        return screen_runner(self, self.client, actor=self.actor, scope=f"project:{self.project}")

    def summary_text(self) -> str:
        if self._flash:
            flash, self._flash = self._flash, ""
            return flash
        return summary_line(self.mode, len(self.shown), closed_too=self.closed_too)

    def open_row(self, row: RegisterLineView | ClockView) -> None:
        """Enter on a row opens its full record; Esc on that screen comes back to this row."""
        open_record(self, self.client, f"project:{self.project}", self.project, self.actor, row.id)

    # --- views ---------------------------------------------------------------------------

    def _new_columns(self) -> None:
        table = self.query_one("#log-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.columns())

    def action_mode(self, mode: str) -> None:
        if mode in MODES and mode != self.mode:
            self.mode = mode
            self.LOG_NAME = LOG_NAMES[mode]  # pyright: ignore[reportAttributeAccessIssue]
            self.rows = []  # the rows of the other view are not rows of this one
            self._new_columns()
            self._fill(None)
            self.reload()

    def action_next_mode(self) -> None:
        self.action_mode(next_mode(self.mode))

    def action_closed(self) -> None:
        """Show the met and cancelled clocks too, or hide them again (clocks view)."""
        if self.mode != "clocks" or isinstance(self.focused, Input):
            return
        self.closed_too = not self.closed_too
        self.reload()

    def action_sweep(self) -> None:
        """Record the warnings and expiries that are due (a controller's act)."""
        if isinstance(self.focused, Input):
            return  # the key is text

        def sweep() -> None:
            done = self.client.correspondence_command(
                "SweepClocks",
                SweepClocks(actor=self.actor, source="tui", scope=f"project:{self.project}"),
            )
            self._flash = (
                f"Sweep recorded {len(done.events)} event(s)."  # shown once, at the reload
            )

        self.attempt(sweep)

    def refresh_for_display_mode(self) -> None:
        """Technical details came on or off: the clock columns change, the row is kept."""
        self._new_columns()
        super().refresh_for_display_mode()
