# P0-I2-T04 — JSON Schema per record type and psets validator

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I2-T03 (merged into the base of this branch)
Branch: `p0/i2a-t04-json-schema-validator`

## Goal
`tl_schema.validation` builds a JSON Schema (draft 2020-12) for the `psets` object of a record type from an `EffectiveSchema`, caches it by
the schema hash, and validates a `psets` mapping against it, returning structured issues. The module exists as a stub; after this ticket
the stub bodies work and a provided test file passes.

## Brief references (pasted)
> **27.3** Compilation uses linkml-runtime (SchemaView) to merge packages, then generates JSON Schema for fast runtime validation plus custom validators for cross-record rules. ... compiled artefacts (cached by hash): JSON Schema per record type (runtime validation).
> **6.3 Values** are stored as events (`Pset.ValuesSet`) recording the effective schema hash they were validated against. A value on a record is addressed by layer-aware paths: `psets.valve_data.size_in` (company standard), `psets.valve_data.x.fat_witness_by` (project custom section of the same pset), `psets.prj.shutdown_tie_in.window` (project custom pset), `psets.enrich.ai_classifier.valve_type` (enrichment), `psets.src.ifc.Pset_ValveTypeCommon.Size` (source).

Design note: this JSON Schema checks structure and value constraints only (type, range, pattern, enum, unknown keys). Required-in-state, enforcement levels and waivers are not JSON Schema; a separate conformance evaluator (supervisor-built) uses these issues.

### Shape of the schema (the specification; the provided test checks it)
`record_json_schema(schema, record_type)` returns this dict (a fresh build the first time, the same cached object afterwards):
```
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:tl:effective:<schema.hash>:<record_type>",
  "title": "<record_type> psets",
  "type": "object",
  "properties": { <pset schemas> },
  "additionalProperties": true          # enrichment ("enrich") and source ("src") psets and other root keys are allowed
}
```
- Psets are `schema.for_record_type(record_type)`. A pset with `layer == "standard"` is a property of the root named `pset.name`.
- Psets with `layer == "project"` (names like `prj.shutdown_tie_in`) go under one root property `"prj"`:
  `{"type": "object", "properties": {<short name>: <pset schema>}, "additionalProperties": false}` where the short name is the part after `"prj."`. `"prj"` exists only if there is at least one project pset.
- Pset schema: `{"type": "object", "title": pset.label, "description": pset.description, "properties": {...}, "additionalProperties": false}`.
  Its properties are `pset.properties` (key = property name, declaration order), plus, only when `pset.custom` is non-empty, a property `"x"`:
  `{"type": "object", "properties": {<custom property name>: <property schema>}, "additionalProperties": false}`.
- Property schema: `{"title": prop.label, "description": prop.description}` plus, by `prop.kind`:
  | kind | added keys |
  |---|---|
  | `string`, `text`, `ref` | `"type": "string"`; `"pattern": prop.pattern` when set |
  | `int` | `"type": "integer"` |
  | `decimal`, `quantity` | `"type": "number"` |
  | `bool` | `"type": "boolean"` |
  | `date` | `"type": "string"`, `"pattern": DATE_PATTERN` |
  | `datetime` | `"type": "string"`, `"pattern": DATETIME_PATTERN` |
  | `enum` | `"type": "string"`, `"enum": [v.code for v in prop.enum_values]` |
  | `json` | nothing (any JSON value) |
  and for kinds `int`, `decimal`, `quantity`: `"minimum"` / `"maximum"` when `prop.minimum` / `prop.maximum` is not None; and `"x-unit": prop.unit` when the unit is set (any kind).
- `DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"`; `DATETIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?$"`. Define both as module constants.

