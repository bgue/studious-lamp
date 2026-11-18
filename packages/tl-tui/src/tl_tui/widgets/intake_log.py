"""The intake log of a project (V3-F4; I05; skill ``tui-layout``): what public intake received.

``IntakeLogScreen`` is a full-size ``LogScreen`` beside the review queue: the intake items,
oldest first, with state, received date and outcome. The panel shows the highlighted item (its
answers while it is Pending) read through the client's ``get_intake_item``. ``s`` shows the next
state: all, then Pending, Accepted and Rejected. The log is read-only: an item is accepted or
rejected with ``tl intake``. A person without ``forms.intake.review``, and an agent, gets the
client's refusal as the status line, never a row. Nothing here holds a code, a hash or a salt.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from textual.binding import Binding, BindingType
from tl_mod_forms.intake_views import ItemRow

from tl_tui import intake_text as text
from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Panel, render
from tl_tui.widgets.log_screen import LogAction, LogScreen

LIST_LIMIT = 500


class IntakeLogScreen(LogScreen[ItemRow]):
    """The intake items of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Intake"
    KEY_HINTS: ClassVar[str] = "/ filter  s state  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "s state")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "Show the next state: all, then Pending, Accepted and Rejected"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [Binding("s", "state", "State", show=False)]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None
        self.total = 0
        self._summary = ""

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return text.INTAKE_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return text.INTAKE_DROP

    def load_rows(self) -> Sequence[ItemRow]:
        page = self.client.list_intake_items(
            self.project, state=self.state_filter, limit=LIST_LIMIT
        )
        rows: list[ItemRow] = list(page.rows)
        self.total = int(page.total)
        self._summary = text.intake_summary(
            text.counts_of(rows), self.total, len(rows), self.state_filter
        )
        return rows

    def row_key(self, row: ItemRow) -> str:
        return row.id

    def row_cells(self, row: ItemRow) -> Sequence[str]:
        return text.intake_cells(row)

    def row_record(self, row: ItemRow) -> tuple[str, str]:
        return (text.item_name(row), "")

    def panel_text(self, row: ItemRow | None) -> Panel:
        if row is None:
            return "No intake item matches."
        try:
            detail = self.client.get_intake_item(self.project, row.id)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This intake item could not be read."
        return render(text.intake_page(detail, technical=mode_of(self.app).technical, panel=True))

    def actions_for(self, row: ItemRow) -> Sequence[LogAction]:
        """None: accepting and rejecting are ``tl intake`` commands."""
        return []

    def summary_text(self) -> str:
        return self._summary

    def open_row(self, row: ItemRow) -> None:
        self.reload()  # the panel already holds the item; Enter reads it again

    # --- filter --------------------------------------------------------------------------

    def action_state(self) -> None:
        options: list[str | None] = [None, *text.STATES]
        at = options.index(self.state_filter)
        self.state_filter = options[(at + 1) % len(options)]
        self.reload()
