# P0-I2-T04b — Form metadata from the effective schema

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I2-T03 (merged into the base of this branch)
Branch: `p0/i2a-t04b-form-metadata`

## Goal
`tl_schema.formgen.form_metadata(schema, record_type)` turns an `EffectiveSchema` into the `FormMetadata` the TUI renders (the contract
models live in `tl_schema/forms.py`). The module is a stub; after this ticket it works and a provided test file passes.

## Brief references (pasted)
> **6.1** From the LinkML model the build generates ... TUI form/grid metadata (labels, help, ordering, widgets, lookups).
> **27.3** compiled artefacts (cached by hash) include form/grid metadata (TUI, PWA, web).
> **6.3 layers** (what `layer` means): `standard` = company standard pset property; `custom` = project custom-section property (addressed under `x.`); `project` = property of a project custom pset (`prj.<name>`); `core` = envelope field (not a pset).
> Enforcement: `advisory` (warning only), `required`, `locked`. A property with `required_in_states == ["*"]` is required in every state.

### Mapping (the specification; the provided test checks it)
`FormMetadata(record_type=record_type, effective_schema_hash=schema.hash, core_fields=<4 fields>, psets=<groups>)`.

Core fields, in this order, all with `layer="core"`, `group="details"`, `enforcement=None`, `unit=None`, `enum_values=None`, `order` = 0..3:
| order | path (= name) | label | description | kind | readonly | required_in_states |
|---|---|---|---|---|---|---|
| 0 | `title` | `Title` | `Short human-readable title.` | `string` | false | `["*"]` |
| 1 | `description` | `Description` | `Longer free-text description.` | `text` | false | `[]` |
| 2 | `key` | `Key` | `Human-readable number, unique within a scope.` | `string` | true | `[]` |
| 3 | `status` | `Status` | `Workflow state.` | `string` | true | `[]` |

Groups: one `PsetGroupMeta` per pset in `schema.for_record_type(record_type)`, sorted by `(pset.layer != "standard", pset.name)` (standard psets first, then project psets, each by name):
`name=pset.name, label=pset.label, package=pset.package, version=pset.version, enforcement=pset.enforcement, layer=pset.layer, fields=[...]`.

Fields of a group: one `FieldMeta` per `pset.all_properties()` (standard or project properties first, then custom-section properties), with
`path=f"psets.{pset.name}.{prop.relative_key()}"`, `label=prop.label`, `description=prop.description`, `kind=prop.kind`, `unit=prop.unit`,
`enum_values=` a list of `EnumValue(code, label, crosswalk)` copied from `prop.enum_values` (None when the property has none),
`required_in_states=list(prop.required_in_states)`, `enforcement=prop.enforcement`, `layer=prop.layer`, `readonly=False`, `group=pset.name`, `order=prop.order`.
A record type with no psets gives `psets == []` and still has the four core fields.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copied test.
- pyright is strict for `packages/tl-schema/src`. A `kind` value passed to `FieldMeta` must be typed `FieldKind` (import it from `tl_schema.forms`); build the four core fields with one small helper whose `kind` parameter is annotated `FieldKind`, not with a list of tuples (tuple elements widen to `str` and fail the check). `ruff` enforces 100 columns including docstrings and comments.
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call. Ignore it. If imports fail in a fresh worktree run `uv sync --all-packages` once. Do not pipe `just check` into `tail` (it hides the exit code).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/formgen.py (stub; replace the body, add helpers)
def form_metadata(schema: EffectiveSchema, record_type: str) -> FormMetadata: ...
```
```python
# packages/tl-schema/src/tl_schema/forms.py (read-only contract; do not change)
FieldKind = Literal["string", "text", "int", "decimal", "bool", "date", "datetime", "enum", "quantity", "ref", "json"]
class EnumValue(BaseModel): code: str; label: str; crosswalk: str | None = None
class FieldMeta(BaseModel):
    path: str; label: str; description: str; kind: FieldKind; unit: str | None = None
    enum_values: list[EnumValue] | None = None; required_in_states: list[str] = []
    enforcement: Enforcement | None = None; layer: Layer; readonly: bool = False; group: str; order: int
class PsetGroupMeta(BaseModel):
    name: str; label: str; package: str; version: str; enforcement: Enforcement | None; layer: Layer; fields: list[FieldMeta]
class FormMetadata(BaseModel):
    record_type: str; effective_schema_hash: str; core_fields: list[FieldMeta]; psets: list[PsetGroupMeta]
```
```python
# packages/tl-schema/src/tl_schema/effective.py (read-only; the parts you use)
ALWAYS = "*"
class EffectiveProperty(BaseModel):
    name: str; layer: Literal["standard", "custom", "project"]; label: str; description: str; kind: FieldKind
    unit: str | None; enum_values: list[EnumValue] | None; required_in_states: list[str]; enforcement: Enforcement; order: int
    def relative_key(self) -> str: ...      # "size_in" or "x.fat_witness_by"
class EffectivePset(BaseModel):
    name: str; layer: Literal["standard", "project"]; label: str; package: str; version: str; enforcement: Enforcement
    def all_properties(self) -> list[EffectiveProperty]: ...    # standard/project properties, then custom ones
class EffectiveSchema(BaseModel):
    hash: str
    def for_record_type(self, record_type: str) -> list[EffectivePset]: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/formgen.py`
- `packages/tl-schema/src/tl_schema/forms.py`
- `packages/tl-schema/src/tl_schema/effective.py`
- `packages/tl-schema/tests/conftest.py`
- `docs/tickets/P0-I2/provided/test_formgen.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-schema/src/tl_schema/formgen.py` (edit: implement the stub)
- `packages/tl-schema/tests/test_formgen.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_formgen.py.txt packages/tl-schema/tests/test_formgen.py`
2. Implement the mapping above.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest packages/tl-schema/tests/test_formgen.py -q
just check
just test
diff docs/tickets/P0-I2/provided/test_formgen.py.txt packages/tl-schema/tests/test_formgen.py
```
Expected: all tests pass (10 in the provided file), `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands and the test count.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the mapping above.
- Stop rather than change `forms.py`, `effective.py` or `conftest.py`: `forms.py` is a contract shared with another workstream.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
