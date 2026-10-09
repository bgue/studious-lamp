# P0-I3-T04 — Expected links: declarations and the missing list

Status: ready
Tier: haiku
Labels: core
Depends on: — (models, stub, fixture and `cur_links` DDL are on the base branch; the test inserts link rows directly)
Branch: `p0/i3-t04-expected-links`

## Goal
`tl_core.links.expected` reads `tl:expects_link` declarations from LinkML YAML files, and answers "which expected links does this record
still lack?" by counting rows of `cur_links`. The models (`ExpectedLink`, `MissingLink`), the sample declaration
`schema/fixtures/links/core-record.yaml` and all signatures exist; every function body marked `raise NotImplementedError` is the work. A
provided test file (31 tests) must pass. The workflow engine (supervisor) uses `unmet_expectations` and `missing_expected_links` as workflow
guards.

## Brief references (pasted)
> **7.1** **Expected links** are declared in LinkML (`tl:expects_link`), e.g. a weld needs a WPS by `Welded`, an IWP needs a permit-to-work by `Issued`. Missing expected links show on the record and in data health reports, and can act as workflow guards.
> **7.4** Links tab: "! expected but missing: permit-to-work (rule: IWP@Issued)".

### Specification (the provided test checks it)
- Declaration format: in a LinkML YAML document, `classes.<Class>.annotations["tl:expects_link"]` is a list of mappings (a single mapping is also accepted) with the keys of `ExpectedLink`. The record type of the class is `f"{module}.{Class}"`, where `module` is the schema-level `annotations["tl:module"]`.
- `ExpectedLinkRegistry`: `add` appends to the list of a type; `for_type` returns a **new** list (empty for unknown types); `record_types()` is the sorted types that have at least one expectation; `merge(other)` adds all of `other`'s expectations after this registry's.
- `parse_expected_links(text, source=)`: `yaml.safe_load`; `yaml.YAMLError` raises `ExpectedLinkError(f"{source}: invalid YAML: {exc}")`; a non-mapping document raises `ExpectedLinkError(f"{source}: a schema file must be a YAML mapping")`. A document without `classes` (or with a non-mapping `classes`) gives an empty registry. A class whose `annotations` has no `tl:expects_link` contributes nothing. If a class has the annotation but the schema has no `tl:module`, raise `ExpectedLinkError(f"{source}: class {class_name} has tl:expects_link but the schema has no tl:module")`. An invalid entry raises `ExpectedLinkError(f"{source}: {class_name}.tl:expects_link[{index}]: {problems}")` where `problems` is the pydantic errors joined by `"; "`, each `f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"`.
- `load_expected_links(path)`: a directory gives every `*.yaml` directly inside, sorted by name, merged in that order; a file gives just that file; a path that does not exist gives an empty registry. Read errors raise `ExpectedLinkError(f"{file.name}: cannot read file: {exc}")`; parse errors use `source=file.name`.
- `default_expected_links()`: `load_expected_links(default_schema_dir() / "links")` with `from tl_schema.registry import default_schema_dir` (it honours `TL_SCHEMA_DIR`).
- `unmet_expectations(uow, record_id, expectations)`: for each expectation count matching links and keep those with `found < min_count` as `MissingLink(expectation=..., found=found, needed=min_count)`, in the given order. A link matches when `cur_links.status = 'active'`, `relation` equals the expectation's, and the record at the *other* end is not voided and (when `target_type` is set) has `type = target_type`. Direction `out`: the record is `from_id` (other end `to_id`); `in`: the record is `to_id` (other end `from_id`); `either`: add both counts. Use these two statements, appending `" AND r.type = :target_type"` when needed, with bound parameters `id`, `relation`, `no` (= `False`) and `target_type`:
  ```sql
  SELECT COUNT(*) FROM cur_links l JOIN cur_core_record r ON r.id = l.to_id
   WHERE l.from_id = :id AND l.relation = :relation AND l.status = 'active' AND r.voided = :no
  SELECT COUNT(*) FROM cur_links l JOIN cur_core_record r ON r.id = l.from_id
   WHERE l.to_id = :id AND l.relation = :relation AND l.status = 'active' AND r.voided = :no
  ```
  Run them with `uow.conn().execute(text(sql), params).scalar_one()`.
- `missing_expected_links(uow, record_id, *, registry=None, by_state=None)`: `SELECT type FROM cur_core_record WHERE id = :id`; no row raises `RecordNotFoundError(f"no record {record_id!r}")` (from `tl_core.services.errors`). `registry` defaults to `default_expected_links()`. `expectations = registry.for_type(type)`; with `by_state` keep only those whose `by_state` equals it. Return `unmet_expectations(uow, record_id, expectations)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No SQLite- or Postgres-specific SQL; bound parameters only.
- pyright is `strict` for `packages/tl-core/src`: annotate `yaml.safe_load` results as `Any` and narrow with `isinstance` plus `typing.cast`. ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I3-T04)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/links/expected.py (existing stub; models are final, keep every name and signature)
class ExpectedLink(BaseModel):   # frozen, extra="forbid"
    relation: str; direction: Literal["out", "in", "either"] = "out"; target_type: str | None = None
    by_state: str | None = None; label: str | None = None; min_count: int = Field(default=1, ge=1)
    @property
    def display(self) -> str: ...      # implemented
class MissingLink(BaseModel): expectation: ExpectedLink; found: int; needed: int
class ExpectedLinkError(ValueError): ...
class ExpectedLinkRegistry:
    def __init__(self, by_type: Mapping[str, Sequence[ExpectedLink]] | None = None) -> None: ...   # implemented (self._by_type)
    def add(self, record_type: str, expectation: ExpectedLink) -> None; def for_type(self, record_type: str) -> list[ExpectedLink]
    def record_types(self) -> list[str]; def merge(self, other: ExpectedLinkRegistry) -> None
def parse_expected_links(text: str, *, source: str = "<string>") -> ExpectedLinkRegistry
def load_expected_links(path: Path) -> ExpectedLinkRegistry
def default_expected_links() -> ExpectedLinkRegistry
def unmet_expectations(uow: UnitOfWork, record_id: str, expectations: Sequence[ExpectedLink]) -> list[MissingLink]
def missing_expected_links(uow, record_id, *, registry: ExpectedLinkRegistry | None = None, by_state: str | None = None) -> list[MissingLink]
```
```python
# tl_core.uow.UnitOfWork: .conn() -> sqlalchemy Connection (the open transaction)
# tl_core.services.errors.RecordNotFoundError(ServiceError)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/links/expected.py`
- `schema/fixtures/links/core-record.yaml`
- `docs/tickets/P0-I3/provided/test_expected_links.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/links/expected.py` (edit)
- `packages/tl-core/tests/test_expected_links.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T04.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_expected_links.py.txt packages/tl-core/tests/test_expected_links.py`
2. Implement the registry methods and functions; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_expected_links.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_expected_links.py.txt packages/tl-core/tests/test_expected_links.py
```
Expected: 31 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file (the models are not yours to change).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
