# P1-UX-T01 — Documents register: Enter opens the record screen, plain text

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3 (merged)
Branch: `p1/ux-t01-documents-register`

## Goal
In the document register (F7) Enter on a row opens the full record screen (Details, Properties, Links, History, Thread) and
Esc returns to the register on the same row. In plain mode the table, the panel and the status line speak in labels:
`Piping`, not `PIP`; `Registered`, not a stored word in any other form; no `core.Record` class names. Technical mode adds the
lines plain hides. The document Details renderer already exists (`details/documents.py`, S2): this ticket does not touch it.

## Brief references (pasted)
> SCOPE clause 1: Enter on any row opens the full record view; Escape returns to the list on the same row.
> Clause 2: code-list names, not codes (`Piping`, not `PIP`); type labels, not class names; hidden by default: ids, hashes, schema
> versions, internal keys. Clause 3: technical mode shows what plain hides.
> D14: a widget whose text depends on the mode defines `refresh_for_display_mode(self) -> None` (T10 calls it on every toggle).
> Learning (S2): a `DataTable` consumes Enter before a screen binding, and a priority binding would steal Enter from the filter
> `Input`. Handle `DataTable.RowSelected` instead.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/record_screen.py (merged)
def open_record(screen: Screen[Any], client: ClientInterface, scope: str, project: str, actor: str, record_id: str) -> None
# opens RecordScreen (ModalScreen[None]); "No record" when the id is hidden or missing; Esc = dismiss(None)
# tl_tui/labels_load.py (merged): never raises, a failed read leaves its part empty
def load_labels(client: ClientInterface, scope: str, record_types: Iterable[str] = ("core.Record",)) -> Labels
# tl_tui/display.py (merged)
def code_label(labels: Labels, list_name: str, code: str | None) -> str   # label, else the code, else "—"
def type_label(labels: Labels, record_type: str) -> str                   # title, else humanized name
def humanize(name: str) -> str                                            # "Registered" stays; "under_review" -> "Under review"
def mode_of(widget_or_app: object) -> DisplayMode                         # pass the APP (self.app), never a widget; .technical
# tl_tui/document_text.py (today)
COLUMNS = ("Number", "State", "Current", "Type", "Disc", "Title")
def row_cells(view: DocumentView) -> tuple[str, ...]   # (number, state, current_text, doc_type or "-", discipline or "-", title)
def link_line(link: DocumentLinkView) -> str           # f"{mark} {who} ({link.from_type}) {pin}" ...   from_type is "core.Record"
def detail_lines(view: DocumentView) -> list[str]      # line 2: f"state ... | type ... | discipline ... | scheme {view.revision_scheme}"
def summary_line(shown, total, *, state, doc_type, include_void, text) -> str   # parts "state X", "type X"
# widgets/document_register.py (today): self.project, self.actor; table "#docs-table" (row key = number); self.shown: list[DocumentView];
#   _fill(keep) rebuilds rows with row_cells(view); _describe() calls detail_lines(full); status "#docs-status"
# DocumentView.id is the record id; code lists are named "doc_type" and "discipline" in labels.code_labels.
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/document_register.py`, `document_text.py`
- `packages/tl-tui/tests/test_document_text.py`, `test_document_register.py`, `test_record_screen.py` (the Enter/Esc pattern, lines 1-120)
- `packages/tl-tui/tests/fakes.py` (`FakeClient.add_stored_record`, new: registers a record under a module fake's view id so Enter finds it)
may explore: `packages/tl-tui/tests/fakes_documents.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/document_register.py`, `packages/tl-tui/src/tl_tui/document_text.py`
- `packages/tl-tui/tests/test_document_text.py`, `test_document_register.py`, `test_document_flow.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_document_plain.py` (create)
- `docs/reports/P1-UX/T01.md` (create)

## Steps
1. `document_text`: every function that prints a code takes `labels: Labels | None = None` (default `Labels()`); add `technical: bool = False`
   where noted. `COLUMNS = ("Number", "State", "Current", "Type", "Discipline", "Title")`. `row_cells(view, labels=None)`: State via
   `humanize(view.state)`, Type via `code_label(labels, "doc_type", ...)`, Discipline via `code_label(labels, "discipline", ...)`.
   `link_line(link, labels=None)`: `type_label(labels, link.from_type)` instead of the raw class name. `detail_lines(view, labels=None, *, technical=False)`:
   same label rules; the `scheme ...` text, a `record {view.id}` line and `version {view.version}` appear only when `technical`.
   `summary_line(..., labels=None)`: `type` shows the label. Filters still compare stored codes.
2. Register: in `on_mount` set `self.labels = load_labels(self.client, f"project:{self.project}", ("documents.Document",))`;
   read `technical = mode_of(self.app).technical` where rows, the panel and the status line are built and pass it and `self.labels`.
3. Add `on_data_table_row_selected(self, event)`: `event.stop()`, take `self.shown[event.cursor_row]` (guard the index), then
   `open_record(self, self.client, f"project:{self.project}", self.project, self.actor, view.id)`.
4. Add `refresh_for_display_mode(self) -> None`: `self._fill(self._number())` (keeps the row; the panel is rebuilt by `_fill`).
5. Update pinned expectations (`Disc`, `core.Record`, raw codes) in the existing tests to the plain words; keep one technical-mode assertion.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_document_text.py packages/tl-tui/tests/test_document_register.py packages/tl-tui/tests/test_document_flow.py packages/tl-tui/tests/test_document_plain.py packages/tl-tui/tests/test_details_registry.py packages/tl-tui/tests/test_record_screen.py
```
Gate paths: all exist at dispatch except `test_document_plain.py` (new, this ticket creates it). Expected: `gate: PASS`. No snapshot test shows this screen; do not run the whole suite. If a snapshot test fails, regenerate only that test's snapshots and name it.

## Tests to add
`packages/tl-tui/tests/test_document_plain.py` (TlApp on `FakeClient`; `client.seed_documents("P123")`; make Enter findable with
`client.add_stored_record(view.id, view.number, "documents.Document", view.title)` for each seeded view; set `client.metadata_by_type`/code
labels only if needed, else assert the code fallback):
- `test_enter_opens_the_record_screen_and_escape_returns_to_the_same_row` (move down, Enter: `RecordScreen` on top with the document's number in Details; Esc: register back, `cursor_row` unchanged).
- `test_enter_in_the_filter_box_does_not_open_a_record` (focus `#docs-filter`, press Enter: no `RecordScreen`, table focused).
- `test_a_row_the_viewer_cannot_read_opens_as_no_record` (do not add the stored record: the screen reads `No record`, and the view id is not in the text).
- `test_plain_text_has_labels_not_codes_or_class_names` (with `code_labels` for `doc_type` ISO -> `Isometric`, `discipline` PIP -> `Piping` set on the fake's metadata so `load_labels` finds them: the table and panel show them; `find_technical(text) == []`; `core.Record` absent).
- `test_technical_mode_adds_the_scheme_and_record_lines_and_back` (set `app.display_mode.technical = True`, call `screen.refresh_for_display_mode()`: `scheme alpha` and `record DOC-ISO-1234` show; off again: gone).

## Report requirements
Standard report. List each existing assertion changed and why (one line). Say how labels reached the fake.

## Escalation triggers
- `FakeClient.add_stored_record` does not make the record screen open (fix would be in `fakes.py`, not Allowed): stop.
- Enter on a row also moves the cursor or fires twice: report, do not add a priority binding.
- Plain text still shows an id, hash or `x@1.2.3` in this register: list it; fix only inside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
