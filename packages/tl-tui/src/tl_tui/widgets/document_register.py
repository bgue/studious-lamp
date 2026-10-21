"""The document register: a project's controlled documents, their revisions and links (P1-I2).

A full-size modal opened with ``F7``. The table lists the project's documents by number with their
state and current revision (``B(IFC)``). The panel under it describes the highlighted document: its
revisions with their files, and the links to it, a stale pin marked ``!``. Everything is read
through the client. The two changes a person makes from here are their own dialogs: ``r`` re-pins
the first stale link of the highlighted document (after showing what changed) and ``t`` drafts a
transmittal. The filter keys narrow the list on the screen (state, type, text); ``a`` asks the
client for the void documents too.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_documents.views import DocumentView

from tl_tui.client import ClientInterface
from tl_tui.display import Labels, mode_of
from tl_tui.document_text import (
    COLUMNS,
    detail_lines,
    next_choice,
    row_cells,
    stale_links,
    summary_line,
)
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import load_labels
from tl_tui.widgets.record_screen import open_record
from tl_tui.widgets.repin_dialog import RepinScreen
from tl_tui.widgets.transmittal_composer import TransmittalComposerScreen

MAX_DOCUMENTS = 5000


class DocumentRegisterScreen(ModalScreen[None]):
    """The documents of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "s state  y type  a void too  r re-pin  t transmittal  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state_filter", "State", show=False),
        Binding("y", "type_filter", "Type", show=False),
        Binding("a", "void", "Void too", show=False),
        Binding("r", "repin", "Re-pin", show=False),
        Binding("t", "transmittal", "Transmittal", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    DocumentRegisterScreen { background: $surface; }
    DocumentRegisterScreen > Vertical { padding: 0 1; }
    DocumentRegisterScreen #docs-title { text-style: bold; height: 1; }
    DocumentRegisterScreen #docs-filter { height: 3; }
    DocumentRegisterScreen #docs-table { height: 1fr; min-height: 6; }
    DocumentRegisterScreen #docs-detail { height: 14; border-top: solid $accent; padding: 0 1; }
    DocumentRegisterScreen #docs-status { height: 1; }
    DocumentRegisterScreen #docs-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self, client: ClientInterface, project: str, actor: str, *, is_controller: bool = False
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.is_controller = is_controller  # an admin or a document controller (ADR-0013)
        self.state: str | None = None
        self.doc_type: str | None = None
        self.include_void = False
        self.text = ""
        self.views: list[DocumentView] = []  # as listed, before the screen's own filters
        self.shown: list[DocumentView] = []
        self.detail: DocumentView | None = None  # the highlighted document, in full
        self.labels: Labels = Labels()  # the code and type labels, loaded on mount

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Documents of {self.project}", markup=False, id="docs-title")
            yield Input(placeholder="Filter by number or title", id="docs-filter")
            yield DataTable[str](id="docs-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="docs-detail")
            yield Static("", markup=False, id="docs-status")
            yield Static(self.KEY_HINTS, markup=False, id="docs-hints")

    def on_mount(self) -> None:
        self.labels = load_labels(self.client, f"project:{self.project}", ("documents.Document",))
        self.query_one("#docs-table", DataTable).add_columns(*COLUMNS)
        self.reload()
        self.query_one("#docs-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the list again and keep the highlighted document where it is."""
        keep = self._number()
        try:
            self.views = self.client.list_documents(
                self.project, include_void=self.include_void, limit=MAX_DOCUMENTS
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
            if (self.state is None or v.state == self.state)
            and (self.doc_type is None or v.doc_type == self.doc_type)
            and (not needle or needle in v.number.lower() or needle in v.title.lower())
        ]
        table = self.query_one("#docs-table", DataTable)
        table.clear()
        for view in self.shown:
            # Text, not str: a cell is read as markup, and a title such as [a, b] is not markup
            table.add_row(*(Text(cell) for cell in row_cells(view, self.labels)), key=view.number)
        if self.shown:
            numbers = [v.number for v in self.shown]
            table.move_cursor(row=numbers.index(keep) if keep in numbers else 0)
        self.query_one("#docs-status", Static).update(
            summary_line(
                len(self.shown),
                len(self.views),
                state=self.state,
                doc_type=self.doc_type,
                include_void=self.include_void,
                text=self.text,
                labels=self.labels,
            )
        )
        self._describe()

    def _number(self) -> str | None:
        view = self.current()
        return view.number if view is not None else None

    def current(self) -> DocumentView | None:
        table = self.query_one("#docs-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _describe(self) -> None:
        """Show the highlighted document with its revisions and links (one call per document)."""
        detail = self.query_one("#docs-detail", Static)
        view = self.current()
        if view is None:
            self.detail = None  # nothing is highlighted, so nothing is described
            detail.update("No document matches.")
            return
        try:
            full = self.client.get_document(self.project, view.number)
        except CLIENT_ERRORS as exc:
            full = view  # the listing's copy: no revisions
            self._say(describe_error(exc), error=True)
        self.detail = full
        technical = mode_of(self.app).technical
        detail.update("\n".join(detail_lines(full, self.labels, technical=technical)))

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#docs-status", Static).update(("! " if error else "") + text)

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
        self.query_one("#docs-table", DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a row opens the full record screen; Esc there returns to this row."""
        event.stop()
        if not 0 <= event.cursor_row < len(self.shown):
            return
        view = self.shown[event.cursor_row]
        open_record(self, self.client, f"project:{self.project}", self.project, self.actor, view.id)

    def refresh_for_display_mode(self) -> None:
        """The technical toggle changed: rebuild the rows and the panel, keeping the row."""
        self._fill(self._number())

    # --- actions -------------------------------------------------------------------------

    def action_state_filter(self) -> None:
        """Show the next state: all, then each state that has a document in the list, then all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state = next_choice(self.state, [v.state for v in self.views])
        self._fill(self._number())

    def action_type_filter(self) -> None:
        """Show the next document type: all, then each type in the list, then all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.doc_type = next_choice(
            self.doc_type, [v.doc_type for v in self.views if v.doc_type is not None]
        )
        self._fill(self._number())

    def action_void(self) -> None:
        """Include the void documents, or leave them out again (reads again)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.include_void = not self.include_void
        self.reload()

    def action_repin(self) -> None:
        """Re-pin the first stale link of the highlighted document, after showing the diff."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.detail is None:
            self._say("No document is highlighted.")
            return
        found = stale_links(self.detail)
        if not found:
            self._say(f"{self.detail.number} has no stale link to re-pin.")
            return
        self.app.push_screen(
            RepinScreen(self.client, self.project, self.detail.number, found[0], self.actor),
            self._repinned,
        )

    def _repinned(self, moved: bool | None) -> None:
        """The re-pin dialog closed: read again when a link was moved."""
        if moved:
            self.reload()
            self._say("Link re-pinned.")

    def action_transmittal(self) -> None:
        """Draft a transmittal, starting from the highlighted document's current revision."""
        if isinstance(self.focused, Input):
            return  # the key is text
        number = self._number()
        composer = TransmittalComposerScreen(
            self.client,
            self.project,
            self.actor,
            document=number,
            is_controller=self.is_controller,
        )

        def closed(made: str | None) -> None:
            self._drafted(made, composer)

        self.app.push_screen(composer, closed)

    def _drafted(self, number: str | None, composer: TransmittalComposerScreen) -> None:
        """The composer closed: say which transmittal was drafted, and whether it was issued."""
        if not number:
            return
        if composer.issued:
            self._say(f"Drafted and issued transmittal {number}.")
        elif composer.issue_error:
            self._say(f"Drafted transmittal {number}; issuing it failed: {composer.issue_error}")
        else:
            self._say(f"Drafted transmittal {number}.")

    def action_filter(self) -> None:
        self.query_one("#docs-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#docs-filter", Input).value = ""
            self.query_one("#docs-table", DataTable).focus()
            return
        self.dismiss(None)
