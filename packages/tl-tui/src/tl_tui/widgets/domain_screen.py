"""RFIs, Commercial notices and the evidence trail (P1-I6; brief 9 M10).

A full-size modal opened with ``Ctrl+G``. Three views of one project: the **RFI log** (``1``) with
the response times and impact flags, the **Commercial register** (``2``) with values by currency
and the time bars, and the **evidence trail** (``3``) of the item highlighted in either, as the
ledger knew it at the end of a day (``[`` and ``]`` step the day back and forward, ``0`` is today).
Everything is read through the client: a plain person's Commercial register is empty because the
items are restricted, and the trail leaves out what the person may not read today (ADR-0016).
The screen changes nothing.
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_mod_correspondence.evidence import EvidenceTrail
from tl_mod_correspondence.reports_commercial import CommercialLine, CommercialRegister
from tl_mod_correspondence.reports_technical import RfiLog, RfiLogLine

from tl_tui.client import ClientInterface
from tl_tui.commercial_text import (
    COMMERCIAL_COLUMNS,
    commercial_cells,
    commercial_lines,
    commercial_summary,
)
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.evidence_text import (
    EVIDENCE_COLUMNS,
    evidence_title,
    node_cells,
    node_lines,
    step_day,
)
from tl_tui.rfi_text import RFI_COLUMNS, rfi_cells, rfi_lines, rfi_summary

MODES = ("rfi", "commercial", "evidence")
MODE_TITLES = {"rfi": "RFI log", "commercial": "Commercial register", "evidence": "Evidence"}
MAX_LINES = 500
NO_COMMERCIAL = "Commercial items are for document controllers and admins; none is listed for you."


class DomainScreen(ModalScreen[None]):
    """The Technical and Commercial domains of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "1 RFI log  2 Commercial  3 evidence (e on a row)  o open  v overdue/bars  i impact  "
        "[ ] day  0 today  r reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "mode('rfi')", "RFI log", show=False),
        Binding("2", "mode('commercial')", "Commercial", show=False),
        Binding("3", "mode('evidence')", "Evidence", show=False),
        Binding("tab", "next_mode", "Next view", show=False),
        Binding("o", "switch('open')", "Open only", show=False),
        Binding("v", "switch('narrow')", "Overdue or bars", show=False),
        Binding("i", "switch('impact')", "Impact", show=False),
        Binding("e", "evidence", "Evidence", show=False),
        Binding("left_square_bracket", "day(-1)", "Earlier", show=False),
        Binding("right_square_bracket", "day(1)", "Later", show=False),
        Binding("0", "today", "Today", show=False),
        Binding("r", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    DomainScreen { background: $surface; }
    DomainScreen > Vertical { padding: 0 1; }
    DomainScreen #dom-title { text-style: bold; height: 1; }
    DomainScreen #dom-table { height: 1fr; min-height: 6; }
    DomainScreen #dom-detail { height: 12; border-top: solid $accent; padding: 0 1; }
    DomainScreen #dom-status { height: 1; }
    DomainScreen #dom-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        actor: str,
        *,
        is_controller: bool = False,
        mode: str = "rfi",
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.is_controller = is_controller
        self.mode = mode if mode in MODES else "rfi"
        self.only_open = False
        self.narrow = False  # RFI: overdue only; Commercial: running or late bars only
        self.impact = False  # RFI: an impact flag of yes only
        self.today = date.today()
        self.as_of = self.today
        self.number: str | None = None  # the item the evidence view is about
        self.rfi_log: RfiLog | None = None
        self.notices: CommercialRegister | None = None
        self.trail: EvidenceTrail | None = None

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="dom-title")
            yield DataTable[str](id="dom-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="dom-detail")
            yield Static("", markup=False, id="dom-status")
            yield Static(self.KEY_HINTS, markup=False, id="dom-hints")

    def on_mount(self) -> None:
        self.reload()
        self.query_one("#dom-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the current view again and keep the highlighted row where it is."""
        keep = self._key()
        table = self.query_one("#dom-table", DataTable)
        table.clear(columns=True)
        columns = {
            "rfi": RFI_COLUMNS,
            "commercial": COMMERCIAL_COLUMNS,
            "evidence": EVIDENCE_COLUMNS,
        }
        table.add_columns(*columns[self.mode])
        title = f"{MODE_TITLES[self.mode]} of {self.project}   [1 2 3]"
        rows: list[tuple[str, tuple[str, ...]]] = []
        summary = ""
        try:
            if self.mode == "rfi":
                self.rfi_log = self.client.list_rfis(
                    self.project,
                    only_open=self.only_open,
                    only_overdue=self.narrow,
                    only_impact=self.impact,
                    limit=MAX_LINES,
                )
                rows = [(x.id, rfi_cells(x)) for x in self.rfi_log.lines]
                summary = rfi_summary(
                    self.rfi_log,
                    only_open=self.only_open,
                    only_overdue=self.narrow,
                    only_impact=self.impact,
                )
            elif self.mode == "commercial":
                self.notices = self.client.list_commercial(
                    self.project,
                    only_open=self.only_open,
                    time_bars_only=self.narrow,
                    limit=MAX_LINES,
                )
                rows = [(x.id, commercial_cells(x)) for x in self.notices.lines]
                summary = commercial_summary(
                    self.notices, only_open=self.only_open, time_bars_only=self.narrow
                )
                if not rows and not self.is_controller:
                    summary = NO_COMMERCIAL
            else:
                title = evidence_title(self.number or "-", self.as_of.isoformat())
                self.trail = None
                if self.number is None:
                    summary = "Highlight an RFI or a notice and press e."
                else:
                    self.trail = self.client.get_evidence_trail(
                        self.project, self.number, as_of=self.as_of
                    )
                    title = evidence_title(self.number, self.trail.as_of)
                    rows = [(n.record_id, node_cells(n)) for n in self.trail.nodes]
                    summary = f"{len(rows)} record{'s' if len(rows) != 1 else ''} in the trail" + (
                        " (cut short by a bound)" if self.trail.truncated else ""
                    )
        except CLIENT_ERRORS as exc:
            self.query_one("#dom-title", Static).update(title)
            self._say(describe_error(exc), error=True)
            self.query_one("#dom-detail", Static).update("")
            return
        self.query_one("#dom-title", Static).update(title)
        for key, cells in rows:
            table.add_row(*(Text(cell) for cell in cells), key=key)
        keys = [key for key, _ in rows]
        if keys:
            table.move_cursor(row=keys.index(keep) if keep in keys else 0)
        self._say(summary)
        self._describe()

    def _rows(self) -> list[RfiLogLine] | list[CommercialLine] | list[str]:
        if self.mode == "rfi":
            return self.rfi_log.lines if self.rfi_log is not None else []
        if self.mode == "commercial":
            return self.notices.lines if self.notices is not None else []
        return [n.record_id for n in self.trail.nodes] if self.trail is not None else []

    def _key(self) -> str | None:
        table = self.query_one("#dom-table", DataTable)
        rows = self._rows()
        if not rows or not 0 <= table.cursor_row < len(rows):
            return None
        row = rows[table.cursor_row]
        return row if isinstance(row, str) else row.id

    def current_number(self) -> str | None:
        """The number of the highlighted RFI or notice (``None`` in the evidence view)."""
        table = self.query_one("#dom-table", DataTable)
        rows = self._rows()
        if self.mode == "evidence" or not 0 <= table.cursor_row < len(rows):
            return None
        row = rows[table.cursor_row]
        return None if isinstance(row, str) else row.number

    def _describe(self) -> None:
        """Show the highlighted row in full (one read per row)."""
        detail = self.query_one("#dom-detail", Static)
        table = self.query_one("#dom-table", DataTable)
        if self.mode == "evidence":
            nodes = self.trail.nodes if self.trail is not None else []
            if 0 <= table.cursor_row < len(nodes):
                detail.update("\n".join(node_lines(nodes[table.cursor_row])))
            else:
                detail.update("Nothing here.")
            return
        number = self.current_number()
        if number is None:
            detail.update("Nothing here.")
            return
        try:
            if self.mode == "rfi":
                detail.update("\n".join(rfi_lines(self.client.get_rfi(self.project, number))))
            else:
                detail.update(
                    "\n".join(commercial_lines(self.client.get_commercial(self.project, number)))
                )
        except CLIENT_ERRORS as exc:
            detail.update(describe_error(exc))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#dom-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def action_mode(self, mode: str) -> None:
        if mode in MODES and mode != self.mode:
            if mode == "evidence" and self.number is None:
                self.number = self.current_number()
            self.mode = mode
            self.reload()

    def action_next_mode(self) -> None:
        self.action_mode(MODES[(MODES.index(self.mode) + 1) % len(MODES)])

    def action_switch(self, what: str) -> None:
        """``open`` limits both lists to items still open; ``narrow`` to the overdue RFIs or the
        running or late time bars; ``impact`` (RFI log) to answers that say yes."""
        if self.mode == "evidence" or (what == "impact" and self.mode != "rfi"):
            return
        if what == "open":
            self.only_open = not self.only_open
        elif what == "narrow":
            self.narrow = not self.narrow
        else:
            self.impact = not self.impact
        self.reload()

    def action_evidence(self) -> None:
        """The evidence trail of the highlighted RFI or notice, as of the day shown."""
        number = self.current_number()
        if number is None:
            self._say("Highlight an RFI or a notice in view 1 or 2 first.")
            return
        self.number = number
        self.mode = "evidence"
        self.reload()

    def action_day(self, step: int) -> None:
        self.as_of = step_day(self.as_of, step, self.today)
        if self.mode == "evidence":
            self.reload()
        else:
            self._say(f"Evidence will be read as of {self.as_of.isoformat()}.")

    def action_today(self) -> None:
        self.as_of = self.today
        if self.mode == "evidence":
            self.reload()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)
