"""The punch log of a project and one punch item's screen (P2-PUNCH-T06; spec §8, ``tui-layout``).

``PunchLogScreen`` is a full-size ``LogScreen``: the project's punch items by key, with subject,
state, category, area, system, due date and assignee. The panel describes the highlighted item.
``s`` shows the next state, ``c`` the next category, ``o`` the overdue items, ``m`` the items
assigned to the signed-in actor; each filter is read again from the client (the list filters).
Enter opens ``PunchScreen`` for the item.

``PunchScreen`` shows one item in full. ``c`` clears it (asks a note), ``v`` verifies it (asks
"are you sure"), ``o`` reopens it (asks a reason). A key is shown and taken only in the states
``tl_mod_quality.actions.RULES`` offers the command in. The command goes through the client's
``quality_command`` with the signed-in actor and the project's scope; a refusal is the status line.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_mod_quality.actions import states_for
from tl_mod_quality.commands import ClearPunchItem, ReopenPunchItem, VerifyPunchItem
from tl_mod_quality.names import CATEGORIES
from tl_mod_quality.views import PunchDetail, PunchRow

from tl_tui.action_ui import FormField
from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Adaptive, Page, Panel, render
from tl_tui.punch_text import (
    PUNCH_COLUMNS,
    PUNCH_DROP,
    STATES,
    punch_cells,
    punch_count,
    punch_page,
    punch_summary,
)
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.log_screen import LogAction, LogScreen

CLEAR = "ClearPunchItem"
VERIFY = "VerifyPunchItem"
REOPEN = "ReopenPunchItem"


def _next_value(current: str | None, values: Iterable[str]) -> str | None:
    """The next filter value: all (``None``), then each value in order, then all again."""
    options: list[str | None] = [None, *values]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


class PunchLogScreen(LogScreen[PunchRow]):
    """The punch items of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Punch list"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    KEY_HINTS: ClassVar[str] = (
        "/ filter  s state  c category  o overdue  m mine  F5 reload  Esc back"
    )
    KEY_CELLS: ClassVar[tuple[str, ...]] = (
        "/ filter",
        "s state",
        "c category",
        "o overdue",
        "m mine",
    )
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "Show the next state: all, then each state"),
        ("c", "Show the next category: all, then A, B and C"),
        ("o", "Show only the overdue items (again: all)"),
        ("m", "Show only the items assigned to you (again: all)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state", "State", show=False),
        Binding("c", "category", "Category", show=False),
        Binding("o", "overdue", "Overdue", show=False),
        Binding("m", "mine", "Mine", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None
        self.category_filter: str | None = None
        self.overdue = False
        self.mine = False  # True: only the items assigned to the signed-in actor
        self.counts: dict[str, int] = {}  # the project's items by state, as last read

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return PUNCH_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return PUNCH_DROP

    def load_rows(self) -> Sequence[PunchRow]:
        """The filters go to the list (state, category, overdue, assignee); the counts follow."""
        page = self.client.list_punch_items(
            self.project,
            state=self.state_filter,
            category=self.category_filter,
            overdue=self.overdue,
            assignee=self._actor() if self.mine else None,
        )
        self.counts = self.client.get_punch_counts(self.project)
        return page.rows

    def row_key(self, row: PunchRow) -> str:
        return row.key

    def row_cells(self, row: PunchRow) -> Sequence[str]:
        return punch_cells(row)

    def row_record(self, row: PunchRow) -> tuple[str, str]:
        return (row.key, row.subject)

    def panel_text(self, row: PunchRow | None) -> Panel:
        """The highlighted item in full: one ``get_punch_item`` read for it."""
        if row is None:
            return "No punch item matches."
        try:
            detail = self.client.get_punch_item(self.project, row.key)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This punch item could not be read."
        technical = mode_of(self.app).technical
        return render(punch_page(detail, technical=technical, panel=True))

    def actions_for(self, row: PunchRow) -> Sequence[LogAction]:
        """No action on the log's rows: the commands are on the item's screen."""
        return []

    def summary_text(self) -> str:
        total = sum(self.counts.values())
        if self.category_filter is None and not self.mine:
            return punch_summary(
                self.counts, total, len(self.shown), state=self.state_filter, overdue=self.overdue
            )
        named: list[str] = []
        if self.state_filter is not None:
            named.append(f"state {self.state_filter}")
        if self.overdue:
            named.append("overdue")
        if self.category_filter is not None:
            named.append(f"category {self.category_filter}")
        if self.mine:
            named.append("mine")
        return ", ".join([f"{len(self.shown)} of {punch_count(total)}", *named])

    def open_row(self, row: PunchRow) -> None:
        """Enter on a row opens the item's screen."""
        self.app.push_screen(PunchScreen(self.client, self.project, row.key))

    # --- the log's own keys --------------------------------------------------------------

    def action_state(self) -> None:
        """Show the next state: all, then Open, Cleared, Verified and Void."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_value(self.state_filter, STATES)
        self.reload()

    def action_category(self) -> None:
        """Show the next category: all, then A, B and C."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.category_filter = _next_value(self.category_filter, CATEGORIES)
        self.reload()

    def action_overdue(self) -> None:
        """Show only the overdue items (Open and due before today), or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.overdue = not self.overdue
        self.reload()

    def action_mine(self) -> None:
        """Show only the items assigned to the signed-in actor, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.mine = not self.mine
        self.reload()

    # --- helpers -------------------------------------------------------------------------

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))


