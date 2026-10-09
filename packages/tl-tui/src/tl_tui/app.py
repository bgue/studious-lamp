"""The Textual application shell: header, nav tree, main area, context panel, footer (brief 10.1).

`TlApp` owns layout and message routing only. It reads and writes through the injected
`ClientInterface`, so the same shell runs embedded or remote (brief 4). Side panels collapse with
F2/F3; at 80 columns or less they become overlays (sketch 11).
"""

from __future__ import annotations

from typing import ClassVar

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widget import Widget

from tl_tui.client import ClientInterface
from tl_tui.messages import (
    CloseRecord,
    NavSelected,
    OpenRecord,
    RecordChanged,
    RecordHighlighted,
    SelectionChanged,
    StatusMessage,
    StepRecord,
)
from tl_tui.widgets.context_panel import ContextPanel
from tl_tui.widgets.footer import TlFooter, hints_for
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.header import TlHeader
from tl_tui.widgets.main_area import MainArea
from tl_tui.widgets.nav_tree import NavTree
from tl_tui.widgets.record_view import RecordView

NARROW_MAX_WIDTH = 80  # columns; at or below this the side panels become overlays


class TlApp(App[None]):
    """Throughline TUI. ``scope`` is ``project:<id>``; ``record_type`` filters the grid."""

    TITLE = "Throughline"
    CSS_PATH = "app.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f2", "toggle_panel('nav')", "Nav"),
        Binding("f3", "toggle_panel('context')", "Context"),
        Binding("f6", "cycle_panels(1)", "Panels"),
        Binding("shift+f6", "cycle_panels(-1)", "Panels back", show=False),
        Binding("escape", "close_overlay", "Close", show=False),
        Binding("n", "new_record", "New", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        *,
        scope: str = "project:P123",
        company: str = "ACME",
        record_type: str | None = "core.Record",
        actor: str = "user:dev",
        mode: str = "embedded",
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.company = company
        self.record_type = record_type
        self.actor = actor
        self.mode = mode
        self._open_key: str | None = None

    # --- layout ------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield TlHeader(
            company=self.company, scope=self.scope, mode=self.mode, actor=self.actor, id="header"
        )
        with Horizontal(id="body"):
            yield NavTree(company=self.company, scope=self.scope, id="nav")
            with MainArea(id="main"):
                yield RecordGrid(self.client, self.scope, record_type=self.record_type, id="grid")
            yield ContextPanel(id="context")
        yield TlFooter(id="footer")

    def on_mount(self) -> None:
        self._apply_width(self.size.width)
        self.query_one("#grid", RecordGrid).focus()

    @property
    def narrow(self) -> bool:
        return self.has_class("-narrow")

    def on_resize(self, event: events.Resize) -> None:
        self._apply_width(event.size.width)

    def _apply_width(self, width: int) -> None:
        narrow = width <= NARROW_MAX_WIDTH
        if narrow != self.narrow:
            for panel in self._panels():
                panel.remove_class("-open", "-hidden")
        self.set_class(narrow, "-narrow")

    def _panels(self) -> list[Widget]:
        return [self.query_one("#nav", Widget), self.query_one("#context", Widget)]

    def panel_visible(self, name: str) -> bool:
        """Whether panel ``name`` (``nav`` or ``context``) is on screen now."""
        panel = self.query_one(f"#{name}", Widget)
        return panel.display

    def action_toggle_panel(self, name: str) -> None:
        panel = self.query_one(f"#{name}", Widget)
        if self.narrow:
            opening = not panel.has_class("-open")
            for other in self._panels():
                other.remove_class("-open")
            panel.set_class(opening, "-open")
            (panel if opening else self.query_one("#grid", Widget)).focus()
        else:
            panel.toggle_class("-hidden")
            if panel.has_class("-hidden") and panel.has_focus:
                self.query_one("#grid", Widget).focus()

    def action_close_overlay(self) -> None:
        if self.narrow and any(p.has_class("-open") for p in self._panels()):
            for panel in self._panels():
                panel.remove_class("-open")
            self.query_one("#main", MainArea).focus()
            self._focus_main()

    def action_cycle_panels(self, direction: int) -> None:
        order: list[Widget] = [
            p
            for p in (
                self.query_one("#nav", Widget),
                self._main_focus_target(),
                self.query_one("#context", Widget),
            )
            if p.display
        ]
        current = self.focused
        index = -1
        for i, panel in enumerate(order):
            if current is not None and (current is panel or panel in current.ancestors):
                index = i
        order[(index + direction) % len(order)].focus()

    def _main_focus_target(self) -> Widget:
        main = self.query_one("#main", MainArea)
        return main.query_one("#record" if main.showing_record else "#grid", Widget)

    def _focus_main(self) -> None:
        self._main_focus_target().focus()

    def action_new_record(self) -> None:
        # The app-level `n` binding stays live under a modal; a form already open must keep it.
        if isinstance(self.screen, ModalScreen):
            return
        from tl_tui.widgets.new_record_form import NewRecordForm

        async def created(key: str | None) -> None:
            if key is None:
                return
            self.query_one("#grid", RecordGrid).reload()
            self.query_one("#footer", TlFooter).show_status(f"Created {key}", "info")
            await self._show_record(self.scope, key)

        self.push_screen(
            NewRecordForm(
                self.client,
                self.scope,
                record_type=self.record_type or "core.Record",
                actor=self.actor,
            ),
            created,
        )

    # --- hints -------------------------------------------------------------------------------

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self.query_one("#footer", TlFooter).set_hints(hints_for(self.focused))

    # --- message routing ---------------------------------------------------------------------

    def on_record_highlighted(self, message: RecordHighlighted) -> None:
        self.query_one("#context", ContextPanel).show_record(message.record)

    def on_selection_changed(self, message: SelectionChanged) -> None:
        self.query_one("#footer", TlFooter).set_selection_count(message.count)

    def on_status_message(self, message: StatusMessage) -> None:
        self.query_one("#footer", TlFooter).show_status(message.text, message.severity)

    def on_nav_selected(self, message: NavSelected) -> None:
        if message.view_id == "records":
            self.call_later(self._show_grid)

    async def on_open_record(self, message: OpenRecord) -> None:
        await self._show_record(message.scope, message.key)

    async def on_close_record(self, message: CloseRecord) -> None:
        await self._show_grid()

    async def on_step_record(self, message: StepRecord) -> None:
        if self._open_key is None:
            return
        key = self.query_one("#grid", RecordGrid).neighbor_key(self._open_key, message.delta)
        if key is None:
            self.query_one("#footer", TlFooter).show_status("No more records in this list", "info")
            return
        await self._show_record(self.scope, key)

    def on_record_changed(self, message: RecordChanged) -> None:
        self.query_one("#grid", RecordGrid).reload()

    async def _show_record(self, scope: str, key: str) -> None:
        self._open_key = key
        self.query_one("#header", TlHeader).set_view(key)
        await self.query_one("#main", MainArea).show_record(RecordView(self.client, scope, key))

    async def _show_grid(self) -> None:
        self._open_key = None
        self.query_one("#header", TlHeader).set_view("Records")
        await self.query_one("#main", MainArea).show_grid()
