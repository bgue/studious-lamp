# P1-I2-T13b — TUI: the document register (F7)

Status: ready
Tier: haiku
Labels: tui
Depends on: S17 on `p1/i2` (the document text functions, the client methods and the F7 binding, all in the tree); no other ticket
Branch: `p1/i2-t13b-tui-document-register`

## Goal
A person sees a project's controlled documents in the TUI: state, current revision with its status class, and under the table the highlighted document's revisions (a status class each) and links, with a stale pin marked. `packages/tl-tui/src/tl_tui/widgets/document_register.py` has the screen's layout, bindings, event handlers and four simple actions written; five methods (`reload`, `_fill`, `_describe`, `action_repin`, `action_transmittal`) raise `NotImplementedError`. You implement them. The text of every row and panel comes from `tl_tui/document_text.py` (final, in the tree). One provided test file must pass.

## Brief references (pasted)
> **Brief 10 TUI.** Screens are built on the client interface (`ClientInterface`); they never import the services. A screen shows what the services return and decides nothing.
>
> **Brief 9 M1 / 7.3.** A document has revisions; each issue status belongs to a status class (review, construction, record). A pinned link goes stale when a newer revision is issued in the same class or a later one (ADR-0012); its owner re-pins it after seeing what changed. The register shows the stale pin; `r` opens the re-pin dialog (another ticket) and `t` the transmittal composer (another ticket).