class PunchScreen(ModalScreen[None]):
    """One punch item in full. Esc closes it, F5 reads it again; ``c``, ``v`` and ``o`` are
    offered only in the states that take them."""

    KEY_HINTS: ClassVar[str] = "c Clear  v Verify  o Reopen  Esc back  F5 reload"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("c", "clear", "Clear", show=False),
        Binding("v", "verify", "Verify", show=False),
        Binding("o", "reopen", "Reopen", show=False),
    ]

    DEFAULT_CSS = """
    PunchScreen { background: $surface; }
    PunchScreen #punch-body { height: 1fr; padding: 0 1; }
    PunchScreen #punch-keys { height: 1; color: $text-muted; }
    PunchScreen #punch-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, key: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.key = key
        self.detail: PunchDetail | None = None  # as last read
        self._gen = 0

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="punch-body"):
                yield Static("", markup=False, id="punch-page")
            yield Static(self.KEY_HINTS, markup=False, id="punch-keys")
            yield Static("", markup=False, id="punch-status")

    def on_mount(self) -> None:
        self.reload()

    # --- reads ---------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the item again (off the UI thread)."""
        self._gen += 1
        self.run_worker(
            self._load(self._gen, mode_of(self.app).technical), group="punch", exclusive=True
        )

    async def _load(self, gen: int, technical: bool) -> None:
        try:
            detail = await asyncio.to_thread(self.client.get_punch_item, self.project, self.key)
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self.detail = None
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self.detail = detail
            self._show(punch_page(detail, technical=technical), "")

    def _show(self, page: Page | None, error: str) -> None:
        body: Adaptive | str = (
            render(page) if page is not None else "This punch item could not be read."
        )
        self.query_one("#punch-page", Static).update(body)
        self.query_one("#punch-keys", Static).update(self._keys_text())
        status = self.query_one("#punch-status", Static)
        status.update(("! " + error) if error else "")

    # --- the screen's keys ---------------------------------------------------------------

    def _offers(self, command: str) -> bool:
        """The command is offered (and taken) for the item's state now."""
        return self.detail is not None and self.detail.row.state in states_for(command)

    def _keys_text(self) -> str:
        offered = [
            cell
            for cell, command in (("c Clear", CLEAR), ("v Verify", VERIFY), ("o Reopen", REOPEN))
            if self._offers(command)
        ]
        return "  ".join([*offered, "Esc back", "F5 reload"])

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_clear(self) -> None:
        """Ask for the note of the work done, then clear the item (Open only)."""
        if not self._offers(CLEAR):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    CLEAR,
                    lambda: ClearPunchItem(
                        **self._envelope(), punch_item=self._record_id(), note=answers["note"]
                    ),
                )

        self.app.push_screen(
            ActionFormScreen("Clear punch item", (FormField("note", "Note"),)), answered
        )

    def action_verify(self) -> None:
        """Ask "are you sure", then verify the item (Cleared only)."""
        if not self._offers(VERIFY):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    VERIFY,
                    lambda: VerifyPunchItem(**self._envelope(), punch_item=self._record_id()),
                )

        self.app.push_screen(
            ActionFormScreen("Verify punch item", confirm="Are you sure this item is verified?"),
            answered,
        )

    def action_reopen(self) -> None:
        """Ask for the reason, then reopen the item (Cleared or Verified)."""
        if not self._offers(REOPEN):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    REOPEN,
                    lambda: ReopenPunchItem(
                        **self._envelope(), punch_item=self._record_id(), reason=answers["reason"]
                    ),
                )

        self.app.push_screen(
            ActionFormScreen("Reopen punch item", (FormField("reason", "Reason"),)), answered
        )

    # --- helpers -------------------------------------------------------------------------

    def _record_id(self) -> str:
        assert self.detail is not None  # the keys are offered only when an item is read
        return self.detail.row.id

    def _envelope(self) -> dict[str, Any]:
        return {
            "actor": str(getattr(self.app, "actor", "user:dev")),
            "source": "tui",
            "scope": f"project:{self.project}",
        }

    def _send(self, name: str, make: Callable[[], Any]) -> None:
        """Send the command as the person; a refusal is the status line, then the item is read."""
        try:
            self.client.quality_command(name, make())
        except CLIENT_ERRORS as exc:
            self.query_one("#punch-status", Static).update("! " + describe_error(exc))
            return
        self.reload()
