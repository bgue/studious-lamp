# P0-I2-T16b — Edit form: Ctrl+S saves core and pset changes

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T14, P0-I2-T15, P0-I2-T16a, and the supervisor's `tl_tui/forms.py` (all merged on `p0/i2b`)
Branch: `p0/i2b-t16b-edit-form`

## Goal
Pressing `e` in the record view opens a modal form with one editor per writable field of the record: title and
description, then each pset group's properties. `Ctrl+S` validates, sends only the changed fields through
`save_record_edits` (already written), and closes; the record view then reloads. Failures stay visible and nothing is lost.

## Brief references (pasted)
> Forms: Auto-generated from schema + pset definitions; field-level validation (§10.2)
> Keys: `e` Edit · `Ctrl+S` Save · `Esc` Back / close overlay · `Tab` next field (§10.4, sketch 2 footer: `e edit  Tab next`)
> `Pset.ValuesSet` events record the effective schema hash they were validated against (§6.3). Enrichment and source layers are never user-writable (§6.3).
> Live data: "record view shows 'updated by X — reload/merge' on conflict" (§10.3): here a conflict is shown as text and the form stays open.

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns, docstrings and comments included. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- `Static` parses `[...]` as markup: use `markup=False`.
- Do not name an attribute after a Textual `Widget`/`Screen` attribute (`visible`, `size`, `region`, `id`...).
- Textual 8.2.8: an `Input` with text must be created inside a running app; `FieldEditor` already builds its widgets in `compose`, so create editors inside `compose` too.
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text`.
- A screen reads and writes through `ClientInterface` and the helpers in `tl_tui/forms.py` only. It never imports `tl_core.services` handlers.
- You may commit your report as `docs/reports/P0-I2/P0-I2-T16b.md` (allowed in *Allowed paths*).

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/forms.py (existing; do not change)
@dataclass
class SaveOutcome:
    version: int
    applied: list[str]          # e.g. ["core", "valve_data/standard", "valve_data/custom"]
    failed: str | None          # label of the command that failed, e.g. "valve_data/custom"
    error: Exception | None
    @property
    def ok(self) -> bool: ...
def save_record_edits(client: ClientInterface, *, scope: str, actor: str, record: dict[str, Any],
                      meta: FormMetadata, edits: dict[str, Any], source: str = "tui") -> SaveOutcome: ...
# edits are keyed by FieldMeta.path ("title", "description", "psets.valve_data.size_in", ...); a cleared field is None.
# It raises ValueError for an unknown or read-only path; it returns (does not raise) service failures.

# packages/tl-tui/src/tl_tui/widgets/form_fields.py (existing)
class FieldEditor(Vertical):
    def __init__(self, meta: FieldMeta, value: Any = None, *, id: str | None = None) -> None: ...
    meta: FieldMeta
    value -> Any; changed -> bool; error -> str | None
    def validate(self) -> bool: ...        # shows the inline error; True when valid
    class Edited(Message): ...

# packages/tl-schema/src/tl_schema/forms.py (existing, frozen)
class FormMetadata(BaseModel):  record_type; effective_schema_hash; core_fields: list[FieldMeta]; psets: list[PsetGroupMeta]
class PsetGroupMeta(BaseModel): name; label; package; version; enforcement; layer; fields: list[FieldMeta]
class FieldMeta(BaseModel):     path; label; kind; layer; readonly: bool; group: str; ...   # core fields have group "details" and path "title"/"description"

# packages/tl-tui/src/tl_tui/paths.py:  def pset_value(psets: dict[str, Any], path: str) -> Any
# packages/tl-tui/src/tl_tui/errors.py: def describe_error(exc: BaseException) -> str   (ConcurrencyError -> "this record changed since you opened it; reload and try again")
# packages/tl-tui/src/tl_tui/messages.py
class StatusMessage(Message):  def __init__(self, text: str, severity: Severity = "info") -> None
class RecordChanged(Message):  def __init__(self, record_id: str) -> None
# packages/tl-tui/src/tl_tui/client.py:  form_metadata(self, scope, record_type) -> FormMetadata   (may raise CLIENT_ERRORS or NotImplementedError)

# NEW: packages/tl-tui/src/tl_tui/widgets/edit_form.py
def editor_id(path: str) -> str: ...        # "f_" + path with every "." replaced by "_"
class EditForm(ModalScreen[bool]):
    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S save  Esc cancel"
    def __init__(self, client: ClientInterface, scope: str, record: dict[str, Any],
                 meta: FormMetadata, *, actor: str = "user:dev") -> None: ...
    # attributes: client, scope, record, meta, actor, editors: list[FieldEditor], headings: list[str]
```

