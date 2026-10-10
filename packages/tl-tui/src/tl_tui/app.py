"""The Textual application shell: header, nav tree, main area, context panel, footer (brief 10.1).

`TlApp` owns layout and message routing only. It reads and writes through the injected
`ClientInterface`, so the same shell runs embedded or remote (brief 4). Side panels collapse with
F2/F3; at 80 columns or less they become overlays (sketch 11).
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widget import Widget

from tl_tui.client import ClientInterface
from tl_tui.commands import command_by_id
from tl_tui.messages import (
    CloseRecord,
    NavSelected,
    OpenRecord,
    RecordChanged,
    RecordHighlighted,
    SelectionChanged,
    Severity,
    StatusMessage,
    StepRecord,
)
from tl_tui.navigation import NavHistory
from tl_tui.tray import ReferenceTray, TrayItem
from tl_tui.widgets.context_panel import ContextPanel
from tl_tui.widgets.feed_pane import FeedPane, PostRequested
from tl_tui.widgets.footer import TlFooter, hints_for
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.header import TlHeader
from tl_tui.widgets.links_tab import LinksTab
from tl_tui.widgets.main_area import MainArea
from tl_tui.widgets.nav_tree import NavTree
from tl_tui.widgets.record_view import RecordView

NARROW_MAX_WIDTH = 80  # columns; at or below this the side panels become overlays


class TlApp(App[None]):
    """Throughline TUI. ``scope`` is ``project:<id>``; ``record_type`` filters the grid."""

    TITLE = "Throughline"
    ENABLE_COMMAND_PALETTE = False  # ours (Ctrl+P and `:`) replaces Textual's
    CSS_PATH = "app.tcss"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f2", "toggle_panel('nav')", "Nav"),
        Binding("f3", "toggle_panel('context')", "Context"),
        Binding("f6", "cycle_panels(1)", "Panels"),
        Binding("shift+f6", "cycle_panels(-1)", "Panels back", show=False),
        Binding("escape", "close_overlay", "Close", show=False),
        Binding("n", "new_record", "New", show=False),
        Binding("f1", "help", "Help", show=False),
        Binding("question_mark", "help", "Help", show=False),
        Binding("ctrl+p", "palette", "Palette", show=False),
        Binding("colon", "palette", "Palette", show=False),
        Binding("l", "link", "Link", show=False),
        Binding("R", "tray_add", "Add to tray", show=False),
        Binding("f4", "tray_open", "Tray", show=False),
        Binding("w", "workflow", "Workflow", show=False),
        Binding("t", "trace", "Trace", show=False),
        Binding("F", "feed", "Feed", show=False),
        Binding("p", "post", "Post", show=False),
        Binding("alt+left", "back", "Back", show=False),
        Binding("alt+right", "forward", "Forward", show=False),
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
        roles: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.company = company
        self.record_type = record_type
        self.actor = actor
        self.mode = mode
        # Roles the user claims for workflow guards: a stub until auth exists (brief 8).
        self.roles = roles
        self.tray = ReferenceTray()
        self.history = NavHistory()
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
        main = self.query_one("#main", MainArea)
        if main.showing_feed and not self._modal_open():
            self.call_later(self._show_grid)
            return
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
        if main.showing_feed:
            return main.query_one("#feed", Widget)
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

    # --- palette, links, tray, workflow, trace, history ---------------------------

    def _modal_open(self) -> bool:
        # App-level keys stay live under a modal; they must not open a second one on top.
        return isinstance(self.screen, ModalScreen)

    def _say(self, text: str, severity: Severity = "info") -> None:
        self.query_one("#footer", TlFooter).show_status(text, severity)

    def _record_view(self) -> RecordView | None:
        main = self.query_one("#main", MainArea)
        if not main.showing_record:
            return None
        views = list(main.query(RecordView))
        return views[0] if views else None

    def _changed(self, *record_ids: str) -> None:
        """Commands run from a modal changed these records: reload the grid and the open view."""
        self.query_one("#grid", RecordGrid).reload()
        view = self._record_view()
        if view is not None and view.record is not None and view.record["id"] in record_ids:
            view.reload()

    def _focused_records(self) -> list[dict[str, Any]]:
        """The records a command acts on: the open record, else the grid selection or cursor row."""
        view = self._record_view()
        if view is not None:
            return [view.record] if view.record is not None else []
        grid = self.query_one("#grid", RecordGrid)
        cursor = grid.cursor_record
        return grid.selected_records() or ([cursor] if cursor is not None else [])

    def action_palette(self) -> None:
        if self._modal_open():
            return
        from tl_tui.widgets.palette import CommandPalette, PaletteChoice

        async def chosen(choice: PaletteChoice | None) -> None:
            if choice is None:
                return
            if choice.kind == "record" and choice.key is not None:
                await self._show_record(self.scope, choice.key, follow=True)
            elif choice.command_id is not None:
                command = command_by_id(choice.command_id)
                if command is not None:
                    await self.run_action(command.action)

        self.push_screen(CommandPalette(self.client, self.scope), chosen)

    def _feed_pane(self) -> FeedPane | None:
        main = self.query_one("#main", MainArea)
        panes = list(main.query(FeedPane)) if main.showing_feed else []
        return panes[0] if panes else None

    async def action_feed(self) -> None:
        """Open the feed: of the open record (a record view is showing), else of the project."""
        if self._modal_open():
            return
        view = self._record_view()
        record = view.record if view is not None else None
        await self._show_feed(record)

    async def _show_feed(self, record: dict[str, Any] | None) -> None:
        self._open_key = None
        pane = FeedPane(
            self.client,
            self.scope,
            record_id=str(record["id"]) if record is not None else None,
            record_key=record["key"] if record is not None else None,
            actor=self.actor,
        )
        title = f"Feed · {record['key']}" if record is not None and record["key"] else "Feed"
        self.query_one("#header", TlHeader).set_view(title)
        await self.query_one("#main", MainArea).show_feed(pane)

    def action_post(self, record_key: str | None = None) -> None:
        """Open the composer. Inside a record's feed or view it starts with that record's tag."""
        if self._modal_open():
            return
        from tl_tui.widgets.composer import ComposerScreen

        pane = self._feed_pane()
        view = self._record_view()
        key = record_key
        if key is None and pane is not None:
            key = pane.record_key
        if key is None and view is not None and view.record is not None:
            key = view.record["key"]

        def done(post_id: str | None) -> None:
            if post_id is None:
                return
            self._say("Posted", "info")
            current = self._feed_pane()
            if current is not None:
                current.reload()

        self.push_screen(
            ComposerScreen(
                self.client, self.scope, actor=self.actor, prefill=f"#{key} " if key else ""
            ),
            done,
        )

    def on_post_requested(self, message: PostRequested) -> None:
        self.action_post(message.record_key)

    def action_link(self) -> None:
        if self._modal_open():
            return
        from tl_tui.widgets.link_picker import LinkPicker, LinkPickerResult, PickerSource

        sources = self._focused_records()
        if not sources:
            self._say("Nothing to link: select a record or open one", "warning")
            return

        def done(result: LinkPickerResult | None) -> None:
            if result is None:
                return
            if result.created:
                self._changed(*(str(source["id"]) for source in sources))
                self._say(f"Linked {result.created}", "info")
            if result.messages:
                self._say("; ".join(result.messages), "error")

        self.push_screen(
            LinkPicker(
                self.client,
                self.scope,
                [PickerSource.from_record(r) for r in sources],
                actor=self.actor,
            ),
            done,
        )

    def action_tray_add(self) -> None:
        if self._modal_open():
            return
        view = self._record_view()
        records = self._focused_records()
        if view is not None:
            other = view.query_one("#links-tab", LinksTab).highlighted_other()
            if other is not None and view.query_one("#rv-tabs").has_focus_within:
                records = [other]
        if not records:
            self._say("Nothing to add to the tray", "warning")
            return
        added = [r["key"] for r in records if self.tray.add(TrayItem.from_record(r))]
        if added:
            self._say(f"Added {', '.join(added)} to the tray ({len(self.tray)})", "info")
        else:
            self._say(f"Already in the tray ({len(self.tray)})", "info")

    def action_tray_open(self) -> None:
        if self._modal_open():
            return
        from tl_tui.widgets.ref_tray import ReferenceTrayScreen

        view = self._record_view()
        target = view.record if view is not None else None

        def done(linked: int | None) -> None:
            if linked and target is not None:
                self._changed(str(target["id"]))
                self._say(f"Linked {linked} from the tray", "info")

        self.push_screen(
            ReferenceTrayScreen(self.client, self.scope, self.tray, target, actor=self.actor), done
        )

    def action_workflow(self) -> None:
        if self._modal_open():
            return
        from tl_tui.widgets.workflow_menu import WorkflowMenu

        records = self._focused_records()
        if len(records) != 1:
            self._say("Open a record (or put the cursor on one) for workflow actions", "warning")
            return
        record = records[0]

        def done(ran: bool | None) -> None:
            if ran:
                self._changed(str(record["id"]))

        self.push_screen(
            WorkflowMenu(self.client, self.scope, record, roles=self.roles, actor=self.actor), done
        )

    def action_trace(self) -> None:
        if self._modal_open():
            return
        view = self._record_view()
        if view is None:
            self._say("Open a record first to trace it", "warning")
            return
        view.show_tab("trace")

    async def action_back(self) -> None:
        if self._modal_open():
            return
        entry = self.history.back()
        if entry is None:
            self._say("Nothing to go back to", "info")
            return
        await self._show_record(entry[0], entry[1], navigate=False)

    async def action_forward(self) -> None:
        if self._modal_open():
            return
        entry = self.history.forward()
        if entry is None:
            self._say("Nothing to go forward to", "info")
            return
        await self._show_record(entry[0], entry[1], navigate=False)

    def action_toggle_nav(self) -> None:
        self.action_toggle_panel("nav")

    def action_toggle_context(self) -> None:
        self.action_toggle_panel("context")

    def action_help(self) -> None:
        # The app-level `F1` and `?` bindings stay live under a modal; help must not open over
        # a form or stack on top of another help screen.
        if isinstance(self.screen, ModalScreen):
            return
        from tl_tui.widgets.help_screen import HelpScreen

        self.push_screen(HelpScreen())

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
        await self._show_record(message.scope, message.key, follow=message.follow)

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

    async def _show_record(
        self, scope: str, key: str, *, follow: bool = False, navigate: bool = True
    ) -> None:
        """Open a record. ``navigate`` is false for back/forward, which only move in the history.

        Following a reference extends the trail; any other opening (the grid, ``[`` and ``]``,
        a record just created) starts a new one.
        """
        if navigate:
            if follow:
                self.history.visit(scope, key)
            else:
                self.history.start(scope, key)
        self._open_key = key
        trail = self.history.trail()
        self.query_one("#header", TlHeader).set_view(trail or key)
        await self.query_one("#main", MainArea).show_record(RecordView(self.client, scope, key))

    async def _show_grid(self) -> None:
        self._open_key = None
        self.query_one("#header", TlHeader).set_view("Records")
        await self.query_one("#main", MainArea).show_grid()
