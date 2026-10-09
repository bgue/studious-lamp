# P0-I4-T22 — File slot declarations: parse and load `tl:file_slots`

Status: merged
Tier: haiku
Labels: core
Depends on: — (models, registry, fixture and the provided test are on the base branch)
Branch: `p0/i4b-t22-file-slot-declarations`

## Goal
`tl_core.files.slots` reads `tl:file_slots` declarations from LinkML YAML files, so a record type can say which attachment slots it has
(brief 20.1). The models (`FileSlot`, `FileSlotRegistry`, `FileSlotError`), the sample declaration `schema/fixtures/files/core-record.yaml`
and all signatures exist; the three functions marked `raise NotImplementedError` are the work. A provided test file (30 tests) must pass.
The upload service (supervisor) checks every upload against these slots.

## Brief references (pasted)
> **20.1** Each record type declares **file slots** in LinkML (and psets can add slots): `name`, `label`, `cardinality` (one / many), `accepted_types` (PDF, image/*, IFC, XLSX, CSV, EML/MSG), `max_size`, `required_in_states` (required before `Receipt: Accepted`), `capture_hint` (`camera`, `scan`, `file`), `metadata_pset`, `processing`, `retention_class`, `confidentiality`. Generic, unslotted attachments remain possible on every record.

### Specification (the provided test checks it)
This mirrors `tl_core.links.expected` (expected links), which you may read for the pattern: `packages/tl-core/src/tl_core/links/expected.py`.
- Declaration format: in a LinkML YAML document, `classes.<Class>.annotations["tl:file_slots"]` is a list of mappings (a single mapping is also accepted) with the keys of `FileSlot`. The record type of the class is `f"{module}.{Class}"`, where `module` is the schema-level `annotations["tl:module"]`.
- `parse_file_slots(text, source=)`: `yaml.safe_load`; `yaml.YAMLError` raises `FileSlotError(f"{source}: invalid YAML: {exc}")`; an empty document (`None`) gives an empty registry; a non-mapping document raises `FileSlotError(f"{source}: a schema file must be a YAML mapping")`. A document without `classes` (or with a non-mapping `classes`) gives an empty registry. A class that is not a mapping, or whose `annotations` has no `tl:file_slots`, contributes nothing. If a class has the annotation but the schema has no `tl:module` (missing or not a non-empty string), raise `FileSlotError(f"{source}: class {class_name} has tl:file_slots but the schema has no tl:module")`. A value that is neither a mapping nor a list raises `FileSlotError(f"{source}: {class_name}.tl:file_slots must be a mapping or a list of mappings")`. An invalid entry (`FileSlot.model_validate` raises `ValidationError`, which also covers unknown keys because the model forbids extras) raises `FileSlotError(f"{source}: {class_name}.tl:file_slots[{index}]: {problems}")` where `problems` is the pydantic errors joined by `"; "`, each `f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"`. Add each valid slot with `registry.add(f"{module}.{class_name}", slot)`; `add` raises `FileSlotError` for a name declared twice, and you re-raise it as `FileSlotError(f"{source}: {exc}")`.
- `load_file_slots(path)`: a directory gives every `*.yaml` file directly inside (not `.yml`, not recursive), sorted by name, merged in that order; a file gives just that file; a path that does not exist gives an empty registry. A read error (`OSError`, `UnicodeDecodeError`) raises `FileSlotError(f"{file.name}: cannot read file: {exc}")`. Parse errors use `source=file.name`. Merging with `registry.merge(parsed)` can raise `FileSlotError` for a slot declared in two files: re-raise as `FileSlotError(f"{file.name}: {exc}")`.
- `default_file_slots()`: `load_file_slots(default_schema_dir() / "files")` with `from tl_schema.registry import default_schema_dir` (it honours `TL_SCHEMA_DIR`).

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-core/src`: annotate `yaml.safe_load` results as `Any` and narrow with `isinstance` plus `typing.cast`. ruff limits lines to 100 columns (docstrings too); run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I4-T22)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/files/slots.py (existing stub; models and registry are final, keep every name and signature)
class FileSlot(BaseModel):   # frozen, extra="forbid"
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$"); label: str | None = None
    cardinality: Literal["one", "many"] = "many"; accepted_types: list[str] = []
    max_size: int | None = Field(default=None, ge=1); required_in_states: list[str] = []
    capture_hint: Literal["camera", "scan", "file"] = "file"; metadata_pset: str | None = None
    processing: list[str] = []; retention_class: str | None = None; confidentiality: str | None = None
    @property
    def display(self) -> str: ...                 # implemented
    def accepts(self, content_type: str) -> bool  # implemented
class FileSlotError(ValueError): ...
class FileSlotRegistry:                           # implemented
    def add(self, record_type: str, slot: FileSlot) -> None        # raises FileSlotError on a duplicate name
    def for_type(self, record_type: str) -> list[FileSlot]; def get(self, record_type: str, name: str) -> FileSlot | None
    def record_types(self) -> list[str]; def merge(self, other: FileSlotRegistry) -> None
def parse_file_slots(text: str, *, source: str = "<string>") -> FileSlotRegistry
def load_file_slots(path: Path) -> FileSlotRegistry
def default_file_slots() -> FileSlotRegistry
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/files/slots.py`
- `packages/tl-core/src/tl_core/links/expected.py` (the pattern to mirror)
- `schema/fixtures/files/core-record.yaml`
- `docs/tickets/P0-I4/provided/test_file_slots.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/files/slots.py` (edit)
- `packages/tl-core/tests/test_file_slots.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T22.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_file_slots.py.txt packages/tl-core/tests/test_file_slots.py`
2. Implement the three functions; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_file_slots.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_file_slots.py.txt packages/tl-core/tests/test_file_slots.py
```
Expected: 30 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file (the models and the registry are not yours to change; `schema/**` is read-only).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