Rules for `EditForm`:
- Bindings: `ctrl+s` runs `save`; `escape` runs `cancel` (`dismiss(False)`, nothing sent).
- Layout (centred, about 80% wide and 90% high, `Vertical` with a border): a `Static` `f"Edit {record['key']}"`; a `VerticalScroll` containing, in order,
  a group heading, then the editors of that group. Groups: first `"Details"` with the `meta.core_fields` that are not `readonly`; then for each `meta.psets` group
  that has at least one non-readonly field, a heading `f"{group.name}   {group.package} {group.version}"` (three spaces) and the non-readonly fields in listed order.
  Headings are `Static(..., classes="form-group", markup=False)`; each heading text is also appended to `self.headings`. After the scroll area: a `Static` id `form-status`
  (`markup=False`), then a `Horizontal` with `Button("Save", id="save", variant="primary")` and `Button("Cancel", id="cancel")`.
- One `FieldEditor` per field, `id=editor_id(field.path)`, appended to `self.editors`, initial value: for a core field `record.get(field.path)`, for a pset field
  `pset_value(record.get("psets") or {}, field.path)`.
- Save (`ctrl+s` or the Save button):
  1. `invalid = [e for e in self.editors if not e.validate()]`; if any: status `f"Fix {len(invalid)} field(s) first"` and stop.
  2. `edits = {e.meta.path: e.value for e in self.editors if e.changed}`; if empty: status `"No changes to save"` and stop.
  3. `outcome = save_record_edits(client, scope=..., actor=self.actor, record=self.record, meta=self.meta, edits=edits)`.
  4. `outcome.ok`: `dismiss(True)`.
  5. Not ok and `outcome.applied` is non-empty (partly saved): post `StatusMessage(f"Saved {', '.join(applied)}; failed {outcome.failed}: {reason}", "error")` and `dismiss(True)`;
     `reason` is `describe_error(outcome.error)`.
  6. Not ok and nothing applied: set the form status to `f"Not saved: {reason}"` and stay open.
  The Cancel button runs `cancel`.
- `DEFAULT_CSS`: centre the screen (`EditForm { align: center middle; }`), size the `Vertical` as above, `.form-group { text-style: bold; margin: 1 0 0 0; }`.

Change to `RecordView` (`widgets/record_view.py`, this is the only edit there):
- Add `Binding("e", "edit", show=False)` and change `KEY_HINTS` to `"Esc back  [ ] prev/next  h history  e edit"`.
- Add `action_edit`: do nothing when `self.record is None`. Otherwise `meta = self.client.form_metadata(self.scope, record["type"])` (function-level import of `EditForm`, because `edit_form` is a new module).
  On `NotImplementedError` post `StatusMessage("Editing needs the pset services", "warning")` and stop; on `CLIENT_ERRORS` post `StatusMessage(describe_error(exc), "error")` and stop.
  Then `self.app.push_screen(EditForm(self.client, self.scope, record, meta, actor=actor), saved)` where `actor = str(getattr(self.app, "actor", "user:dev"))` and
  `saved(done)` posts `RecordChanged(record["id"])` when `done` is true.

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/forms.py`
- `packages/tl-tui/src/tl_tui/widgets/form_fields.py`
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`
- `packages/tl-tui/tests/fakes.py` (read only)
- `docs/tickets/P0-I2/provided/test_edit_form.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/edit_form.py` (create)
- `packages/tl-tui/src/tl_tui/widgets/record_view.py` (edit: the binding, the hint, `action_edit` only)
- `packages/tl-tui/tests/test_edit_form.py` (create by copying the provided file; do not edit it)
- `docs/reports/P0-I2/P0-I2-T16b.md` (your report)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_edit_form.py.txt packages/tl-tui/tests/test_edit_form.py`
2. Create `edit_form.py`; add the binding, hint and action to `record_view.py`.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_edit_form.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass (`test_record_view.py` and `test_app_shell.py` unchanged and green).

## Tests to add
None beyond the provided file. It covers the field list and headings, save of core and pset changes in layer order with the right actor, the Save button, invalid input,
no changes, cancel, a stale record, a partial save, `e` from the record view with refresh, and `e` without pset services.

## Report requirements
Standard report, committed at `docs/reports/P0-I2/P0-I2-T16b.md`. State that the provided test file is byte-identical to the `.txt` and list the lines you changed in `record_view.py`.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing a file outside *Allowed paths*.
- Stop if `save_record_edits` or `FieldEditor` does not behave as pasted: do not patch them; they are supervisor-owned.

## Blocked

## Decision
