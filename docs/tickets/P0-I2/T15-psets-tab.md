# P0-I2-T15 — Psets tab: layer-grouped rendering with enforcement markers

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T14 (merged on `p0/i2b`); form metadata comes from the fake until workstream A merges
Branch: `p0/i2b-t15-psets-tab`

## Goal
The Psets tab of the record view shows every pset group of the record's type, each property with its value, unit, layer,
enforcement rule, and a conformance mark, plus a legend and the effective-schema hash. It reads only
`ClientInterface.form_metadata` and `ClientInterface.conformance`. `PsetsTab` exists as a stub with its final constructor
and `show_record`; this ticket replaces its content.

## Brief references (pasted)
Sketch 2 (§10.6), the tab body:
```text
│ Property                    Value                    Layer       Rule                 Source     │
│ ▾ valve_data   co:acme/engineering 3.2.0 · required · conformance 5/5 ✓                          │
│   size_in                   6.0 in                   standard    ● req@Design   ✓     ISD rC     │
│   fail_action               Fail closed              standard    ■ locked       ✓     ISD rC     │
│   seat_leakage              —                        standard    ○ advisory     !                │
│   x.fat_witness_by          @party:client-acme       P123 x.     optional                        │
│ ● required  ○ advisory  ■ locked  x. project custom section  ! conformance warning               │
│ Waiver: none   Conformance mode: strict with waivers   Effective schema #a91f…3c                 │
```
> Standard, project-custom (`x.`), project pset, enrichment, and source layers are visible at once, with enforcement markers. (§10.6)
> Enforcement: `advisory` violations are warnings only; `required` violations block the write or transition where the binding says so; `locked` is as required and projects cannot extend or tighten it. (§6.3)
> Meaning never rides on colour alone: pair status with a symbol (§10.3).

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns, docstrings and comments included. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- `Static` parses `[...]` as markup: use `markup=False` (the stub does).
- Do not name an attribute after a Textual `Widget` attribute (`visible`, `size`, `region`, `id`...).
- A screen reads through `self.client` only. Catch `CLIENT_ERRORS`, post `StatusMessage(describe_error(exc), "error")`.
  `NotImplementedError` (pset services not installed yet) is shown as text, not posted.
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text`.
- Shared display helpers live in `tl_tui/text.py`: `format_value`, `conformance_mark`, `short_hash`, `unit_label`, `EMPTY`.
  Pset values are read with `tl_tui.paths.pset_value(record["psets"], field.path)` (it accepts nested and flat stores).

## Interfaces (verbatim from repo at the branch point, plus the new functions)
```python
# packages/tl-schema/src/tl_schema/forms.py (existing, frozen contract)
class FieldMeta(BaseModel):
    path: str            # "psets.valve_data.size_in" | "psets.valve_data.x.fat_witness_by" | "psets.prj.shutdown_tie_in.window"
    label: str; description: str; kind: FieldKind
    unit: str | None = None; enum_values: list[EnumValue] | None = None
    required_in_states: list[str] = []; enforcement: Enforcement | None = None   # "advisory" | "required" | "locked"
    layer: Layer; readonly: bool = False; group: str; order: int
class PsetGroupMeta(BaseModel):
    name: str; label: str; package: str; version: str; enforcement: Enforcement | None; layer: Layer; fields: list[FieldMeta]
class FormMetadata(BaseModel):
    record_type: str; effective_schema_hash: str; core_fields: list[FieldMeta]; psets: list[PsetGroupMeta]
class ConformanceIssue(BaseModel):
    path: str; level: Literal["warning", "nonconformant"]; rule: str; message: str
class ConformanceReport(BaseModel):
    status: ConformanceLevel; issues: list[ConformanceIssue]; effective_schema_hash: str

# packages/tl-tui/src/tl_tui/client.py (existing)
def form_metadata(self, scope: str, record_type: str) -> FormMetadata: ...
def conformance(self, record_id: str) -> ConformanceReport: ...

# packages/tl-tui/src/tl_tui/widgets/psets_tab.py  (stub today; keep this constructor and show_record)
class PsetsTab(VerticalScroll, can_focus=True):
    def __init__(self, client: ClientInterface, scope: str, *, id: str | None = None) -> None: ...
    # attributes: client, scope, record (dict | None), text (str; the last rendered text)
    def show_record(self, record: dict[str, Any]) -> None: ...
