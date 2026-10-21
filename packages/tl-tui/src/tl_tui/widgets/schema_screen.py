"""The schema workbench: every package version and what it defines (P1-I8-T04a; brief 10.6, 27.8).

A full-size modal opened with ``Ctrl+O``. The table lists the package versions, the versions of one
package together (``tree_cells``); the panel under it shows the highlighted version: who drafted
it, and one of three tabs, ``1`` what it defines, ``2`` its lint findings, ``3`` the diff against
the version below. ``[`` and ``]`` move between the tabs. ``v`` opens the review of the highlighted
version (classification, impact, test on a sample, submit, approve, publish; P1-I8-T04b) and the
list is read again when it closes. ``F5`` reads again, ``Esc`` closes. Nothing is stored here and
nothing changes here: every read is a client call, and a refusal or a missing package is shown in
the status line.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static
from tl_mod_schemareg.views import PackageDetail, PackageSummary

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schema_text import (
    COLUMNS,
    diff_lines,
    header_lines,
    lint_lines,
    plain_ref,
    property_lines,
    tree_cells,
)

TABS = ("Properties", "Lint", "Diff")


class SchemaWorkbenchScreen(ModalScreen[None]):
    """The package versions for ``scope``; ``tab`` is the one shown first."""

    KEY_HINTS: ClassVar[str] = "[ ] or 1-3 tab  v review and publish  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("right_square_bracket", "next_tab(1)", "Next tab", show=False),
        Binding("left_square_bracket", "next_tab(-1)", "Previous tab", show=False),
        *(
            Binding(str(n), f"show_tab({n - 1})", name, show=False)
            for n, name in enumerate(TABS, 1)
        ),
        Binding("v", "review", "Review", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    SchemaWorkbenchScreen { background: $surface; }
    SchemaWorkbenchScreen > Vertical { padding: 0 1; }
    SchemaWorkbenchScreen #schema-title { text-style: bold; height: 1; }
    SchemaWorkbenchScreen #schema-table { height: 10; min-height: 4; }
    SchemaWorkbenchScreen #schema-header { height: 5; border-top: solid $accent; padding: 0 1; }
    SchemaWorkbenchScreen #schema-tabs { height: 1; }
    SchemaWorkbenchScreen #schema-scroll { height: 1fr; padding: 0 1; }
    SchemaWorkbenchScreen #schema-status { height: 1; }
    SchemaWorkbenchScreen #schema-hints { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, scope: str, actor: str, *, tab: int = 0) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.tab = tab if 0 <= tab < len(TABS) else 0
        self.rows: list[PackageSummary] = []
        self.details: dict[str, PackageDetail] = {}

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", markup=False, id="schema-title")
            yield DataTable[str](id="schema-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="schema-header")
            yield Static("", markup=False, id="schema-tabs")
            with VerticalScroll(id="schema-scroll"):
                yield Static("", markup=False, id="schema-detail")
            yield Static("", markup=False, id="schema-status")
            yield Static(self.KEY_HINTS, markup=False, id="schema-hints")

    def on_mount(self) -> None:
        self.reload()
        self.query_one("#schema-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> bool:
        """Read the list again and keep the highlighted version where it is; False if it failed."""
        keep = self.current()
        self.details = {}
        try:
            self.rows = self.client.list_schema_packages()
        except CLIENT_ERRORS as exc:
            self.rows = []
            self._fill(None)
            self._say(describe_error(exc), error=True)
            return False
        self._fill(keep.id if keep is not None else None)
        return True

    def _fill(self, keep: str | None) -> None:
        """Show `self.rows` in the table, the title and the panel."""
        table = self.query_one("#schema-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*COLUMNS)
        technical = mode_of(self.app).technical
        for row, cells in zip(self.rows, tree_cells(self.rows, technical=technical), strict=True):
            table.add_row(*(Text(c) for c in cells), key=row.id)
        if self.rows:
            ids = [row.id for row in self.rows]
            table.move_cursor(row=ids.index(keep) if keep in ids else 0)
        self.query_one("#schema-title", Static).update(
            f"Schema packages ({len(self.rows)})   scope {self.scope}"
        )
        self._describe()

    def current(self) -> PackageSummary | None:
        """The highlighted version, or `None` when there is none."""
        cursor = self.query_one("#schema-table", DataTable).cursor_row
        if not self.rows or not 0 <= cursor < len(self.rows):
            return None
        return self.rows[cursor]

    def _describe(self) -> None:
        """Fill the header, the tab line and the panel with the highlighted version."""
        tabs = "  ".join(
            f"[{n} {name}]" if n - 1 == self.tab else f"{n} {name}"
            for n, name in enumerate(TABS, 1)
        )
        self.query_one("#schema-tabs", Static).update(tabs)
        header = self.query_one("#schema-header", Static)
        panel = self.query_one("#schema-detail", Static)
        technical = mode_of(self.app).technical
        row = self.current()
        if row is None:
            header.update("No package versions.")
            panel.update("")
            return
        detail = self.details.get(row.id)
        if detail is None:
            try:
                detail = self.client.get_schema_package(row.id)
            except CLIENT_ERRORS as exc:
                header.update(row.key if technical else plain_ref(row.key))
                panel.update("")
                self._say(describe_error(exc), error=True)
                return
            self.details[row.id] = detail
        header.update("\n".join(header_lines(detail, technical=technical)))
        if self.tab == 0:
            lines = property_lines(detail.content)
        elif self.tab == 1:
            lines = lint_lines(detail.lint)
        else:
            lines = diff_lines(detail)
        panel.update("\n".join(lines))

    def refresh_for_display_mode(self) -> None:
        """Draw the table, title and panel again for the display mode; the highlighted row stays."""
        keep = self.current()
        self._fill(keep.id if keep is not None else None)

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#schema-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    # --- actions -------------------------------------------------------------------------

    def action_show_tab(self, index: int) -> None:
        """Show the tab at `index` of `TABS`."""
        self.tab = index
        self._describe()

    def action_next_tab(self, step: int) -> None:
        """Show the next (or, with a negative `step`, the previous) tab, wrapping round."""
        self.action_show_tab((self.tab + step) % len(TABS))

    def action_review(self) -> None:
        """Open the review of the highlighted version; read the list again when it closes."""
        row = self.current()
        if row is None:
            return
        from tl_tui.widgets.schema_review_screen import SchemaReviewScreen

        self.app.push_screen(
            SchemaReviewScreen(self.client, self.scope, self.actor, row.id),
            callback=self._review_closed,
        )

    def _review_closed(self, _: None) -> None:
        self.reload()

    def action_reload(self) -> None:
        if self.reload():
            self._say("Reloaded.")

    def action_close(self) -> None:
        self.dismiss(None)
