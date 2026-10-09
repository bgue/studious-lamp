# P0-I2-T16a — Form field editors generated from field metadata

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T11 (merged on `p0/i2b`); independent of T15
Branch: `p0/i2b-t16a-form-fields`

## Goal
One widget, `FieldEditor`, that edits a single pset or core property from its `FieldMeta`: it picks an input widget by
field kind, shows the label with unit and enforcement marker, validates what the user types inline, and reports the
parsed value, whether it changed, and its error. Pure functions `parse_value` and `format_initial` hold the text rules.
A later ticket stacks editors into a form and saves through `SetPsetValues`.

## Brief references (pasted)
> Forms: Auto-generated from schema + pset definitions; field-level validation; lookup fields with inline search; "create and link" from lookups (§10.2)
> Property attributes: key, label, description (mandatory), data type (string, int, decimal, bool, date, datetime, enum, quantity-with-UOM, reference-to-record, ...), required/required-in-states, default, validation, unit, ... enforcement (§6.3)
> `locked`: as required, and projects cannot extend or tighten it. `enforcement` markers: ● required  ○ advisory  ■ locked (§10.6 sketch 2)
> Meaning never rides on colour alone (§10.3).

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns, docstrings and comments included. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- `Static` parses `[...]` as markup: pass `markup=False`.
- Do not name an attribute after a Textual `Widget` attribute. `Select.NULL` is the "nothing selected" sentinel; use
  `select.is_blank()` to test it. An `Input` posts `Changed` once at mount with its initial value; that must not count as an edit.
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text`.
- Shared display helpers: `tl_tui.text.unit_label(code)` (`"[in_i]"` becomes `"in"`).

## Interfaces (verbatim from repo at the branch point, plus the new module)
```python
# packages/tl-schema/src/tl_schema/forms.py (existing, frozen contract)
FieldKind = Literal["string", "text", "int", "decimal", "bool", "date", "datetime", "enum", "quantity", "ref", "json"]
class EnumValue(BaseModel):
    code: str; label: str; crosswalk: str | None = None
class FieldMeta(BaseModel):
    path: str; label: str; description: str; kind: FieldKind
    unit: str | None = None; enum_values: list[EnumValue] | None = None
    required_in_states: list[str] = []; enforcement: Literal["advisory", "required", "locked"] | None = None
    layer: Layer; readonly: bool = False; group: str; order: int

# packages/tl-tui/src/tl_tui/text.py (existing)
def unit_label(code: str | None) -> str

# NEW: packages/tl-tui/src/tl_tui/widgets/form_fields.py
PLACEHOLDERS: dict[str, str]
@dataclass(frozen=True)
class ParseResult:
    value: Any
    error: str | None = None
def parse_value(kind: FieldKind, text: str) -> ParseResult: ...
def format_initial(value: Any) -> str: ...
def label_text(meta: FieldMeta) -> str: ...
class FieldEditor(Vertical):
    class Edited(Message):                       # posted when the user really changes the value
        def __init__(self, editor: FieldEditor) -> None   # .editor
    def __init__(self, meta: FieldMeta, value: Any = None, *, id: str | None = None) -> None: ...
    # attributes: meta, initial
    input_widget -> Widget      # property: the Input, Select or Switch (id "input")
    value -> Any                # property: parsed current value; None when empty or invalid
    error -> str | None         # property: the message shown under the field
    changed -> bool             # property
    def validate(self) -> bool: ...
    def set_error(self, message: str | None) -> None: ...
