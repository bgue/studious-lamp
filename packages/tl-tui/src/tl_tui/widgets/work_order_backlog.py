"""The work order backlog and the work order screen (P2-I4A T07b; spec §8, ``tui-layout``).

``WorkOrderBacklogScreen`` is a full-size ``LogScreen``: the project's work orders by key, with
kind, state, assigned, planned dates and hours. The panel describes the highlighted work order
(``wo_page``, panel form). ``s`` shows the next state (each: all, Open, Scheduled, Assigned,
Started, Completed, Closed, then all again); ``m`` shows only the work orders assigned to the
signed-in actor. The filters work on the rows already read; the list is read once per load (F5).
Enter opens ``WorkOrderScreen`` for the work order: one work order in full, text only.

``WorkOrderScreen`` has no actions; Esc closes it, F5 reads it again.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_mod_requisitions.api import WorkOrderRow

from tl_tui.display import humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Page, Panel, render
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.work_order_text import WO_COLUMNS, WO_DROP, wo_cells, wo_page, wo_summary

if TYPE_CHECKING:
    from tl_tui.client import ClientInterface

STATE_CYCLE: tuple[str | None, ...] = (
    None,
    "Open",
    "Scheduled",
    "Assigned",
    "Started",
    "Completed",
    "Closed",
)


def _next_state(current: str | None) -> str | None:
    """The next state filter: all (``None``), then each state in ``STATE_CYCLE``, then all."""
    index = STATE_CYCLE.index(current) if current in STATE_CYCLE else 0
    return STATE_CYCLE[(index + 1) % len(STATE_CYCLE)]


class WorkOrderBacklogScreen(LogScreen[WorkOrderRow]):
    """The work orders of ``project``: what is open, scheduled, assigned, started."""

    LOG_NAME: ClassVar[str] = "Work orders"
    KEY_HINTS: ClassVar[str] = "/ filter  s state  m mine  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "s state", "m mine")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        (
            "s",
            "Show the next state: all, then Open, Scheduled, Assigned, Started, Completed, Closed",
        ),
        ("m", "Show only the work orders assigned to you (again: all)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state", "State", show=False),
        Binding("m", "mine", "Mine", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None
        self.mine = False  # True: only the work orders assigned to the signed-in actor
        self.views: list[WorkOrderRow] = []  # as listed, before the screen's own filters

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return WO_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return WO_DROP

    def load_rows(self) -> Sequence[WorkOrderRow]:
        """Read the work orders once (off the UI thread); the filters keep the rows held."""
        self.views = list(self.client.list_work_orders(self.project).rows)
        return self._filtered()

    def row_key(self, row: WorkOrderRow) -> str:
        return row.key

    def row_cells(self, row: WorkOrderRow) -> Sequence[str]:
        return wo_cells(row)

    def row_record(self, row: WorkOrderRow) -> tuple[str, str]:
        return (row.key, humanize(row.work_kind))

    def panel_text(self, row: WorkOrderRow | None) -> Panel:
        """The highlighted work order in full: one ``get_work_order`` for it."""
        if row is None:
            return "No work order matches."
        try:
            detail = self.client.get_work_order(self.project, row.key)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This work order could not be read."
        technical = mode_of(self.app).technical
        return render(wo_page(detail, technical=technical, panel=True))

    def actions_for(self, row: WorkOrderRow) -> Sequence[LogAction]:
        """No action on a work order here: the writes come with the later screens."""
        return []

    def summary_text(self) -> str:
        return wo_summary(
            len(self.views),
            len(self.shown),
            state=self.state_filter,
            assigned_to=self._actor() if self.mine else None,
        )

    def open_row(self, row: WorkOrderRow) -> None:
        """Enter on a row opens the work order screen for it."""
        self.app.push_screen(WorkOrderScreen(self.client, self.project, row.key))

    # --- the log's own keys --------------------------------------------------------------

    def action_state(self) -> None:
        """Show the next state: all, then each state in the cycle."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_state(self.state_filter)
        self._apply()

    def action_mine(self) -> None:
        """Show only the work orders assigned to the signed-in actor, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.mine = not self.mine
        self._apply()

    # --- helpers -------------------------------------------------------------------------

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))

    def _filtered(self) -> list[WorkOrderRow]:
        """The listed work orders the screen's filters keep, in key order."""
        actor = self._actor()
        return [
            v
            for v in self.views
            if (self.state_filter is None or v.state == self.state_filter)
            and (not self.mine or v.assigned_to == actor)
        ]

    def _apply(self) -> None:
        """A filter key changed: filter the rows already held (no read), keep the cursor."""
        self.rows = self._filtered()
        self._fill(self._key())


class WorkOrderScreen(ModalScreen[None]):
    """One work order in full: identity, state, summary, Work, Dates and hours. Text only; Esc
    closes it, F5 reads it again."""

    KEY_HINTS: ClassVar[str] = "Esc back  F5 reload"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
    ]

    DEFAULT_CSS = """
    WorkOrderScreen { background: $surface; }
    WorkOrderScreen #wo-body { height: 1fr; padding: 0 1; }
    WorkOrderScreen #wo-keys { height: 1; color: $text-muted; }
    WorkOrderScreen #wo-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, key: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.key = key
        self._gen = 0

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="wo-body"):
                yield Static("", markup=False, id="wo-page")
            yield Static(self.KEY_HINTS, markup=False, id="wo-keys")
            yield Static("", markup=False, id="wo-status")

    def on_mount(self) -> None:
        self.reload()

    # --- reads ---------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the work order again (off the UI thread)."""
        self._gen += 1
        self.run_worker(
            self._load(self._gen, mode_of(self.app).technical), group="work_order", exclusive=True
        )

    async def _load(self, gen: int, technical: bool) -> None:
        try:
            page = await asyncio.to_thread(self._read, technical)
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self._show(page, "")

    def _read(self, technical: bool) -> Page:
        detail = self.client.get_work_order(self.project, self.key)
        return wo_page(detail, technical=technical)

    def _show(self, page: Page | None, error: str) -> None:
        body: Any = render(page) if page is not None else "This work order could not be read."
        self.query_one("#wo-page", Static).update(body)
        status = self.query_one("#wo-status", Static)
        status.update(("! " + error) if error else "")

    # --- the screen's keys ---------------------------------------------------------------

    def actions_for(self, *_: Any) -> Sequence[LogAction]:
        """Text only: this screen offers no action."""
        return []

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)
