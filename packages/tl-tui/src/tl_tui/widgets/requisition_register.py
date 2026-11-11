"""The requisition log and the requisition screen (P2-I4A T07a; spec §8, skill ``tui-layout``).

``RequisitionLogScreen`` is the module's home log: the project's requisitions by key, with subject,
kind, state, priority, need by and requester. The panel describes the highlighted requisition
(``req_page``, panel form; one ``get_requisition`` for it). ``k`` shows the next kind, ``s`` the
next state (each: all, then each one present in the list), ``m`` shows only the requisitions the
signed-in actor raised. The filters work on the rows already read; the list is not read again.
Enter opens ``RequisitionScreen`` for the requisition: one requisition in full, text only.

``RequisitionScreen`` has no actions; Esc closes it, F5 reads it again.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_mod_requisitions.api import RequisitionRow

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, actor_label, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Page, Panel, render
from tl_tui.requisition_text import REQ_COLUMNS, REQ_DROP, req_cells, req_page, req_summary
from tl_tui.widgets.log_screen import LogAction, LogScreen

if TYPE_CHECKING:
    from tl_tui.layout import Adaptive


def _next_value(current: str | None, values: Iterable[str]) -> str | None:
    """The next filter value: all (``None``), then each value in order, then all again."""
    options: list[str | None] = [None, *sorted(set(values))]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


class RequisitionLogScreen(LogScreen[RequisitionRow]):
    """The requisitions of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Requisitions"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = "/ filter  k kind  s state  m mine  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "k kind", "s state", "m mine")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("k", "Show the next kind: all, then each kind in the list"),
        ("s", "Show the next state: all, then each state in the list"),
        ("m", "Show only the requisitions you raised (again: all)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("k", "kind", "Kind", show=False),
        Binding("s", "state", "State", show=False),
        Binding("m", "mine", "Mine", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.kind_filter: str | None = None  # a kind code, as the list gives it
        self.state_filter: str | None = None
        self.mine = False  # True: only the requisitions the signed-in actor raised
        self.views: list[RequisitionRow] = []  # as listed, before the screen's own filters

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return REQ_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return REQ_DROP

    def load_rows(self) -> Sequence[RequisitionRow]:
        self.views = list(self.client.list_requisitions(self.project).rows)
        return self._filtered()

    def row_key(self, row: RequisitionRow) -> str:
        return row.key

    def row_cells(self, row: RequisitionRow) -> Sequence[str]:
        return req_cells(row)

    def row_record(self, row: RequisitionRow) -> tuple[str, str]:
        return (row.key, row.subject)

    def panel_text(self, row: RequisitionRow | None) -> Panel:
        """The highlighted requisition in full: one ``get_requisition`` for it."""
        if row is None:
            return "No requisition matches."
        try:
            detail = self.client.get_requisition(self.project, row.key)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This requisition could not be read."
        technical = mode_of(self.app).technical
        return render(req_page(detail, technical=technical, panel=True))

    def actions_for(self, row: RequisitionRow) -> Sequence[LogAction]:
        """No action on a requisition here: the writes come with the later screens."""
        return []

    def summary_text(self) -> str:
        total, count = len(self.views), len(self.shown)
        head = req_summary(total, count, kind=self.kind_filter, state=self.state_filter)
        if self.mine:
            if self.kind_filter is None and self.state_filter is None:
                head = f"{count} of {req_summary(total, total)}"
            head += f", requester {actor_label(Labels(), self._actor())}"
        if self.filter_text.strip():
            head += f" · filter {self.filter_text.strip()!r}"
        return head

    def open_row(self, row: RequisitionRow) -> None:
        """Enter on a row opens the requisition screen for it."""
        self.app.push_screen(RequisitionScreen(self.client, self.project, row.key))

    # --- the log's own keys --------------------------------------------------------------

    def action_kind(self) -> None:
        """Show the next kind: all, then each kind that a requisition in the list has."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.kind_filter = _next_value(self.kind_filter, (v.kind for v in self.views))
        self._apply()

    def action_state(self) -> None:
        """Show the next state: all, then each state that a requisition in the list has."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_value(self.state_filter, (v.state for v in self.views))
        self._apply()

    def action_mine(self) -> None:
        """Show only the requisitions the signed-in actor raised, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.mine = not self.mine
        self._apply()

    # --- helpers -------------------------------------------------------------------------

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))

    def _filtered(self) -> list[RequisitionRow]:
        """The listed requisitions the screen's filters keep, in key order."""
        actor = self._actor()
        return [
            v
            for v in self.views
            if (self.kind_filter is None or v.kind == self.kind_filter)
            and (self.state_filter is None or v.state == self.state_filter)
            and (not self.mine or v.requester == actor)
        ]

    def _apply(self) -> None:
        """A filter key changed: filter the rows already held (no read), keep the cursor."""
        self.rows = self._filtered()
        self._fill(self._key())


class RequisitionScreen(ModalScreen[None]):
    """One requisition in full: identity, state, summary, Detail, Work order (and Technical in
    technical mode). Text only; Esc closes it, F5 reads it again."""

    KEY_HINTS: ClassVar[str] = "Esc back  F5 reload"
    WORK_ORDER_HINT: ClassVar[str] = "  w Work order"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("w", "work_order", "Work order", show=False),
    ]

    DEFAULT_CSS = """
    RequisitionScreen { background: $surface; }
    RequisitionScreen #req-body { height: 1fr; padding: 0 1; }
    RequisitionScreen #req-keys { height: 1; color: $text-muted; }
    RequisitionScreen #req-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, key: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.key = key
        self._gen = 0
        self._work_key: str | None = None  # the work order of the requisition, once read

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="req-body"):
                yield Static("", markup=False, id="req-page")
            yield Static(self.KEY_HINTS, markup=False, id="req-keys")
            yield Static("", markup=False, id="req-status")

    def on_mount(self) -> None:
        self.reload()

    # --- reads ---------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the requisition again (off the UI thread)."""
        self._gen += 1
        self.run_worker(
            self._load(self._gen, mode_of(self.app).technical),
            group="requisition",
            exclusive=True,
        )

    async def _load(self, gen: int, technical: bool) -> None:
        try:
            page, work_key = await asyncio.to_thread(self._read, technical)
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self._work_key = None
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self._work_key = work_key
            self._show(page, "")

    def _read(self, technical: bool) -> tuple[Page, str | None]:
        detail = self.client.get_requisition(self.project, self.key)
        work_key = None if detail.work_order is None else detail.work_order.key
        return req_page(detail, technical=technical), work_key

    def _show(self, page: Page | None, error: str) -> None:
        body: Adaptive | str = (
            render(page) if page is not None else "This requisition could not be read."
        )
        self.query_one("#req-page", Static).update(body)
        keys = self.KEY_HINTS + (self.WORK_ORDER_HINT if self._work_key else "")
        self.query_one("#req-keys", Static).update(keys)
        status = self.query_one("#req-status", Static)
        status.update(("! " + error) if error else "")

    # --- the screen's keys ---------------------------------------------------------------

    def actions_for(self, *_: Any) -> Sequence[LogAction]:
        """Text only: this screen offers no action."""
        return []

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """``w`` exists only when the requisition has a work order (no binding otherwise)."""
        if action == "work_order":
            return self._work_key is not None
        return True

    def action_reload(self) -> None:
        self.reload()

    def action_work_order(self) -> None:
        """Open the work order of this requisition, on top of this screen (Esc returns)."""
        if self._work_key is None:
            return
        from tl_tui.widgets.work_order_backlog import WorkOrderScreen

        self.app.push_screen(WorkOrderScreen(self.client, self.project, self._work_key))

    def action_close(self) -> None:
        self.dismiss(None)
