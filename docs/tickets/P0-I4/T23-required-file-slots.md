# P0-I4-T23 — Required file slots: the missing list

Status: ready
Tier: haiku
Labels: core
Depends on: — (models, stub and the provided test are on the base branch; the test inserts `cur_files` rows with SQL and passes its own registry)
Branch: `p0/i4b-t23-required-file-slots`

## Goal
`tl_core.files.required` answers "which required file slots does this record still lack?" by counting current rows of `cur_files`, so the
workflow engine can use it as a guard (a report must be attached before `Approved`). The model `MissingFile`, the SQL constants and the
signatures exist; the two functions marked `raise NotImplementedError` are the work. A provided test file (9 tests) must pass.

## Brief references (pasted)
> **20.1** `required_in_states`: required before `Receipt: Accepted`. Each record type declares file slots in LinkML.
> **7.1** (the same idea for links) Missing expected links show on the record and in data health reports, and can act as workflow guards.

### Specification (the provided test checks it)
This mirrors `unmet_expectations` and `missing_expected_links` in `tl_core.links.expected`, which you may read for the pattern.
- `unmet_file_slots(uow, record_id, slots)`: for each slot, in the order given, run `_COUNT_SQL` with `{"record_id": record_id, "slot": slot.name}` via `uow.conn().execute(_COUNT_SQL, params).scalar_one()` and convert to `int`. A count below 1 gives `MissingFile(slot=slot, found=count, needed=1)`; a slot with a current file is left out. Only available, non-superseded files count (the SQL says so); quarantined and rejected files never do.
- `missing_required_files(uow, record_id, *, registry=None, by_state=None)`: `row = uow.conn().execute(_TYPE_SQL, {"id": record_id}).first()`; no row raises `RecordNotFoundError(f"no record {record_id!r}")` (from `tl_core.services.errors`). `registry` defaults to `default_file_slots()` (from `tl_core.files.slots`; another ticket implements it, so do not call it in your tests; the provided test always passes a registry). Take `registry.for_type(<the record's type>)`, keep slots whose `required_in_states` is not empty, and with `by_state` keep only those whose `required_in_states` contains that state. Return `unmet_file_slots(uow, record_id, those slots)`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No SQLite- or Postgres-specific SQL; bound parameters only (the constants are given).
- pyright is `strict` for `packages/tl-core/src`: `row[0]` is `Any`, so use `typing.cast(str, row[0])`. ruff limits lines to 100 columns (docstrings too); run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I4-T23)` paragraph from the module docstring when you are done. The import of `default_file_slots` and `RecordNotFoundError` is yours to add.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/files/required.py (existing stub; keep every name and signature)
class MissingFile(BaseModel): slot: FileSlot; found: int; needed: int
def unmet_file_slots(uow: UnitOfWork, record_id: str, slots: Sequence[FileSlot]) -> list[MissingFile]
def missing_required_files(uow: UnitOfWork, record_id: str, *, registry: FileSlotRegistry | None = None, by_state: str | None = None) -> list[MissingFile]
```
```python
# tl_core.files.slots (final): FileSlot.required_in_states: list[str]; FileSlotRegistry.for_type(record_type) -> list[FileSlot]
# tl_core.uow.UnitOfWork: .conn() -> sqlalchemy Connection (the open transaction)
# tl_core.services.errors.RecordNotFoundError(ServiceError)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/files/required.py`
- `packages/tl-core/src/tl_core/links/expected.py` (the pattern to mirror)
- `docs/tickets/P0-I4/provided/test_required_files.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/files/required.py` (edit)
- `tests/services/test_required_files.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T23.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_required_files.py.txt tests/services/test_required_files.py`
2. Implement the two functions; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest tests/services/test_required_files.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_required_files.py.txt tests/services/test_required_files.py
```
Expected: 9 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