### Validator
`validate_psets(schema, record_type, psets)` runs `jsonschema.Draft202012Validator` over `dict(psets)` and returns `ValueIssue`s:
- `path` is `"psets"` followed by `"." + part` for every element of the error's `absolute_path` (so a top-level pset error is `psets.valve_data`, a property error `psets.valve_data.size_in`, a custom one `psets.valve_data.x.fat_witness_by`).
- `keyword` is `str(error.validator)` (`type`, `minimum`, `maximum`, `pattern`, `enum`, `additionalProperties`); `message` is `error.message`.
- An `additionalProperties` error produces one issue per unknown key: the keys of `error.instance` that are not in `error.schema["properties"]`; `path` is the error path plus `.<key>`; `keyword` is `additionalProperties`; message `f"{key!r} is not defined in the effective schema"`.
- Return the issues de-duplicated and sorted by `(path, keyword)`.
- Cache the schema and the validator with the existing `EffectiveCache` (`from tl_schema.compose import EffectiveCache`): keep one module-level `_CACHE = EffectiveCache()` and call `_CACHE.get_or_build(schema, f"json:{record_type}", build)` and `_CACHE.get_or_build(schema, f"validator:{record_type}", lambda: Draft202012Validator(document))`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copied test.
- pyright is strict for `packages/tl-schema/src`. `jsonschema` is only partly typed: declare `validator: Any = ...` and `errors: list[Any] = list(validator.iter_errors(...))` so the checker accepts the calls. `ruff` enforces 100 columns including docstrings and comments.
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call. Ignore it. If imports fail in a fresh worktree run `uv sync --all-packages` once. Do not pipe `just check` into `tail` (it hides the exit code).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-schema/src/tl_schema/validation.py (stub; replace the two `raise NotImplementedError` bodies, add module constants and helpers)
@dataclass(frozen=True)
class ValueIssue:
    path: str
    # The JSON Schema keyword: type, minimum, maximum, pattern, enum, additionalProperties.
    keyword: str
    message: str

def record_json_schema(schema: EffectiveSchema, record_type: str) -> dict[str, Any]: ...
def validate_psets(schema: EffectiveSchema, record_type: str, psets: Mapping[str, Any]) -> list[ValueIssue]: ...
```
```python
# packages/tl-schema/src/tl_schema/effective.py (read-only; the parts you use)
class EffectiveProperty(BaseModel):
    name: str; layer: Literal["standard", "custom", "project"]; label: str; description: str
    kind: FieldKind   # "string" | "text" | "int" | "decimal" | "bool" | "date" | "datetime" | "enum" | "quantity" | "ref" | "json"
    unit: str | None; enum_values: list[EnumValue] | None   # EnumValue.code
    pattern: str | None; minimum: float | None; maximum: float | None
class EffectivePset(BaseModel):
    name: str; layer: Literal["standard", "project"]; label: str; description: str
    properties: dict[str, EffectiveProperty]; custom: dict[str, EffectiveProperty]
class EffectiveSchema(BaseModel):
    scope: str; hash: str; psets: dict[str, EffectivePset]
    def for_record_type(self, record_type: str) -> list[EffectivePset]: ...   # name order
# packages/tl-schema/src/tl_schema/compose.py
class EffectiveCache:
    def get_or_build(self, schema: EffectiveSchema, kind: str, build: Callable[[], T]) -> T: ...   # keyed by (schema.hash, kind)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-schema/src/tl_schema/validation.py`
- `packages/tl-schema/src/tl_schema/effective.py`
- `packages/tl-schema/tests/conftest.py`
- `docs/tickets/P0-I2/provided/test_validation.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-schema/src/tl_schema/validation.py` (edit: implement the stub)
- `packages/tl-schema/tests/test_validation.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_validation.py.txt packages/tl-schema/tests/test_validation.py`
2. Implement `_property_schema`, `_pset_schema`, `record_json_schema`, `validate_psets` as specified.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest packages/tl-schema/tests/test_validation.py -q
just check
just test
diff docs/tickets/P0-I2/provided/test_validation.py.txt packages/tl-schema/tests/test_validation.py
```
Expected: all tests pass (16 in the provided file), `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file. Do not add, change or skip tests in it.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands and the test count.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification above.
- Stop rather than change `effective.py`, `compose.py` or `conftest.py`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
