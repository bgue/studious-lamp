"""The tag register: a project's engineering tags, their class, state and conformance (P1-I1-T09d).

A full-size modal opened with ``F8``. The table lists the project's tags by number; ``BAD`` in the
``No.`` column marks a number that breaks the registry pattern, ``Conf`` is the stored conformance
level. The panel under the table describes the highlighted tag: its parts, why its number is
refused or accepted, and what it still lacks. Everything is read through the client; nothing here
changes a tag. The filter keys narrow the list on the screen (class, violations only, text);
``a`` asks the client for the ended tags too.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_engineering.views import TagView

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.tag_text import COLUMNS, detail_lines, next_class, row_cells, summary_line

MAX_TAGS = 5000


class TagRegisterScreen(ModalScreen[None]):
    """The tags of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "c class  v violations only  a ended too  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "class_filter", "Class", show=False),
        Binding("v", "violations", "Violations only", show=False),
        Binding("a", "ended", "Ended too", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    TagRegisterScreen { background: $surface; }
    TagRegisterScreen > Vertical { padding: 0 1; }
    TagRegisterScreen #tags-title { text-style: bold; height: 1; }
    TagRegisterScreen #tags-filter { height: 3; }
    TagRegisterScreen #tags-table { height: 1fr; min-height: 6; }
    TagRegisterScreen #tags-detail { height: 12; border-top: solid $accent; padding: 0 1; }
    TagRegisterScreen #tags-status { height: 1; }
    TagRegisterScreen #tags-hints { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.class_code: str | None = None
        self.violations_only = False
        self.include_ended = False
        self.text = ""
        self.views: list[TagView] = []  # as listed, before the screen's own filters
        self.shown: list[TagView] = []
        self.detail: TagView | None = None  # the highlighted tag with its issues

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Tags of {self.project}", markup=False, id="tags-title")
            yield Input(placeholder="Filter by number or title", id="tags-filter")
            yield DataTable[str](id="tags-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="tags-detail")
            yield Static("", markup=False, id="tags-status")
            yield Static(self.KEY_HINTS, markup=False, id="tags-hints")

    def on_mount(self) -> None:
        self.query_one("#tags-table", DataTable).add_columns(*COLUMNS)
        self.reload()
        self.query_one("#tags-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the list again and keep the highlighted tag where it is."""
        keep = self._number()
        try:
            self.views = self.client.list_tags(
                self.project, include_ended=self.include_ended, limit=MAX_TAGS
            )
        except CLIENT_ERRORS as exc:
            self._say(describe_error(exc), error=True)
            return
        self._fill(keep)

    def _fill(self, keep: str | None = None) -> None:
        """Apply the screen's filters to ``self.views`` and fill the table."""
        needle = self.text.strip().lower()
        self.shown = [
            v
            for v in self.views
            if (self.class_code is None or v.class_code == self.class_code)
            and (not self.violations_only or v.number_status == "violation")
            and (not needle or needle in v.number.lower() or needle in v.title.lower())
        ]
        table = self.query_one("#tags-table", DataTable)
        table.clear()
        for view in self.shown:
            # Text, not str: a cell is read as markup, and a title such as [a, b] is not markup
            table.add_row(*(Text(cell) for cell in row_cells(view)), key=view.number)
        if self.shown:
            numbers = [v.number for v in self.shown]
            table.move_cursor(row=numbers.index(keep) if keep in numbers else 0)
        self.query_one("#tags-status", Static).update(
            summary_line(
                len(self.shown),
                len(self.views),
                class_code=self.class_code,
                violations_only=self.violations_only,
                include_ended=self.include_ended,
                text=self.text,
            )
        )
        self._describe()

    def _number(self) -> str | None:
        view = self.current()
        return view.number if view is not None else None

    def current(self) -> TagView | None:
        table = self.query_one("#tags-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _describe(self) -> None:
        """Show the highlighted tag with what it lacks (one ``get_tag`` call per tag)."""
        detail = self.query_one("#tags-detail", Static)
        view = self.current()
        if view is None:
            self.detail = None  # nothing is highlighted, so nothing is described
            detail.update("No tag matches.")
            return
        try:
            full = self.client.get_tag(self.project, view.number)
        except CLIENT_ERRORS as exc:
            full = view  # the listing's copy: no issues
            self._say(describe_error(exc), error=True)
        self.detail = full
        detail.update("\n".join(detail_lines(full)))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#tags-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.text = event.value
        self._fill(self._number())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#tags-table", DataTable).focus()

    # --- actions -------------------------------------------------------------------------

    def action_class_filter(self) -> None:
        """Show the next class: all, then each class that has a tag in the list, then all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        classes = [v.class_code for v in self.views if v.class_code is not None]
        self.class_code = next_class(self.class_code, classes)
        self._fill(self._number())

    def action_violations(self) -> None:
        """Show only the tags whose number breaks the pattern, or all again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.violations_only = not self.violations_only
        self._fill(self._number())

    def action_ended(self) -> None:
        """Include the superseded and deleted tags, or leave them out again (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.include_ended = not self.include_ended
        self.reload()

    def action_filter(self) -> None:
        self.query_one("#tags-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#tags-filter", Input).value = ""
            self.query_one("#tags-table", DataTable).focus()
            return
        self.dismiss(None)
