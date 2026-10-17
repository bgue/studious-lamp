"""The derived documents: a project's extracted data, its validation report and its diff (P1-I3).

A full-size modal opened with ``F11``. The table lists the project's derived documents with their
state, the number of the latest pass, rows and errors. The panel under it describes the highlighted
one: its passes and running job, and either its validation report (issues by row and column) or
its diff against the previous pass (``d`` toggles). ``x`` queues an extraction, ``v`` queues a
validation again, ``j`` opens the job monitor and ``p`` the publish preview. Everything is read
and written through the client; the screen shows what the module found and decides nothing.

STUB (P1-I3-T07b): the bodies of _describe, _fill, action_extract, action_validate, reload raise
NotImplementedError; their signatures, options, docstrings and the helpers are final. Each body
has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the
lint-silencing lines.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
# pyright: reportUnusedImport=false, reportUnusedVariable=false

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_documents.derivation.derived import StartExtraction, ValidateDerived
from tl_mod_documents.derivation.views import DerivedSummary, DerivedView

from tl_tui.client import ClientInterface
from tl_tui.derive_text import (
    DERIVED_COLUMNS,
    derived_cells,
    derived_detail_lines,
    diff_lines,
    next_choice,
    report_lines,
    summary_line,
)
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.widgets.job_monitor import JobMonitorScreen
from tl_tui.widgets.publish_preview import PublishPreviewScreen

MAX_DERIVED = 1000


class DerivedDocumentsScreen(ModalScreen[None]):
    """The derived documents of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "s state  d report/diff  x extract  v validate  j jobs  p publish  / filter  "
        "F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state_filter", "State", show=False),
        Binding("d", "toggle_diff", "Report or diff", show=False),
        Binding("x", "extract", "Extract", show=False),
        Binding("v", "validate", "Validate", show=False),
        Binding("j", "jobs", "Jobs", show=False),
        Binding("p", "publish", "Publish", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    DerivedDocumentsScreen { background: $surface; }
    DerivedDocumentsScreen > Vertical { padding: 0 1; }
    DerivedDocumentsScreen #dd-title { text-style: bold; height: 1; }
    DerivedDocumentsScreen #dd-filter { height: 3; }
    DerivedDocumentsScreen #dd-table { height: 1fr; min-height: 6; }
    DerivedDocumentsScreen #dd-detail { height: 16; border-top: solid $accent; padding: 0 1; }
    DerivedDocumentsScreen #dd-status { height: 1; }
    DerivedDocumentsScreen #dd-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        actor: str,
        *,
        is_admin: bool = False,
        is_controller: bool = False,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.actor = actor
        self.is_admin = is_admin
        self.is_controller = is_controller or is_admin
        self.state: str | None = None
        self.text = ""
        self.show_diff = False  # False: the validation report; True: the diff against the last pass
        self.views: list[DerivedSummary] = []  # as listed, before the screen's own filters
        self.shown: list[DerivedSummary] = []
        self.detail: DerivedView | None = None  # the highlighted derived document, in full

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Derived documents of {self.project}", markup=False, id="dd-title")
            yield Input(placeholder="Filter by key or title", id="dd-filter")
            yield DataTable[str](id="dd-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="dd-detail")
            yield Static("", markup=False, id="dd-status")
            yield Static(self.KEY_HINTS, markup=False, id="dd-hints")

    def on_mount(self) -> None:
        self.query_one("#dd-table", DataTable).add_columns(*DERIVED_COLUMNS)
        self.reload()
        self.query_one("#dd-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the list again and keep the highlighted derived document where it is."""
        # STEPS (P1-I3-T07b)
        # 1. keep = self._key().
        # 2. Try self.views = self.client.list_derived_documents(self.project,
        #    limit=MAX_DERIVED); on CLIENT_ERRORS say describe_error(exc) with error=True and
        #    return.
        # 3. Call self._fill(keep).
        raise NotImplementedError

    def _fill(self, keep: str | None = None) -> None:
        """Apply the screen's filters to ``self.views`` and fill the table."""
        # STEPS (P1-I3-T07b)
        # 1. needle = self.text.strip().lower(); self.shown = views whose state matches
        #    self.state (when set) and whose key or title contains the needle (when set).
        # 2. table = #dd-table: clear it and add one row per shown view: Text(cell) for each cell
        #    of derived_cells(view), key=view.key.
        # 3. When there are rows, move the cursor to the row of keep (else row 0).
        # 4. Update #dd-status with summary_line(len(self.shown), len(self.views),
        #    state=self.state, text=self.text), then call self._describe().
        raise NotImplementedError

    def _key(self) -> str | None:
        view = self.current()
        return view.key if view is not None else None

    def current(self) -> DerivedSummary | None:
        table = self.query_one("#dd-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _describe(self) -> None:
        """Show the highlighted document with its passes and its report or diff."""
        # STEPS (P1-I3-T07b)
        # 1. detail = #dd-detail; view = self.current(). With none set self.detail = None and
        #    show "No derived document matches.".
        # 2. Try full = self.client.get_derived_document(self.project, view.key); on
        #    CLIENT_ERRORS set self.detail = None, show describe_error(exc) in the panel and on
        #    the status line (error=True), and return.
        # 3. Set self.detail = full; lines = derived_detail_lines(full); when full.content_rev >
        #    0 append "" and then self._body(full); show "\n".join(lines).
        raise NotImplementedError

    def _body(self, full: DerivedView) -> list[str]:
        """The report of the latest pass, or the diff against the pass before it."""
        try:
            if self.show_diff:
                return [
                    "diff against the previous pass:",
                    *diff_lines(self.client.get_derived_diff(self.project, full.key)),
                ]
            if not any(
                c.report_file_id for c in full.contents if c.content_rev == full.content_rev
            ):
                return ["not validated yet"]
            return [
                "report:",
                *report_lines(self.client.get_derived_report(self.project, full.key)),
            ]
        except CLIENT_ERRORS as exc:
            return [describe_error(exc)]

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#dd-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.text = event.value
        self._fill(self._key())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#dd-table", DataTable).focus()

    # --- actions -------------------------------------------------------------------------

    def action_state_filter(self) -> None:
        """Show the next state: all, then each state that has a derived document, then all."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state = next_choice(self.state, [v.state for v in self.views])
        self._fill(self._key())

    def action_toggle_diff(self) -> None:
        """Switch the panel between the validation report and the diff against the last pass."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.show_diff = not self.show_diff
        self._describe()

    def action_extract(self) -> None:
        """Queue an extraction for the highlighted derived document (any signed-in person)."""
        # STEPS (P1-I3-T07b)
        # 1. If self.focused is an Input return (the key is text).
        # 2. view = self.current(); with none say "No derived document is highlighted." and
        #    return.
        # 3. Try self.client.start_extraction(StartExtraction(actor=self.actor, source="tui",
        #    scope=f"project:{self.project}", derived_id=view.id)); on CLIENT_ERRORS say
        #    describe_error(exc) with error=True and return.
        # 4. Call self.reload() and then say f"Queued an extraction for {view.key}." (say it
        #    last: the reload rewrites the status line).
        raise NotImplementedError

    def action_validate(self) -> None:
        """Queue a validation of the latest pass of the highlighted derived document."""
        # STEPS (P1-I3-T07b)
        # 1. As action_extract, but call
        #    self.client.validate_derived(ValidateDerived(actor=self.actor, source="tui",
        #    scope=f"project:{self.project}", derived_id=view.id)).
        # 2. After self.reload() say f"Queued a validation of {view.key}."
        raise NotImplementedError

    def action_jobs(self) -> None:
        """Open the job monitor, on the highlighted document's jobs when one is highlighted."""
        if isinstance(self.focused, Input):
            return  # the key is text
        view = self.current()
        self.app.push_screen(
            JobMonitorScreen(
                self.client, self.project, self.actor, derived=view.key if view else None
            ),
            lambda _: self.reload(),
        )

    def action_publish(self) -> None:
        """Open the publish preview of the highlighted derived document."""
        if isinstance(self.focused, Input):
            return  # the key is text
        view = self.current()
        if view is None:
            self._say("No derived document is highlighted.")
            return
        self.app.push_screen(
            PublishPreviewScreen(
                self.client,
                self.project,
                self.actor,
                view.key,
                is_admin=self.is_admin,
                is_controller=self.is_controller,
            ),
            self._published,
        )

    def _published(self, changed: bool | None) -> None:
        """The preview closed: read again when records were created or taken back."""
        if changed:
            self.reload()

    def action_filter(self) -> None:
        self.query_one("#dd-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#dd-filter", Input).value = ""
            self.query_one("#dd-table", DataTable).focus()
            return
        self.dismiss(None)
