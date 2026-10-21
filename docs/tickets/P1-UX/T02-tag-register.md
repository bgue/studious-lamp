# P1-UX-T02 — Tag register: Enter opens the record screen, plain text, tag Details

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3 (merged)
Branch: `p1/ux-t02-tag-register`

## Goal
In the tag register (F8) Enter on a row opens the full record screen; its Details tab shows the tag's own fields with labels
(a new renderer `details/tags.py`), its Properties tab already lists the class sets (S2). Table, panel and status line speak plain:
`Control valve`, not `ControlValve`; `Number parts`, not `area=47 mnemonic=FV`; property paths as labels. Technical mode adds the raw lines.

## Brief references (pasted)
> SCOPE clause 1: Enter opens the full record view; Esc returns on the same row. Clause 2: type labels, not class names (`Control valve`,
> not `ControlValve` or `engineering.Tag`); property labels, not keys (`Body material`, not `valve_data.body_material`); set labels
> (`Valve data`); hidden: ids, hashes, internal keys. Clause 3: technical mode shows what plain hides.
> D14: define `refresh_for_display_mode(self) -> None`. Learning (S2): a `DataTable` consumes Enter before a screen binding; use
> `DataTable.RowSelected`, never a priority binding (it would steal Enter from the filter `Input`).
> S2 getter table: `get_tag(project, key)`, key = `record["key"]` (the tag number); project is the `project` argument the renderer receives.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/record_screen.py (merged)
def open_record(screen: Screen[Any], client: ClientInterface, scope: str, project: str, actor: str, record_id: str) -> None
# tl_tui/details/__init__.py (merged): a module in this package is imported once; register by record type
@dataclass(frozen=True) class DetailRow: label: str; value: str; technical: bool = False
DetailRenderer = Callable[[ClientInterface, str, dict[str, Any], Labels], list[DetailRow]]   # (client, project, record, labels)
def register(*record_types: str) -> Callable[[DetailRenderer], DetailRenderer]
# tl_tui/details/generic.py: technical_rows(record) -> list[DetailRow]   (Key, Version, Scope, Schema hash; all technical=True)
# tl_tui/details/documents.py (model to follow): @register("documents.Document") def document_rows(client, project, record, labels)
#   rows Type (type_label), Number, Title, ..., Created/Updated (timestamp(record.get("created_at"))), Conformance (conformance_mark), then + technical_rows(record)
# tl_tui/display.py: humanize, type_label(labels, "engineering.Tag") -> "Tag", mode_of(app).technical, Labels
# tl_tui/labels_load.py: load_labels(client, scope, record_types=("core.Record",)) -> Labels   (never raises)
# tl_tui/tag_text.py (today)
COLUMNS = ("Number", "Class", "Status", "No.", "Conf", "Title")
def row_cells(view: TagView) -> tuple[str, ...]    # number, class_code or "-", status or "-", "ok"|"BAD", conformance, title
def detail_lines(view: TagView) -> list[str]
#   "class {class_code} | status ... | conformance {c}";  f"number {view.number_status}: {segments}" (segments "area=47 mnemonic=FV seq=1001")
#   violation: f"  ! {segment or 'number'}: {message} ({level})";  issues: f"  {issue.level}  {issue.path} {issue.message}"  (path "psets.valve_data.body_material")
def summary_line(shown, total, *, class_code, violations_only, include_ended, text) -> str   # part f"class {class_code}"
# TagView fields: id number title class_code status segments number_status violations conformance version psets issues
# widgets/tag_register.py (today): TagRegisterScreen(client, project); no actor; table "#tags-table" (row key = number); self.shown; _fill(keep); _describe(); _number()
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/tag_register.py`, `tag_text.py`
- `packages/tl-tui/src/tl_tui/details/documents.py` (the model), `details/generic.py`
- `packages/tl-tui/tests/test_tag_text.py`, `test_tag_register.py`, `test_record_screen.py` (Enter/Esc pattern, lines 1-120)
- `packages/tl-tui/tests/fakes.py` (`FakeClient.add_stored_record`, new: registers a record under the tag view's id so Enter finds it)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/tag_register.py`, `packages/tl-tui/src/tl_tui/tag_text.py`
- `packages/tl-tui/src/tl_tui/details/tags.py` (create)
- `packages/tl-tui/tests/test_tag_text.py`, `test_tag_register.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_tag_plain.py` (create)
- `docs/reports/P1-UX/T02.md` (create)

