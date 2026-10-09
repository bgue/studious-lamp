# P0-I2-T06 — `SetPsetValues` handler and `Pset.ValuesSet`

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I2-T04, P0-I2-T05, P0-I2-T07 (all merged into the base of this branch)
Branch: `p0/i2a-t06-set-pset-values`

## Goal
`handle_set_pset_values(uow, cmd)` in `tl_core/services/psets.py` validates a pset write against the scope's effective schema, applies the
layer rules, and appends one `Pset.ValuesSet` event whose payload carries the effective schema hash, the resulting conformance status and
the units. The command model, the services `form_metadata` and `conformance`, the error classes, the projector and the schema provider
already exist. The handler is a stub; after this ticket it works and a provided test file passes (28 tests).

## Brief references (pasted)
> **6.3 Layers.** 2 Company standard psets (`valve_data.size_in`); 3 Project extensions of standard psets, in the pset's custom section (`valve_data.x.fat_witness_by`); 4 Project custom psets (`prj.shutdown_tie_in.window`); 5 Enrichment psets (`enrich:<app>/`, machine-written, read-only for humans); 6 Source psets (`src:<system>/`, preserved verbatim).
> **Company enforcement.** `advisory`: violations are warnings only. `required`: violations block the write or transition where the binding says so. `locked`: as `required`, and projects cannot extend or tighten it: no added values, no custom section.
> **Projects cannot** write into enrichment or source layers; touch `locked` psets beyond filling values.
> **Values** are stored as events (`Pset.ValuesSet`) recording the effective schema hash they were validated against, and projected into current-state tables.

Design decisions already taken (do not reopen): a write is blocked only for *structural* errors (wrong type, unknown key, null, wrong layer). Range, pattern and value-list violations are accepted and show up as conformance (`warning` / `nonconformant`) because enforcement decides their effect, not the write. Null values are not supported in this increment (there is no "clear a value" command yet).

### Algorithm of `handle_set_pset_values` (the specification; the provided test checks it)
Use the names already imported or defined in `psets.py` (`load_row`, `BLOCKING_KEYWORDS`, `READ_ONLY_ROOTS`, `get_provider`, `evaluate`, `CommandResult`) and add the imports you need (listed under *Interfaces*).
1. `row = load_row(uow, cmd.stream_id, cmd.scope)` (raises `RecordNotFoundError` for an unknown record or one in another scope). If `row.voided` raise `RecordVoidedError(f"record {cmd.stream_id!r} is voided and cannot be updated")`.
2. `schema = get_provider().effective(cmd.scope)`.
3. Layer and key rules, in this order, each raising and appending nothing:
   - `root = cmd.pset.split(".")[0]`; if `root in READ_ONLY_ROOTS` raise `LayerError` (enrichment and source layers are not writable).
   - `pset = schema.find_pset(cmd.pset)`; `None` raises `UnknownPsetError`. `row.type not in pset.applies_to` raises `UnknownPsetError`.
   - Empty `cmd.values` raises `NoChangesError`.
   - `cmd.layer == "project"` and `pset.layer != "project"` raises `LayerError`. `cmd.layer in ("standard", "custom")` and `pset.layer != "standard"` raises `LayerError`.
   - For each key of `cmd.values` (iteration order): a key is *custom* when it starts with `"x."`.
     - layer `custom`: if `not pset.custom_allowed` raise `LayerError`; if the key is not custom raise `LayerError`.
     - layers `standard` and `project`: a custom key, or the key `"x"` itself, raises `LayerError`.
     - then `pset.find(key) is None` raises `PsetValidationError(f"{cmd.pset}.{key} is not defined in the effective schema", [f"psets.{cmd.pset}.{key}: not defined"])`.
