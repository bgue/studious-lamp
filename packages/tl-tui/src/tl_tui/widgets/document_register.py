"""The document register: a project's controlled documents, their revisions and links (P1-I2).

A full-size modal opened with ``F7``. The table lists the project's documents by number with their
state and current revision (``B(IFC)``). The panel under it describes the highlighted document: its
revisions with their files, and the links to it, a stale pin marked ``!``. Everything is read
through the client. The two changes a person makes from here are their own dialogs: ``r`` re-pins
the first stale link of the highlighted document (after showing what changed) and ``t`` drafts a
transmittal. The filter keys narrow the list on the screen (state, type, text); ``a`` asks the
client for the void documents too.

STUB (P1-I2-T13b): the bodies of the reload, _fill, _describe, action_repin and action_transmittal
methods raise NotImplementedError; their signatures, options, docstrings and the helpers are
final. Each body has a STEPS comment. Implement them, then delete this paragraph, the STEPS
comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

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
from tl_tui.document_text import (
    COLUMNS,
    detail_lines,
    next_choice,
    row_cells,
    stale_links,
    summary_line,
)
from tl_tui.errors import CLIENT_ERRORS, describe_error
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

    def __init__(self, client: ClientInterface, project: str, actor: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.state: str | None = None
        self.doc_type: str | None = None
        self.include_void = False
        self.text = ""
        self.views: list[DocumentView] = []  # as listed, before the screen's own filters
        self.shown: list[DocumentView] = []
        self.detail: DocumentView | None = None  # the highlighted document, in full

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
        self.query_one("#docs-table", DataTable).add_columns(*COLUMNS)
        self.reload()
        self.query_one("#docs-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the list again and keep the highlighted document where it is."""
        # STEPS
        # 1. keep = self._number(). Try self.views = self.client.list_documents(self.project,
        #    include_void=self.include_void, limit=MAX_DOCUMENTS). On CLIENT_ERRORS call
        #    self._say(describe_error(exc), error=True) and return.
        # 2. self._fill(keep).
        raise NotImplementedError

    def _fill(self, keep: str | None = None) -> None:
        """Apply the screen's filters to ``self.views`` and fill the table."""
        # STEPS
        # 1. needle = self.text.strip().lower(). self.shown = the views whose state equals
        #    self.state (when set), whose doc_type equals self.doc_type (when set) and whose
        #    number or title contains the needle (when there is one), compared in lower case.
        # 2. table = the #docs-table DataTable; table.clear(); for each shown view add a row of
        #    Text(cell) for each cell of row_cells(view), with key=view.number (Text, not str: a
        #    cell is read as markup).
        # 3. When something is shown: move the cursor to the row of `keep` when it is still
        #    listed, else to row 0.
        # 4. Update #docs-status with summary_line(len(self.shown), len(self.views),
        #    state=self.state, doc_type=self.doc_type, include_void=self.include_void,
        #    text=self.text). Then call self._describe().
        raise NotImplementedError

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
        # STEPS
        # 1. detail = the #docs-detail Static; view = self.current(). With no view set
        #    self.detail = None, show "No document matches." and return.
        # 2. Try full = self.client.get_document(self.project, view.number). On CLIENT_ERRORS use
        #    full = view (the listing's copy: no revisions) and call self._say(describe_error(exc),
        #    error=True).
        # 3. self.detail = full; detail.update("\n".join(detail_lines(full))).
        raise NotImplementedError

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
        # STEPS
        # 1. Do nothing when the focus is an Input (the key is text). When self.detail is None,
        #    say "No document is highlighted." and return.
        # 2. found = stale_links(self.detail). With none, say "<number> has no stale link to
        #    re-pin." and return.
        # 3. self.app.push_screen(RepinScreen(self.client, self.project, self.detail.number,
        #    found[0], self.actor), self._repinned).
        raise NotImplementedError

    def _repinned(self, moved: bool | None) -> None:
        """The re-pin dialog closed: read again when a link was moved."""
        if moved:
            self.reload()
            self._say("Link re-pinned.")

    def action_transmittal(self) -> None:
        """Draft a transmittal, starting from the highlighted document's current revision."""
        # STEPS
        # 1. Do nothing when the focus is an Input (the key is text).
        # 2. number = self._number(). self.app.push_screen(TransmittalComposerScreen(self.client,
        #    self.project, self.actor, document=number), self._drafted).
        raise NotImplementedError

    def _drafted(self, number: str | None) -> None:
        """The composer closed: say which transmittal was drafted."""
        if number:
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