```

Rules for `parse_value(kind, text)` (strip the text first; empty text is `ParseResult(None)` for every kind, never an error):
- `int`: `int(text)`; error `"Enter a whole number"`.
- `decimal`, `quantity`: `float(text)`, rejecting `nan` and `inf`; error `"Enter a number"`.
- `date`: `date.fromisoformat(text).isoformat()`; error `"Use YYYY-MM-DD"`.
- `datetime`: `datetime.fromisoformat(text).isoformat()`; error `"Use YYYY-MM-DDTHH:MM"`.
- `bool`: `true`/`yes` is `True`, `false`/`no` is `False` (any case); anything else error `"Enter yes or no"`.
- `json`: `json.loads(text)`; on `json.JSONDecodeError` the error is `f"Invalid JSON: {exc.msg}"`.
- `string`, `text`, `ref`, `enum`: the stripped text.
An invalid result has `value=None`.

`format_initial(value)`: `None` is `""`; `True`/`False` are `"yes"`/`"no"`; dict or list is compact sorted JSON (`json.dumps(value, sort_keys=True, separators=(",", ":"))`); anything else `str(value)`.

`label_text(meta)`: the label; then `f" ({unit_label(meta.unit)})"` if `meta.unit`; then a space and `●` (required), `○` (advisory) or `■` (locked) if
`meta.enforcement` is set; then `" @" + "/".join(required_in_states)` if there are any. Example: `size_in (in) ● @Design/Installed`.

`FieldEditor`:
- `compose` yields, in order: a `Static` (class `field-label`, `markup=False`) with `label_text(meta)`; the input widget with id `input`;
  a `Static` (class `field-error`, `markup=False`, empty).
  Input widget by kind: `bool` is a `Switch(bool(initial))`; `enum` is a `Select[str]` whose options are `(label + (f" → {crosswalk}" if crosswalk), code)`
  for each of `meta.enum_values`, with value `initial` when it is one of the codes, else `Select.NULL`; every other kind is an `Input` starting at
  `format_initial(initial)` with `placeholder=PLACEHOLDERS.get(kind, "")`. Pass `disabled=meta.readonly` to the input widget.
- `PLACEHOLDERS = {"int": "whole number", "decimal": "number", "quantity": "number", "date": "YYYY-MM-DD", "datetime": "YYYY-MM-DDTHH:MM", "json": "JSON value"}`.
- `value`: `Switch.value`; for a `Select` `None` when blank else its value; for an `Input` `parse_value(kind, input.value).value`.
- `changed`: `True` when an `Input` holds invalid text; else `value != initial`, except that a switch that is `False` with `initial is None` is not a change.
- `validate()`: for an `Input` run `parse_value`, call `set_error(result.error)`; other widgets have no error. Return `True` when there is no error.
- `set_error(message)`: remember it (`error` returns it) and update the error `Static` (empty string for `None`).
- Edits: handle `Input.Changed`, `Select.Changed`, `Switch.Changed` (call `event.stop()`), compare the widget's raw value with the last raw value seen
  (initially what the widget was built with: the `format_initial` text, the switch bool, or the select initial/`Select.NULL`); if equal do nothing (this ignores the mount-time echo);
  otherwise remember it, call `validate()`, and post `FieldEditor.Edited(self)`.
- `DEFAULT_CSS`: `FieldEditor { height: auto; margin-bottom: 1; }` and `FieldEditor > .field-error { color: $error; height: auto; }`.

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/text.py`
- `packages/tl-tui/tests/fakes.py` (read only; `valve_form_metadata`)
- `packages/tl-tui/tests/helpers.py`
- `docs/tickets/P0-I2/provided/test_form_fields.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/form_fields.py` (create)
- `packages/tl-tui/tests/test_form_fields.py` (create by copying the provided file; do not edit it)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_form_fields.py.txt packages/tl-tui/tests/test_form_fields.py`
2. Create `form_fields.py` as specified.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_form_fields.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass.

## Tests to add
None beyond the provided file. It covers the parse table, `format_initial`, `label_text`, inline validation and change tracking for a
decimal field, clearing, server-side errors, the switch, the select (including crosswalk labels and an unknown initial code), read-only fields, and literal labels.

## Report requirements
Standard report. State that the provided test file is byte-identical to the `.txt`. Do not commit the report file; return it as your final message.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing a file outside *Allowed paths*.

## Blocked

## Decision
