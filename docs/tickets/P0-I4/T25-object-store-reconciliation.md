# P0-I4-T25 — Object-store reconciliation and `tl file reconcile`

Status: ready
Tier: haiku
Labels: core, cli
Depends on: — (models, stubs, fs store and the provided tests are on the base branch)
Branch: `p0/i4b-t25-object-store-reconciliation`

## Goal
A read-only reconciliation job compares the hashes the ledger references (`cur_files`) with the object store and reports objects that
are missing, objects whose bytes are corrupt (optional, reads everything), orphaned content keys and leftover staging keys. `tl file
reconcile [--verify]` prints the report and exits 1 when anything is missing or corrupt. This is the recovery capability the brief names
for "missing or corrupt objects"; the runbook (supervisor) tells an operator what to do with the report. The models, SQL constant, helper
protocol and signatures exist; the function `reconcile_objects` and the command body `reconcile` marked `raise NotImplementedError` are the
work. Two provided test files (12 and 6 tests) must pass.

## Brief references (pasted)
> **24.5** Missing or corrupt objects: Reconciliation job compares referenced hashes with the store. Restore from object versions or the replica.
> **5.2** Files are immutable too: object keys are content-addressed (SHA-256). A file is never replaced.

### Specification (the provided tests check it)
**`reconcile_objects(uow, store, *, verify=False) -> ReconcileReport`** (`packages/tl-core/src/tl_core/files/reconcile.py`)
- Run `_ROWS_SQL` with `uow.conn().execute(_ROWS_SQL)`; each row has `sha256`, `size`, `file_id`. Group by `sha256`: collect `file_ids` in row order (the SQL sorts them) and keep the size of the first row of each hash (`setdefault`).
- For each distinct hash in sorted order, `key = object_key(digest)`. If `not store.exists(key)`: add `ObjectProblem(kind="missing", sha256=digest, key=key, file_ids=...)` to `missing` and go on. If the object exists and `verify` is true: read it with `store.get(key)` in 1 MiB chunks, hashing with `hashlib.sha256` and counting bytes, closing the stream in a `finally`. If the hex digest differs from `digest` the detail is `f"sha256 is {computed}"`; otherwise, if the count differs from the row's size, `f"{count} bytes, expected {size}"`; either way add `ObjectProblem(kind="corrupt", ..., detail=detail)` to `corrupt`. Without `verify` never call `store.get`.
- Listing: `listed = isinstance(store, _Listing)` (a runtime-checkable Protocol already defined in the file). When listed, go through `sorted(store.iter_keys())`: a key starting with `"sha256/"` that is not in `{object_key(d) for d in groups}` goes to `orphans`; a key starting with `"staging/"` goes to `staging`; others are ignored. When not listed, both lists stay empty.
- Return `ReconcileReport(checked=<number of distinct hashes>, verified=verify, listed=listed, missing=..., corrupt=..., orphans=..., staging=...)`. The function never writes to the store or the ledger.

**`tl file reconcile [--verify]`** (`packages/tl-cli/src/tl_cli/file_reconcile.py`, function `reconcile`)
- `db = ctx.obj` (a `Path`). `store = make_object_store()` from `tl_adapters.objectstore`; a `ValueError` (unconfigured secret) prints `error: <message>` on stderr and exits 1 (`typer.Exit(code=1)`). Then `with open_uow(db, readonly=True) as uow: report = reconcile_objects(uow, store, verify=verify)`.
- Print, one per line with `typer.echo`: `checked <n>`, `verified true|false`, `missing <n>`, `corrupt <n>`, `orphans <n>` and `staging <n>` (each prints the word `unknown` instead of a number when `report.listed` is false).
- Then one line per problem, missing ones first then corrupt: `<kind> <sha256> files=<comma-joined file ids>`, followed by a space and the detail when there is one. Then one line `orphan <key>` per orphan.
- Exit code 1 when `report.ok` is false (raise `typer.Exit(code=1)` after printing), else 0.
- Imports you need: `make_object_store` from `tl_adapters.objectstore`, `open_uow` from `tl_adapters.sqlite.uow`, `reconcile_objects` from `tl_core.files.reconcile`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copies.
- pyright is `strict` for `packages/tl-core/src`; the CLI is `standard`. ruff limits lines to 100 columns (docstrings too); run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Tests run with `TL_ENV=dev` (root `conftest.py` and the provided CLI test). Do not add any default secret.
- Remove both `STUB (P0-I4-T25)` paragraphs (module docstrings) when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/files/reconcile.py (existing stub; models, _ROWS_SQL, _Listing are final)
class ObjectProblem(BaseModel): kind: Literal["missing", "corrupt"]; sha256: str; key: str; file_ids: list[str]; detail: str | None = None
class ReconcileReport(BaseModel):
    checked: int; verified: bool; listed: bool
    missing: list[ObjectProblem]; corrupt: list[ObjectProblem]; orphans: list[str]; staging: list[str]
    @property
    def ok(self) -> bool: ...        # implemented: nothing missing or corrupt
def reconcile_objects(uow: UnitOfWork, store: ObjectStore, *, verify: bool = False) -> ReconcileReport
# packages/tl-core/src/tl_core/files/types.py (frozen): ObjectStore.exists(key) -> bool; .get(key) -> BinaryIO; object_key(sha256_hex) -> "sha256/<aa>/<bb>/<digest>"
```
```python
# packages/tl-cli/src/tl_cli/file_reconcile.py (existing stub; keep the signature and options)
def reconcile(ctx: typer.Context, verify: Annotated[bool, typer.Option("--verify", ...)] = False) -> None
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/files/reconcile.py`
- `packages/tl-cli/src/tl_cli/file_reconcile.py`
- `docs/tickets/P0-I4/provided/test_reconcile.py.txt`
- `docs/tickets/P0-I4/provided/test_cli_file_reconcile.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/files/reconcile.py` (edit)
- `packages/tl-cli/src/tl_cli/file_reconcile.py` (edit)
- `tests/services/test_reconcile.py` (create: byte-for-byte copy of the provided file)
- `packages/tl-cli/tests/test_cli_file_reconcile.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I4/P0-I4-T25.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_reconcile.py.txt tests/services/test_reconcile.py` and `cp docs/tickets/P0-I4/provided/test_cli_file_reconcile.py.txt packages/tl-cli/tests/test_cli_file_reconcile.py`
2. Implement the function and the command; delete both STUB paragraphs.
3. Run the acceptance commands, write the report, commit.

## Acceptance
```
uv run pytest tests/services/test_reconcile.py packages/tl-cli/tests/test_cli_file_reconcile.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_reconcile.py.txt tests/services/test_reconcile.py
diff docs/tickets/P0-I4/provided/test_cli_file_reconcile.py.txt packages/tl-cli/tests/test_cli_file_reconcile.py
```
Expected: 18 tests pass, `just check` and `just test` exit 0, both `diff`s print nothing.

## Tests to add
None beyond the provided files.

## Report requirements
Standard report plus the decisive lines of the acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change any other file (`file.py` and the stores are not yours).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
