# P0-I2-T16c — New record form (`n`)

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T16a, P0-I2-T12 skeleton (merged on `p0/i2b`); independent of T16b
Branch: `p0/i2b-t16c-new-record`

## Goal
Pressing `n` in the app opens a modal with Key, Title and Description. `Ctrl+S` creates a `core.Record` through
`ClientInterface.create_record`, closes the form, refreshes the grid, shows "Created <key>" in the footer, and opens the new record.
Keys are typed by the user until numbering arrives in a later increment.

## Brief references (pasted)
> Keys: `n` New record (current type) · `Ctrl+S` Save · `Esc` Back / close overlay (§10.4)
> Forms: Auto-generated from schema + pset definitions; field-level validation (§10.2)
> Phase 0: record keys are explicit; the numbering service arrives in Increment 3 (build plan).

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns, docstrings and comments included. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- `Static` parses `[...]` as markup: use `markup=False`.
- Do not name an attribute after a Textual `Widget`/`Screen` attribute (`visible`, `size`, `region`, `id`...).
- Textual 8.2.8: create `FieldEditor`s (they hold `Input`s) inside `compose`, never in `__init__`.
- An app-level binding stays active under a modal; the `n` action must return at once when a modal screen is showing.
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text`.
- You may commit your report as `docs/reports/P0-I2/P0-I2-T16c.md`.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/client.py
def create_record(self, cmd: CreateRecord) -> CommandResult: ...      # may raise CLIENT_ERRORS (e.g. DuplicateKeyError)
# tl_core.services.commands
class CreateRecord(Command):
    record_type: str; title: str = Field(min_length=1); description: str | None = None; key: str | None = None; psets: dict[str, Any] = {}
    # Command: actor: str, source: str, scope: str
class CommandResult(BaseModel):  stream_id: str; key: str | None; version: int; events: list[Event]
# packages/tl-tui/src/tl_tui/widgets/form_fields.py
class FieldEditor(Vertical):
    def __init__(self, meta: FieldMeta, value: Any = None, *, id: str | None = None) -> None
    value -> Any (parsed; None when empty); def set_error(self, message: str | None) -> None
# packages/tl-schema/src/tl_schema/forms.py
class FieldMeta(BaseModel):
    path: str; label: str; description: str; kind: FieldKind; unit=None; enum_values=None; required_in_states=[]
    enforcement: Enforcement | None = None; layer: Layer; readonly: bool = False; group: str; order: int
# packages/tl-tui/src/tl_tui/errors.py: CLIENT_ERRORS: tuple[type[Exception], ...]; def describe_error(exc: BaseException) -> str
# packages/tl-tui/src/tl_tui/app.py (existing): TlApp has client, scope, record_type, actor; BINDINGS list; async def _show_record(self, scope, key);
#   query_one("#grid", RecordGrid).reload(); query_one("#footer", TlFooter).show_status(text, severity)

# NEW: packages/tl-tui/src/tl_tui/widgets/new_record_form.py
FIELDS: tuple[FieldMeta, ...]       # key, title, description
class NewRecordForm(ModalScreen[str | None]):
    KEY_HINTS: ClassVar[str] = "Tab next field  Ctrl+S create  Esc cancel"
    def __init__(self, client: ClientInterface, scope: str, *, record_type: str = "core.Record",
                 actor: str = "user:dev") -> None: ...
```

Rules for `FIELDS` (all `layer="core"`, `group="details"`): `FieldMeta(path="key", label="Key", description=..., kind="string", enforcement="required", order=1)`,
`path="title"`, label `Title`, `kind="string"`, `enforcement="required"`, `order=2`, and `path="description"`, label `Description`, `kind="text"`, no enforcement, `order=3`.
(The required marker `●` then shows in the label: `Key ●`.)

Rules for `NewRecordForm`:
- Bindings: `ctrl+s` runs `save`, `escape` runs `cancel` (`dismiss(None)`).
- Layout: centred, about 70% wide, `Vertical` with a border and `height: auto`: `Static("New record", markup=False)`, one `FieldEditor(field, id=f"new_{field.path}")` per entry of `FIELDS`,
  a `Static` id `form-status` (`markup=False`), and a `Horizontal` with `Button("Create", id="create", variant="primary")` and `Button("Cancel", id="cancel")`.
- Save: take the three editors. For the key and title editors whose `value` is empty call `set_error("Required")`; if any is empty set the status to `"Fill in the required fields"` and stop.
  Otherwise call `client.create_record(CreateRecord(actor=self.actor, source="tui", scope=self.scope, record_type=self.record_type, key=str(key.value), title=str(title.value), description=description.value))`.
  On `pydantic.ValidationError` or any `CLIENT_ERRORS` set the status to `f"Not created: {describe_error(exc)}"` and stay open (`ValidationError` first, it is also in `CLIENT_ERRORS`).
  On success `dismiss(result.key)`. The Create button runs `save`, Cancel runs `cancel`. An empty description editor gives `description=None` (that is what `FieldEditor.value` returns).

Rules for `TlApp` (`app.py`, the only edit there):
- Add `Binding("n", "new_record", "New", show=False)` to `BINDINGS`.
- Add `action_new_record(self) -> None`: return immediately if `isinstance(self.screen, ModalScreen)` (import `ModalScreen` from `textual.screen`). Otherwise (function-level import of `NewRecordForm`)
  `self.push_screen(NewRecordForm(self.client, self.scope, record_type=self.record_type or "core.Record", actor=self.actor), created)`, where
  `async def created(key: str | None) -> None` does nothing for `None`, else: `query_one("#grid", RecordGrid).reload()`, `query_one("#footer", TlFooter).show_status(f"Created {key}", "info")`, then `await self._show_record(self.scope, key)`.

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/app.py`
- `packages/tl-tui/src/tl_tui/widgets/form_fields.py`
- `packages/tl-tui/tests/fakes.py` (read only)
- `docs/tickets/P0-I2/provided/test_new_record_form.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/new_record_form.py` (create)
- `packages/tl-tui/src/tl_tui/app.py` (edit: the binding and `action_new_record` only; plus the `ModalScreen` import)
- `packages/tl-tui/tests/test_new_record_form.py` (create by copying the provided file; do not edit it)
- `docs/reports/P0-I2/P0-I2-T16c.md` (your report)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_new_record_form.py.txt packages/tl-tui/tests/test_new_record_form.py`
2. Create `new_record_form.py`; add the binding and action to `app.py`.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_new_record_form.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass (`test_app_shell.py` unchanged and green).

## Tests to add
None beyond the provided file. It covers the fields and required markers, creation with actor and source, empty description, missing key/title, a duplicate key, cancel,
`n` from the app (grid refresh, footer message, record opened), and typing `n` into a field.

## Report requirements
Standard report, committed at `docs/reports/P0-I2/P0-I2-T16c.md`. State that the provided test file is byte-identical to the `.txt` and list the lines you changed in `app.py`.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing a file outside *Allowed paths*.

## Blocked

## Decision