### Specification
- The screen is a modal like `TagRegisterScreen` (`widgets/tag_register.py`): a title, a filter input, a table, a detail panel, a status line and a line of key hints. Its layout (`compose`, `on_mount`), its bindings, its event handlers and the actions `action_state_filter`, `action_type_filter`, `action_void`, `action_filter`, `action_reload` and `action_close` are written. You fill the five marked methods.
- `reload` asks the client for the project's documents (`include_void` as the screen has it); `_fill` applies the screen's own filters (state, type, text) to what was read; `_describe` asks for the highlighted document with `get_document` so the panel can show its revisions and links; `action_repin` and `action_transmittal` push the two dialogs.
- A cell is a `rich.text.Text`, not a string.
- A client failure (`CLIENT_ERRORS`) is shown on the status line with `describe_error`; it never crashes the screen.
- The keys `s`, `y`, `a`, `r` and `t` do nothing while the filter input has focus (the letters are text).
- The row and panel text is built by `tl_tui/document_text.py` (`row_cells`, `detail_lines`, `stale_links`, `summary_line`, `next_choice`); do not build text here and do not edit that file.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/widgets/document_register.py` (the stub you complete):
```python
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
```

`packages/tl-tui/src/tl_tui/document_text.py` (excerpts; read-only, do not edit):
```python
def row_cells(view: DocumentView) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``COLUMNS``."""
    ...


def stale_links(view: DocumentView) -> list[DocumentLinkView]:
    """The links of a document that can be re-pinned: stale, and pinned to a revision."""
    ...


def detail_lines(view: DocumentView) -> list[str]:
    """The panel under the table for the highlighted document."""
    ...


def next_choice(current: str | None, choices: Sequence[str]) -> str | None:
    """The filter after ``current``: ``None`` (all), then each distinct choice, then ``None``."""
    ...


def summary_line(
    shown: int,
    total: int,
    *,
    state: str | None,
    doc_type: str | None,
    include_void: bool,
    text: str,
) -> str:
    """The status line under the table."""
    ...
```

`packages/tl-modules/documents/src/tl_mod_documents/views.py` (excerpts; read-only, do not edit):
```python
class RevisionView(BaseModel):
    id: str
    code: str
    state: str  # Draft | In Review | Issued | Superseded | Void
    issue_status: str | None
    status_class: str | None
    issued_on: str | None
    is_current: bool
    purpose: str | None
    change_note: str | None
    revision_date: str | None
    intended_status: str | None
    superseded_by: str | None  # the code of the revision that replaced it
    renditions: list[RenditionView] = []


class DocumentLinkView(BaseModel):
    """A link to the document and what its pin means now."""

    link_id: str
    from_key: str | None
    from_type: str
    from_title: str
    relation: str
    link_status: str  # active | stale
    pin: str | None  # None floats
    pin_state: str  # current | stale | floating | no_current | unknown
    current_code: str | None
    newer_codes: list[str]


class DocumentView(BaseModel):
    id: str
    number: str
    title: str
    description: str | None
    state: str
    doc_type: str | None
    discipline: str | None
    originator: str | None
    confidentiality: str | None = Field(description=CONFIDENTIALITY_NOTE)
    revision_scheme: str
    pattern_code: str | None
    current_revision_code: str | None
    current_revision_status: str | None
    current_revision_class: str | None
    current_revision_issued_on: str | None
    superseded_by: str | None  # the number of the document that replaced it
    conformance: str
    version: int
    revisions: list[RevisionView] = []
    links: list[DocumentLinkView] = []
```

`packages/tl-tui/src/tl_tui/client.py` (the document methods of `ClientInterface`; read-only):
```python
def list_documents(self, project: str, *, doc_type: str | None = None, discipline: str | None = None, state: str | None = None, include_void: bool = False, limit: int = 1000) -> list[DocumentView]: ...
def get_document(self, project: str, number: str) -> DocumentView: ...
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/document_register.py` (the file you edit)
- `packages/tl-tui/src/tl_tui/document_text.py` (final; the text of rows and panels)
- `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (a finished screen of the same shape; style)
- `packages/tl-tui/tests/fakes_documents.py` and `packages/tl-tui/tests/helpers.py` (the fake client and pilot helpers, already in the tree)
- `docs/tickets/P1-I2/provided/t13b-test_document_register.py.txt` (the test)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `standard` for `packages/tl-modules`, `tl-cli`, `tl-api`; strict for `tl_core`, `tl_schema`, `tl_adapters`.
- Provided files live under `docs/tickets/P1-I2/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I2/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8). A test that does not use the `db`, `world` or `engine` fixtures runs once under `--adapters sqlite,postgres`; one that does runs once per adapter (L-P1-I1-6).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*`, `hist_*` or `v_*` object, and never change `schema/**` or anything under `generated/` unless this ticket says so.
- `just test-parity` takes about 70 minutes for the whole repository (L-P1-I1-10): run only the scoped commands in *Acceptance* (a ticket whose tests do not use the database fixtures has no Postgres command), never the whole parity suite.
- Start Postgres with `sudo pg_ctlcluster 16 main start` if it is not running; `TL_PG_URL` is `postgresql://postgres:postgres@localhost:5432/tl_test`.
- A cell of a table is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup (L-P1-I1-9 in spirit; the tag register does the same).
- The screen reads and writes only through `ClientInterface` (`self.client`); it never imports a service, a handler or the database. The tests use `FakeClient` (`tests/fakes.py`, with the document methods of `tests/fakes_documents.py`).
- Key presses are tested with `pilot.press`; a letter key does nothing while an `Input` has focus.
- `uv run pytest packages/tl-tui -q` is the package gate; the TUI tests run once (they do not use the database fixtures).

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/document_register.py` (edit)
- `packages/tl-tui/tests/test_document_register.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I2/P1-I2-T13b.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I2/provided/t13b-test_document_register.py.txt` to `packages/tl-tui/tests/test_document_register.py`.
3. Implement the five methods by their STEPS comments; remove the STUB paragraph, the STEPS comments and the `ruff: noqa` line.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_document_register.py -q
uv run pytest packages/tl-tui -q
```
Expected: `just check` clean; 7 test functions pass; the whole package passes.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). There is no parity run for this ticket: its tests do not use the database fixtures, so Acceptance has no `--adapters` command.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths (for example in `document_text.py`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