# NEW in psets_tab.py (module-level)
HEADER: str; LEGEND: str
def rule_text(field: FieldMeta) -> str: ...
def value_text(field: FieldMeta, psets: dict[str, Any]) -> str: ...
def psets_text(meta: FormMetadata, record: dict[str, Any], report: ConformanceReport) -> str: ...

# packages/tl-tui/src/tl_tui/text.py (existing)
EMPTY = "—"
def format_value(value: Any) -> str; def conformance_mark(value: str | None) -> str
def short_hash(value: str | None) -> str; def unit_label(code: str | None) -> str    # "[in_i]" -> "in"
# packages/tl-tui/src/tl_tui/paths.py (existing)
def pset_value(psets: dict[str, Any], path: str) -> Any
```

Format rules (lines joined with `"\n"`; the provided test compares exact lines):
- `HEADER = f"{'Property':<28}{'Value':<24}{'Layer':<12}Rule"`.
- `LEGEND = "● required  ○ advisory  ■ locked  ! warning  ✗ nonconformant  ✓ ok  x. project custom section"`.
- `rule_text(field)`: start from `"■ locked"` (enforcement `locked`), `"● required"` (`required`), `"○ advisory"` (`advisory`), else `"optional"`;
  if `required_in_states` is non-empty append `"@"` + the states joined by `"/"`; if `readonly` append `" (read-only)"`.
- `value_text(field, psets)`: `pset_value(psets, field.path)`; `None` or `""` gives `EMPTY`; otherwise `format_value(value)`, then a space and
  `unit_label(field.unit)` when the unit is non-empty (so `6.0` with unit `[in_i]` is `6 in`; an unknown unit shows its code).
- `psets_text` output is, in order:
  1. `HEADER`
  2. for each group in `meta.psets`: the line `f"▾ {group.name}   {group.package} {group.version} · {group.enforcement or 'optional'}"` (three spaces after the name),
     then for each field of the group in listed order the line
     `f"  {field.label:<26}{value:<24}{field.layer:<12}{rule}"` with `  {mark}` appended when `mark` is not empty, where `value = value_text(...)`, `rule = rule_text(...)`
     and `mark` is `"!"` if the report has a `warning` issue whose `path` equals `field.path`, `"✗"` if it has a `nonconformant` one, else `"✓"` when `value` is not `EMPTY`, else empty.
  3. an empty line
  4. `LEGEND`
  5. `f"Conformance: {conformance_mark(report.status)}   Effective schema {short_hash(report.effective_schema_hash)}"` (three spaces before `Effective`).

`PsetsTab` behaviour:
- Compose a `Static` with id `psets-body` and `markup=False`. Give the widget CSS so wide lines scroll instead of wrapping:
  `PsetsTab { overflow-x: auto; padding: 0 1; }` and `PsetsTab > #psets-body { width: auto; }` (in `DEFAULT_CSS`).
- Define `KEY_HINTS: ClassVar[str] = "↑↓ scroll  Esc back"`.
- `show_record(record)`: store `record`; call `client.form_metadata(self.scope, record["type"])` and `client.conformance(record["id"])`.
  On success `text = psets_text(...)`. On `NotImplementedError`: `text = "Psets unavailable: the pset services are not installed yet"`.
  On `CLIENT_ERRORS`: `text = f"Psets unavailable: {describe_error(exc)}"` and post `StatusMessage(describe_error(exc), "error")`.
  Then update the `Static` with `text` and keep `self.text = text`. Initial `text` is `""`.

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/psets_tab.py`
- `packages/tl-tui/src/tl_tui/text.py`
- `packages/tl-tui/tests/fakes.py` (read only; `valve_form_metadata`, `FakeClient`)
- `docs/tickets/P0-I2/provided/test_psets_tab.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/psets_tab.py` (edit: replace the stub content)
- `packages/tl-tui/tests/test_psets_tab.py` (create by copying the provided file; do not edit it)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_psets_tab.py.txt packages/tl-tui/tests/test_psets_tab.py`
2. Implement the three functions and `PsetsTab` as specified.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_psets_tab.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass (the record view tests must still pass unchanged).

## Tests to add
None beyond the provided file. It covers the exact layout for a conformant record, issue marks, `rule_text` and `value_text`
variants, the widget, both unavailable paths, and the record view refreshing the tab after a `RecordChanged`.

## Report requirements
Standard report. State that the provided test file is byte-identical to the `.txt`. Do not commit the report file; return it as your final message.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without changing a file outside *Allowed paths*.

## Blocked

## Decision
