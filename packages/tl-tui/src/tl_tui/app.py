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
from tl_core.ledger import Event

from tl_tui.client import ClientInterface
from tl_tui.commands import command_by_id
from tl_tui.live import (
    ChangeFeed,
    LiveUpdates,
    OwnWrites,
    describe_changes,
    detect_conflict,
    latest_by_record,
    touched_record_ids,
)
from tl_tui.messages import (
    CloseRecord,
    ConnectionChanged,
    ConnectionState,
    FilterClosed,
    FilterSubmitted,
    LedgerReset,
    LiveEvents,
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
from tl_tui.widgets.connection_banner import ConnectionBanner
from tl_tui.widgets.context_panel import ContextPanel
from tl_tui.widgets.feed_pane import FeedPane, PostRequested
from tl_tui.widgets.filter_bar import FilterBar
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
        Binding("slash", "filter", "Filter", show=False),
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
        feed: ChangeFeed | None = None,
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
        # Live updates: a feed of committed events (embedded: bus and poller; remote: SSE). Without
        # one the screens show what they last read until the user reloads.
        self._live = LiveUpdates(feed, self) if feed is not None else None
        if feed is not None:
            feed.head()  # the cursor is taken before the grid's first read: no gap in between
        self._reachable = True
        self._seen_live = False
        self._held: list[Event] = []  # events that may be this client's own; see _release_held

    # --- layout ------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield TlHeader(
            company=self.company, scope=self.scope, mode=self.mode, actor=self.actor, id="header"
        )
        yield ConnectionBanner(id="connection")
        yield FilterBar(id="filter")
        with Horizontal(id="body"):
            yield NavTree(company=self.company, scope=self.scope, id="nav")
            with MainArea(id="main"):
                yield RecordGrid(self.client, self.scope, record_type=self.record_type, id="grid")
            yield ContextPanel(id="context")
        yield TlFooter(id="footer")

    def on_mount(self) -> None:
        self._apply_width(self.size.width)
        self.query_one("#grid", RecordGrid).focus()
        # A remote client reports unreachable/live from whichever thread made the call.
        if hasattr(self.client, "connection_listener"):
            setattr(self.client, "connection_listener", self._connection_from_client)  # noqa: B010
        if self._live is not None:
            self._live.start()

    def on_unmount(self) -> None:
        if hasattr(self.client, "connection_listener"):
            setattr(self.client, "connection_listener", None)  # noqa: B010
        if self._live is not None:
            self._live.stop()

    def _connection_from_client(self, state: ConnectionState, detail: str) -> None:
        self.post_message(ConnectionChanged(state, detail))

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

    async def action_filter(self) -> None:
        """`/`: open the filter bar above the grid (the grid comes back first if needed)."""
        if self._modal_open():
            return
        main = self.query_one("#main", MainArea)
        if main.showing_record or main.showing_feed:
            await self._show_grid()
        self.query_one("#filter", FilterBar).show_bar()

    def on_filter_submitted(self, message: FilterSubmitted) -> None:
        """Enter in the bar: filter the grid; show the count, or the error and its position."""
        bar = self.query_one("#filter", FilterBar)
        result = self.query_one("#grid", RecordGrid).apply_filter(message.text)
        bar.show_result(result)
        if result.ok:
            if not message.text.strip():
                bar.hide_bar()
            self.query_one("#grid", RecordGrid).focus()

    def on_filter_closed(self, message: FilterClosed) -> None:
        """Esc in the bar: back to the grid; the bar stays visible while a filter is in force."""
        grid = self.query_one("#grid", RecordGrid)
        if not grid.filter_text:
            self.query_one("#filter", FilterBar).hide_bar()
        grid.focus()

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
        # A refresh applied while the app shuts down posts this after the screen is gone.
        panels = self.query("#context")
        if panels:
            panels.first(ContextPanel).show_record(message.record)

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

    # --- live updates -----------------------------------------------------------------------

    def on_connection_changed(self, message: ConnectionChanged) -> None:
        self.query_one("#connection", ConnectionBanner).show(message.state, message.detail)
        came_back = message.state == "live" and not self._reachable
        first_live = message.state == "live" and not self._seen_live
        self._reachable = message.state == "live"
        self._seen_live = self._seen_live or message.state == "live"
        if came_back:
            self._say("Connection restored", "info")
        if came_back or first_live:
            # Rows read during an outage, or between the first read and the feed's start, may be
            # stale; the feed replays from its cursor, and this read is the safety net.
            self.query_one("#grid", RecordGrid).refresh_live()

    def on_ledger_reset(self, message: LedgerReset) -> None:
        """The server's ledger went backwards: nothing shown can be trusted, so read it again."""
        self.query_one("#grid", RecordGrid).refresh_live()
        view = self._record_view()
        if view is not None:
            view.reload()
        banner = self.query_one("#connection", ConnectionBanner)
        banner.notice(message.detail or "server ledger changed; reloaded")
        self.set_timer(8.0, lambda: banner.show(banner.state))

    def on_live_events(self, message: LiveEvents) -> None:
        """Events committed by anyone: refresh the grid, and the open record if it was touched.

        Events this client's own commands produced are skipped for the grid (the command's own
        path already reloaded it) but not for the open record, which also hears about link and
        workflow changes made elsewhere.
        """
        own: OwnWrites | None = getattr(self.client, "own_writes", None)
        foreign: list[Event] = []
        for event in message.events:
            origin = "foreign" if own is None else own.classify(event)
            if origin == "foreign":
                foreign.append(event)
            elif origin == "pending":  # a command of ours is in flight on this stream
                self._held.append(event)
        if self._held:
            self.set_timer(0.1, self._release_held)
        self._mark_foreign(foreign)
        self._flag_conflict(foreign)
        view = self._record_view()
        if view is None or view.record is None:
            return
        record_id = str(view.record["id"])
        if record_id not in touched_record_ids(message.events):
            return
        newest = latest_by_record(message.events).get(record_id)
        moved = newest is not None and newest.stream_version > int(view.record["version"])
        linked = any(e.event_type.startswith("Link.") for e in message.events)
        if not (moved or linked):
            return
        view.reload()
        elsewhere = [e for e in foreign if record_id in touched_record_ids([e])]
        if elsewhere and view.record is not None:  # someone else did it: say who and when
            last = elsewhere[-1]
            view.note_remote_update(last.actor, int(view.record["version"]), last.recorded_at)

    def _flag_conflict(self, foreign: list[Event]) -> None:
        """An open edit form whose record moved past the version it was opened at: say so now."""
        from tl_tui.widgets.edit_form import EditForm  # noqa: PLC0415

        form = self.screen
        if not isinstance(form, EditForm) or form.conflict:
            return
        newer = detect_conflict(str(form.record["id"]), form.opened_version, foreign)
        if newer is not None:
            form.mark_conflict(newer.actor, newer.stream_version)

    def _mark_foreign(self, events: list[Event]) -> None:
        ids = touched_record_ids(events)
        if ids:
            self.query_one("#grid", RecordGrid).refresh_live(ids)
            self._say(describe_changes(events), "info")

    def _release_held(self) -> None:
        """Classify the held events again: own ones are dropped, the rest are someone else's.

        An event is held while a command of ours that may have produced it is in flight; after
        the response is noted it is ``own``, or, when the in-flight window ends (response or
        ``OwnWrites.HOLD_CAP_S``), ``foreign``.
        """
        own: OwnWrites | None = getattr(self.client, "own_writes", None)
        held, self._held = self._held, []
        ready: list[Event] = []
        for event in held:
            origin = "foreign" if own is None else own.classify(event)
            if origin == "foreign":
                ready.append(event)
            elif origin == "pending":
                self._held.append(event)
        if self._held:
            self.set_timer(0.1, self._release_held)
        self._mark_foreign(ready)

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