4. Null values: if any value is `None` raise `PsetValidationError("null values are not supported", [f"{cmd.pset}.{k}: null" for k in sorted null keys])`.
5. Structural validation: build `incoming = {}` and for each `key, value` call `set_nested(incoming, [*cmd.pset.split("."), *key.split(".")], value)` (from `tl_core.projection.pset`). `issues = validate_psets(schema, row.type, incoming)` (from `tl_schema.validation`); keep the ones whose `keyword in BLOCKING_KEYWORDS`. If any remain raise `PsetValidationError(f"values for {cmd.pset} are invalid", [f"{i.path}: {i.message}" for i in kept])` (the validator already sorts them).
6. `current = json.loads(row.psets_json)`; `merged = json.loads(json.dumps(current))` (a deep copy); apply the same `set_nested` calls to `merged`. If `merged == current` raise `NoChangesError(f"no value of {cmd.pset} differs from the record")`.
7. `ensure_promoted_columns(uow.conn(), schema)` (from `tl_core.projection.promoted`), then `report = evaluate(schema, row.type, merged, state=row.status, on=utcnow().date())` (`utcnow` from `tl_core.util`).
8. `units = {key: prop.unit for key in cmd.values if (prop := pset.find(key)) is not None and prop.unit is not None}`.
9. `result = uow.append(stream_id=cmd.stream_id, stream_type=row.type, scope=cmd.scope, expected_version=cmd.expected_version, events=[NewEvent(event_type="Pset.ValuesSet", payload={...})], actor=cmd.actor, source=cmd.source, correlation_id=cmd.correlation_id or new_ulid(), causation_id=cmd.causation_id)`.
   Payload keys, exactly: `pset` (`cmd.pset`), `layer` (`cmd.layer`), `values` (`cmd.values`), `effective_schema_hash` (`schema.hash`), `conformance` (`report.status`), `units` (the dict from step 8).
10. Return `CommandResult(stream_id=cmd.stream_id, key=row.key, version=result.new_version, events=result.events)`.
A wrong `expected_version` makes `uow.append` raise `ConcurrencyError`; let it propagate. The handler never commits.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copied test.
- pyright is strict for `packages/tl-core/src`; `ruff` enforces 100 columns including docstrings and comments. Annotate `json.loads` results (`current: dict[str, Any] = ...`). `load_row` returns `Any` on purpose (a SQLAlchemy row).
- `uow.append` runs the registered projectors in the same transaction, so after the call the projections are updated; the handler does not write projection rows itself.
- Seed events in tests must carry every required payload key. `uv` prints "UV_NATIVE_TLS is deprecated" on every call; ignore it. If imports fail in a fresh worktree run `uv sync --all-packages`. Do not pipe `just check` into `tail`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/services/psets.py (existing; implement the stub body, keep everything else)
class SetPsetValues(Command):
    stream_id: str
    expected_version: int
    pset: str  # "valve_data" | "prj.shutdown_tie_in"
    layer: Literal["standard", "custom", "project"]
    values: dict[str, Any]  # keys relative to the pset; custom-section keys are prefixed "x."

BLOCKING_KEYWORDS = frozenset({"type", "additionalProperties"})
READ_ONLY_ROOTS = frozenset({"enrich", "src"})
def load_row(uow: UnitOfWork, stream_id: str, scope: str) -> Any: ...   # row with id, key, type, scope, status, psets_json, voided, version
def handle_set_pset_values(uow: UnitOfWork, cmd: SetPsetValues) -> CommandResult: ...   # the stub
```
```python
# imports to add (all exist)
from tl_core.ledger import NewEvent
from tl_core.projection.promoted import ensure_promoted_columns          # (conn, schema) -> list[str]
from tl_core.projection.pset import set_nested                           # (root: dict, segments: list[str], value) -> None
from tl_core.services.errors import LayerError, NoChangesError, PsetValidationError, RecordVoidedError, UnknownPsetError
from tl_core.util import new_ulid, utcnow
from tl_schema.validation import validate_psets                           # (schema, record_type, psets) -> list[ValueIssue(path, keyword, message)]
# already imported in the file: get_provider, evaluate, CommandResult, UnitOfWork, RecordNotFoundError, json
# tl_core.services.errors: PsetValidationError(message, issues: list[str]) has .issues
# EffectiveSchema.find_pset(name) -> EffectivePset | None; EffectivePset: layer ("standard"|"project"), applies_to, custom_allowed,
#   find(relative_key) -> EffectiveProperty | None (key "size_in" or "x.fat_witness_by"); EffectiveProperty.unit: str | None
# evaluate(schema, record_type, psets, *, state, on: date) -> ConformanceReport; report.status in ok|warning|nonconformant|waived
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/psets.py`
- `packages/tl-core/src/tl_core/services/errors.py`
- `packages/tl-core/src/tl_core/services/records.py` (the shape of an existing handler)
- `docs/tickets/P0-I2/provided/test_pset_commands.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/services/psets.py` (edit: implement `handle_set_pset_values` and its private helpers, add imports)
- `tests/services/test_pset_commands.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_pset_commands.py.txt tests/services/test_pset_commands.py`
2. Implement the algorithm. A private helper for step 3 keeps the handler readable.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest tests/services/test_pset_commands.py -q
just check
just test
diff docs/tickets/P0-I2/provided/test_pset_commands.py.txt tests/services/test_pset_commands.py
```
Expected: 28 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands and the test count.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the algorithm.
- Stop rather than change `forms.py`, the `SetPsetValues` fields, a projector, or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