## Steps
1. `tag_text`: `COLUMNS = ("Number", "Class", "Status", "Number check", "Conformance", "Title")`; `row_cells(view, labels=None)`: Class via
   `humanize(view.class_code)` (a tag class is not in the type table; `-` when none), the check cell `ok` or `does not fit`, Conformance via
   `conformance_mark`. `detail_lines(view, labels=None, *, technical=False)`: the number line reads `number ok` or `number does not fit the pattern`
   then `Area 47, Mnemonic FV, Seq 1001` (`humanize(name)` + value) in plain mode, today's `area=47 ...` only when `technical`; each issue line
   shows its path as labels: drop a leading `psets`, `humanize` each remaining part, join with ` / ` (`Valve data / Body material`), raw path when `technical`.
   `summary_line(..., labels=None)`: class shown humanized.
2. `details/tags.py`: `@register("engineering.Tag") def tag_rows(client, project, record, labels)` reads `client.get_tag(project, str(record["key"]))`;
   rows Type (`type_label`), Number, Title, Class (humanized), Status (`humanize`, `—` when none), Number check, Conformance, Created, Updated, then
   `technical_rows(record)`; if the tag has issues add one row `Lacks` per issue with the label path and message.
3. Register: `on_mount` sets `self.labels = load_labels(self.client, f"project:{self.project}", ("engineering.Tag",))`; read
   `technical = mode_of(self.app).technical` where rows and the panel are built.
4. Add `on_data_table_row_selected(self, event)`: `event.stop()`, `view = self.shown[event.cursor_row]` (guard the index), then
   `open_record(self, self.client, f"project:{self.project}", self.project, str(getattr(self.app, "actor", "user:dev")), view.id)`.
5. Add `refresh_for_display_mode(self) -> None`: `self._fill(self._number())`.
6. Update existing pinned expectations (`No.`, `Conf`, `area=`, `ControlValve`) to the plain words; keep one technical assertion.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_tag_text.py packages/tl-tui/tests/test_tag_register.py packages/tl-tui/tests/test_tag_plain.py packages/tl-tui/tests/test_details_registry.py packages/tl-tui/tests/test_record_screen.py packages/tl-tui/tests/test_embedded_tags.py
```
Gate paths: all exist at dispatch except `test_tag_plain.py` (new, this ticket creates it). Expected: `gate: PASS`. No snapshot test shows this screen. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_tag_plain.py` (TlApp on `FakeClient` as `test_tag_register.py` does; for Enter use
`client.add_stored_record(view.id, view.number, "engineering.Tag", view.title)`):
- `test_enter_opens_the_record_screen_with_the_tag_details_and_escape_returns_to_the_same_row`.
- `test_enter_in_the_filter_box_does_not_open_a_record`.
- `test_a_tag_the_viewer_cannot_read_opens_as_no_record` (no stored record; no id in the text).
- `test_plain_text_names_the_class_and_the_properties_in_words` (`Control valve`, `Valve data / Body material`, none of `ControlValve`, `psets.`, `area=`; `find_technical(text) == []`).
- `test_technical_mode_shows_the_raw_path_and_segments_and_back` (flag on, `refresh_for_display_mode()`, then off).
- `test_the_tag_renderer_rows_with_a_failing_read_fall_back_to_generic_rows_and_a_note` (call `details_for(...)` with a client whose `get_tag` raises; generic rows plus the `Note` row).

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- `FakeClient.add_stored_record` does not make the record screen open: stop (fix would be in `fakes.py`).
- The Properties tab for the tag shows no class sets in the fake: that is S2's tested path with real services; note it, do not fix.
- Plain text still shows an id, hash or `x@1.2.3`: list it; fix only inside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
