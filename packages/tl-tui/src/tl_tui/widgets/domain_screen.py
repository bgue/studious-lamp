"""RFIs, Commercial notices and the evidence trail (P1-I6; brief 9 M10).

A full-size modal opened with ``Ctrl+G``, a ``LogScreen`` (P1-UX2-S3). Three views of one project:
the **RFI log** (``1``) with the response times and impact flags, the **Commercial register**
(``2``) with values by currency and the time bars, and the **evidence trail** (``3``) of the item
highlighted in either, as the ledger knew it at the end of a day (``[`` and ``]`` step the day back
and forward, ``0`` is today; ``t`` opens the trail of the highlighted row). Everything is read
through the client: a plain person's Commercial register is empty because the items are restricted,
and the trail leaves out what the person may not read today (ADR-0016). The actions bar offers what
the server says the viewer may do to the highlighted RFI or notice (``allowed_actions``; for an RFI
``a`` answers, ``c`` closes, ``e`` escalates); the trail changes nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import DataTable
from tl_mod_correspondence.evidence import EvidenceNode, EvidenceTrail
from tl_mod_correspondence.reports_commercial import CommercialLine, CommercialRegister
from tl_mod_correspondence.reports_technical import RfiLog, RfiLogLine

from tl_tui.client import ClientInterface
from tl_tui.commercial_text import (
    COMMERCIAL_COLUMNS,
    commercial_cells,
    commercial_lines,
    commercial_summary,
)
from tl_tui.display import Labels, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.evidence_text import (
    EVIDENCE_COLUMNS,
    evidence_title,
    node_cells,
    node_lines,
    step_day,
)
from tl_tui.labels_load import load_labels
from tl_tui.log_actions import ACTION_UI, Runner, log_actions, screen_runner, without_keys
from tl_tui.rfi_text import RFI_COLUMNS, rfi_cells, rfi_lines, rfi_summary
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

MODES = ("rfi", "commercial", "evidence")
MODE_TITLES = {"rfi": "RFI log", "commercial": "Commercial register", "evidence": "Evidence"}
MAX_LINES = 500
NO_COMMERCIAL = "Commercial items are for document controllers and admins; none is listed for you."
OWN_KEYS = frozenset({"1", "2", "3", "o", "v", "i", "t", "0"})  # keys the screen binds itself

Row = RfiLogLine | CommercialLine | EvidenceNode


class DomainScreen(LogScreen[Row]):
    """The Technical and Commercial domains of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = MODE_TITLES["rfi"]
    KEY_HINTS: ClassVar[str] = (
        "1 RFI log  2 Commercial  3 evidence (t on a row)  o open  v overdue/bars  i impact  "
        "[ ] day  0 today  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "mode('rfi')", "RFI log", show=False),
        Binding("2", "mode('commercial')", "Commercial", show=False),
        Binding("3", "mode('evidence')", "Evidence", show=False),
        Binding("tab", "next_mode", "Next view", show=False),
        Binding("o", "switch('open')", "Open only", show=False),
        Binding("v", "switch('narrow')", "Overdue or bars", show=False),
        Binding("i", "switch('impact')", "Impact", show=False),
        Binding("t", "evidence", "Evidence", show=False),
        Binding("left_square_bracket", "day(-1)", "Earlier", show=False),
        Binding("right_square_bracket", "day(1)", "Later", show=False),
        Binding("0", "today", "Today", show=False),
    ]

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
        self.LOG_NAME = MODE_TITLES[self.mode]  # pyright: ignore[reportAttributeAccessIssue]
        self.only_open = False
        self.narrow = False  # RFI: overdue only; Commercial: running or late bars only
        self.impact = False  # RFI: an impact flag of yes only
        self.today = date.today()
        self.as_of = self.today
        self.number: str | None = None  # the item the evidence view is about
        self.rfi_log: RfiLog | None = None
        self.notices: CommercialRegister | None = None
        self.trail: EvidenceTrail | None = None
        self.labels = Labels()
        self._labelled = False
        self._summary = ""  # the summary line of the view last read

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return {
            "rfi": RFI_COLUMNS,
            "commercial": COMMERCIAL_COLUMNS,
            "evidence": EVIDENCE_COLUMNS,
        }[self.mode]

    def load_rows(self) -> Sequence[Row]:
        """Read the current view (off the UI thread) and work out its summary line."""
        if not self._labelled:
            self.labels = load_labels(
                self.client,
                f"project:{self.project}",
                ("correspondence.TechnicalItem", "correspondence.CommercialItem"),
            )
            self._labelled = True
        if self.mode == "rfi":
            self.rfi_log = self.client.list_rfis(
                self.project,
                only_open=self.only_open,
                only_overdue=self.narrow,
                only_impact=self.impact,
                limit=MAX_LINES,
            )
            self._summary = rfi_summary(
                self.rfi_log,
                only_open=self.only_open,
                only_overdue=self.narrow,
                only_impact=self.impact,
            )
            return self.rfi_log.lines
        if self.mode == "commercial":
            self.notices = self.client.list_commercial(
                self.project,
                only_open=self.only_open,
                time_bars_only=self.narrow,
                limit=MAX_LINES,
            )
            self._summary = commercial_summary(
                self.notices, only_open=self.only_open, time_bars_only=self.narrow
            )
            if not self.notices.lines and not self.is_controller:
                self._summary = NO_COMMERCIAL
            return self.notices.lines
        self.trail = None
        if self.number is None:
            self._summary = "Highlight an RFI or a notice and press t."
            return []
        self.trail = self.client.get_evidence_trail(self.project, self.number, as_of=self.as_of)
        count = len(self.trail.nodes)
        self._summary = f"{count} record{'s' if count != 1 else ''} in the trail" + (
            " (cut short by a bound)" if self.trail.truncated else ""
        )
        return self.trail.nodes

    def row_key(self, row: Row) -> str:
        return row.record_id if isinstance(row, EvidenceNode) else row.id

    def row_cells(self, row: Row) -> Sequence[str]:
        technical = mode_of(self.app).technical
        if isinstance(row, EvidenceNode):
            return node_cells(row, self.labels, technical=technical)
        if isinstance(row, RfiLogLine):
            return rfi_cells(row, self.labels, technical=technical)
        return commercial_cells(row, self.labels, technical=technical)

    def row_record(self, row: Row) -> tuple[str, str]:
        if isinstance(row, EvidenceNode):
            return (row.key or "", row.title)
        return (row.number, row.subject)

    def panel_text(self, row: Row | None) -> str:
        """The highlighted row in full (one read per row)."""
        technical = mode_of(self.app).technical
        if isinstance(row, EvidenceNode):
            return "\n".join(node_lines(row, self.labels, technical=technical))
        if row is None:
            return "Nothing here."
        try:
            if isinstance(row, RfiLogLine):
                view = self.client.get_rfi(self.project, row.number)
                return "\n".join(rfi_lines(view, self.labels, technical=technical))
            found = self.client.get_commercial(self.project, row.number)
            return "\n".join(commercial_lines(found, self.labels, technical=technical))
        except CLIENT_ERRORS as exc:
            return describe_error(exc)

    def actions_for(self, row: Row) -> Sequence[LogAction]:
        if isinstance(row, EvidenceNode):
            return []  # the trail changes nothing
        offers = self.client.allowed_actions(row.id)
        return log_actions(offers, without_keys(ACTION_UI, OWN_KEYS), self._runner())

    def _runner(self) -> Runner:
        return screen_runner(self, self.client, actor=self.actor, scope=f"project:{self.project}")

    def summary_text(self) -> str:
        if self.mode == "evidence":
            title = evidence_title(
                self.number or "-", self.trail.as_of if self.trail else self.as_of.isoformat()
            )
            return f"{title}   {self._summary}"
        return self._summary

    def open_row(self, row: Row) -> None:
        """Enter opens the row's full record; Esc there comes back to this row (SCOPE clause 1)."""
        open_record(
            self,
            self.client,
            f"project:{self.project}",
            self.project,
            self.actor,
            self.row_key(row),
        )

    def current_number(self) -> str | None:
        """The number of the highlighted RFI or notice (``None`` in the evidence view)."""
        row = self.current()
        if self.mode == "evidence" or row is None or isinstance(row, EvidenceNode):
            return None
        return row.number

    # --- views and filters ---------------------------------------------------------------

    def _view(self, mode: str) -> None:
        """Show another view: its columns first, then its rows."""
        self.mode = mode
        self.LOG_NAME = MODE_TITLES[mode]  # pyright: ignore[reportAttributeAccessIssue]
        self.rows = []  # the rows of the other view are not rows of this one
        table = self.query_one("#log-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*self.columns())
        self._fill(None)
        self.reload()

    def action_mode(self, mode: str) -> None:
        if mode in MODES and mode != self.mode:
            if mode == "evidence" and self.number is None:
                self.number = self.current_number()
            self._view(mode)

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
            self.say("Highlight an RFI or a notice in view 1 or 2 first.")
            return
        self.number = number
        self._view("evidence")

    def action_day(self, step: int) -> None:
        self.as_of = step_day(self.as_of, step, self.today)
        if self.mode == "evidence":
            self.reload()
        else:
            self.say(f"Evidence will be read as of {self.as_of.isoformat()}.")

    def action_today(self) -> None:
        self.as_of = self.today
        if self.mode == "evidence":
            self.reload()
