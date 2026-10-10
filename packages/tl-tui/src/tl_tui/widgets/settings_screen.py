"""about:config: every setting, its value and where it comes from (P0-I8-S19; brief 30.2, 30.3).

A full-size modal opened with ``F9``. The table lists the settings as the project being looked at
sees them: the ``●`` marks a value set at the layer a change would go to (about:config's
"modified"), the origin says which layer the value comes from, ``locked`` marks a key the company
locked for projects. The panel under the table describes the highlighted setting. Changes go
through :class:`SettingForm`, so the reason and the risk are asked for there; the service decides
what is allowed. Nothing here is stored: every change is one client call, and the list is read
again afterwards.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_core.settings.layers import project_of_scope
from tl_core.settings.views import SettingView

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.settings_text import (
    Preference,
    detail_lines,
    row_cells,
    target_layer,
    user_of,
)
from tl_tui.widgets.setting_form import Action, SettingForm
from tl_tui.widgets.setting_history import SettingHistory

COLUMNS = ("Setting", "Value", "Type", "Origin", "Lock")


class SettingsScreen(ModalScreen[None]):
    """The settings list for the project of ``scope`` (``company`` shows the company view)."""

    KEY_HINTS: ClassVar[str] = (
        "e edit  r reset  h history  k lock  L layer  m modified  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("e", "edit", "Edit", show=False),
        Binding("r", "reset", "Reset", show=False),
        Binding("h", "history", "History", show=False),
        Binding("k", "lock", "Lock", show=False),
        Binding("L", "layer", "Layer", show=False),
        Binding("m", "modified", "Modified only", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    SettingsScreen { background: $surface; }
    SettingsScreen > Vertical { padding: 0 1; }
    SettingsScreen #settings-title { text-style: bold; height: 1; }
    SettingsScreen #settings-filter { height: 3; }
    SettingsScreen #settings-table { height: 1fr; min-height: 6; }
    SettingsScreen #settings-detail { height: 12; border-top: solid $accent; padding: 0 1; }
    SettingsScreen #settings-status { height: 1; }
    SettingsScreen #settings-hints { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, scope: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.project = project_of_scope(scope)
        self.user = user_of(actor)
        self.prefer: Preference = "project" if self.project is not None else "company"
        self.modified_only = False
        self.text = ""
        self.views: list[SettingView] = []  # as listed, before the text filter
        self.shown: list[SettingView] = []

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="settings-title")
            yield Input(placeholder="Filter by name or description", id="settings-filter")
            yield DataTable[str](id="settings-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="settings-detail")
            yield Static("", markup=False, id="settings-status")
            yield Static(self.KEY_HINTS, markup=False, id="settings-hints")

    def on_mount(self) -> None:
        self.query_one("#settings-table", DataTable).add_columns("", *COLUMNS)
        self.reload()
        self.query_one("#settings-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def _title(self) -> str:
        view = self.project if self.project is not None else "the company"
        goes = "the project" if self.prefer == "project" and self.project else "the company"
        mode = "  (modified only)" if self.modified_only else ""
        return f"about:config for {view}: changes go to {goes} (L switches){mode}"

    def reload(self) -> None:
        """Read the list again and keep the highlighted setting where it is."""
        keep = self._key()
        try:
            # the list is seen from the layer a change goes to, so the ● means "set there"
            seen = self.project if self.prefer == "project" else None
            self.views = self.client.list_settings(
                project=seen, user=self.user, modified_only=self.modified_only
            )
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep)

    def _fill(self, keep: str | None = None) -> None:
        needle = self.text.strip().lower()
        self.shown = [
            v
            for v in self.views
            if not needle
            or needle in v.effective.key.lower()
            or needle in v.definition.description.lower()
        ]
        table = self.query_one("#settings-table", DataTable)
        table.clear()
        for view in self.shown:
            cells = row_cells(view)
            mark = "●" if view.effective.modified_here else " "
            # Text, not str: a cell is read as markup, and a value such as [a, b] is not markup
            table.add_row(*(Text(c) for c in (mark, *cells)), key=cells[0])
        self.query_one("#settings-title", Static).update(self._title())
        if self.shown:
            keys = [v.effective.key for v in self.shown]
            table.move_cursor(row=keys.index(keep) if keep in keys else 0)
        self._describe()

    def _key(self) -> str | None:
        view = self.current()
        return view.effective.key if view is not None else None

    def current(self) -> SettingView | None:
        table = self.query_one("#settings-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def target(self, view: SettingView) -> str | None:
        return target_layer(view.definition, self.prefer, self.project, self.user)

    def _describe(self) -> None:
        view = self.current()
        detail = self.query_one("#settings-detail", Static)
        if view is None:
            detail.update("No setting matches.")
            return
        detail.update("\n".join(detail_lines(view, self.target(view))))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#settings-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()  # Enter on the table
        self.action_edit()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.text = event.value
        self._fill(self._key())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#settings-table", DataTable).focus()

    # --- actions -------------------------------------------------------------------------

    def _change(self, action: Action) -> None:
        view = self.current()
        if view is None:
            return
        layer = self.target(view)
        defn = view.definition
        if layer is None:
            self._say(f"{defn.key} has only a platform default; it cannot be changed here.")
            return
        # No rule is checked here: a locked key, a missing reason or nothing to reset is the
        # service's refusal (or no-op), shown by the form, so the screen cannot disagree with it.

        def done(result: bool | None) -> None:
            if result:
                self.reload()
                self._say(f"{action.capitalize()}: {defn.key}")

        self.app.push_screen(SettingForm(self.client, view, action, layer), done)

    def action_edit(self) -> None:
        if isinstance(self.focused, Input):
            return
        self._change("set")

    def action_reset(self) -> None:
        self._change("reset")

    def action_lock(self) -> None:
        view = self.current()
        if view is None:
            return
        self._change_lock(view)

    def _change_lock(self, view: SettingView) -> None:
        action: Action = "unlock" if view.effective.locked else "lock"

        def done(result: bool | None) -> None:
            if result:
                self.reload()
                self._say(f"{action.capitalize()}ed: {view.definition.key}")

        self.app.push_screen(SettingForm(self.client, view, action, "company"), done)

    def action_history(self) -> None:
        view = self.current()
        if view is None:
            return

        def done(result: bool | None) -> None:
            if result:
                self.reload()

        self.app.push_screen(SettingHistory(self.client, view.definition.key), done)

    def action_layer(self) -> None:
        if self.project is None:
            self._say("Without a project, changes go to the company.")
            return
        self.prefer = "company" if self.prefer == "project" else "project"
        self._fill(self._key())

    def action_modified(self) -> None:
        self.modified_only = not self.modified_only
        self.reload()

    def action_filter(self) -> None:
        self.query_one("#settings-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()
        self._say("Reloaded.")

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#settings-filter", Input).value = ""
            self.query_one("#settings-table", DataTable).focus()
            return
        self.dismiss(None)
