# P0-I5-T04 — Numbering tests and property tests on both adapters

Status: ready
Tier: haiku
Labels: tests, adapter
Depends on: —
Branch: `p0/i5a-t04-numbering-parity`

## Goal
The tests in `test_numbering.py`, `test_numbering_uniqueness.py`, `test_projection_determinism.py` run once on SQLite and once on Postgres instead of on SQLite only, with every
test kept and every assertion unchanged. After this ticket `just test-parity` exercises the module on both databases. This ticket changes tests
only; the adapter, the parity fixtures and `tl_core` are already on the branch point.

## Brief references (pasted)
> **03 §6 Dialect isolation.** `tl_core` sees only the `Ledger`, `UnitOfWork`, `ProjectionStore`, `ObjectStore`, `Bus`, `Queue`
> Protocols. `tl_adapters.sqlite` and `tl_adapters.postgres` implement them. Any SQL that differs by dialect lives there, and only
> there. The parity suite runs every adapter test against both and is the gate for Postgres (§15).
>
> **03 §10 Testing conventions.** Cross-package and adapter tests live in `tests/`. Parity tests are parametrised by adapter fixture.
>
> **Fanout P0-I5 decision A4.** Parity tests skip cleanly when `TL_PG_URL` is unreachable; CI runs them. Each test gets an isolated
> schema, so runs do not interfere.
>
> **Brief §14.** SQLite (dev) and PostgreSQL 16+ (prod) are both first-class; "Adapter interface; parity test suite runs on both".

## Interfaces (verbatim from the repo at the branch point)
```python
# conftest.py at the repository root (exists on the branch point; do not edit)
# Every test that asks for adapter_name, adapter, new_db, db, new_engine or dialect runs once per adapter named by
# --adapters (default: sqlite; `just test-parity` and the commands below pass sqlite,postgres).
new_db: Callable[[], DbTarget]       # call it: a fresh, EMPTY, isolated database (SQLite file under tmp_path, or a Postgres schema)
db: DbTarget                         # new_db() with create_schema(default registry) already run (a module may define its own `db`)
new_engine: Callable[[], Engine]     # call it: an engine on a fresh empty database (for projector unit tests); disposed after the test
dialect: str                         # "sqlite" or "postgres": what a projector's ddl(dialect) takes
adapter_name: str                    # "sqlite" or "postgres"

# packages/tl-adapters/src/tl_adapters/db.py (exists; picks the adapter from the target)
DbTarget = str | Path                # a SQLite file path, or a "postgresql://..." URL; treat it as opaque
def create_schema(target: DbTarget, *, registry: ProjectorRegistry | None = None) -> None: ...
def open_uow(target: DbTarget, *, readonly: bool = False, registry: ProjectorRegistry | None = None,
             bus: Bus | None = None) -> AbstractContextManager[BaseUnitOfWork]: ...
def rebuild_projections(target: DbTarget, *, types: Sequence[str] | None = None,
                        registry: ProjectorRegistry | None = None, on_progress: Callable[[int], None] | None = None) -> int: ...
def make_engine(target: DbTarget) -> Engine: ...
def make_ledger(engine: Engine, *, clock=..., id_gen=...) -> LedgerWithSchema: ...
# BaseUnitOfWork lives in tl_adapters._unit (SqliteUnitOfWork and PostgresUnitOfWork derive from it):
#   .ledger, .conn(), .append(**kwargs), context manager
```

## Conversion recipe (apply to every file in *Allowed paths*)
The test bodies stay as they are. Only how the database is made and a few SQL details change.
1. **Imports.** `from tl_adapters.sqlite.uow import create_schema, open_uow, rebuild_projections` (any subset) becomes
   `from tl_adapters.db import DbTarget, create_schema, open_uow, rebuild_projections` (keep only the names the file uses, plus `DbTarget`
   when you annotate with it). A `SqliteUnitOfWork` annotation becomes `BaseUnitOfWork` (`from tl_adapters._unit import BaseUnitOfWork`).
   Add `from collections.abc import Callable` when you annotate `new_db`. Run `uv run ruff check --fix <files>` to sort imports.
2. **Annotations.** A database handle was a `Path`; it is now a `DbTarget`. `sed -i 's/\bdb: Path\b/db: DbTarget/g'` does most of it; check
   `-> Path` return types and helper parameters by hand. Keep `Path` where it still means a real directory or file (packages dir, object store root).
3. **Making the database.** A fixture such as
   ```python
   @pytest.fixture
   def db(tmp_path: Path) -> Path:
       path = tmp_path / "tl.db"
       create_schema(path)
       return path
   ```
   becomes
   ```python
   @pytest.fixture
   def db(new_db: Callable[[], DbTarget]) -> DbTarget:
       path = new_db()
       create_schema(path)
       return path
   ```
   A test that built `tmp_path / "x.db"` itself gets a `new_db: Callable[[], DbTarget]` parameter instead of `tmp_path` (keep `tmp_path` too if
   the body still uses it for something else) and writes `new_db()`. The parameter makes the test run once per adapter; nothing else is needed.
4. **Raw SQL in the tests** (INSERT/UPDATE statements a test writes by hand) must work on both databases:
   - a boolean column takes `TRUE` / `FALSE` (SQL keywords, accepted by SQLite 3.23+), or a bound Python `bool`; never the literals `0` / `1`
     (Postgres: `column "declined" is of type boolean but expression is of type integer`);
   - a timestamp column takes a real ISO string such as `'2026-01-01T00:00:00+00:00'`; never `'x'` or `'2026'`;
   - parameters are SQLAlchemy `text(...)` with `:name` binds; the driver-style `?` placeholder (`exec_driver_sql(..., (x,))`) fails on Postgres;
   - do not call `sqlalchemy.inspect(conn).get_columns(...)` (it breaks on Postgres); for column names use
     `from tl_core.projection.promoted import table_columns` and `table_columns(conn, "cur_core_record")`;
   - no `sqlite_master`, `PRAGMA` or `rowid`. If a test needs one, stop (see *Escalation triggers*).
5. **Do not weaken anything.** No test is removed, skipped, marked xfail, or loosened. The number of collected tests must match the counts in *Acceptance*.
   Hypothesis tests keep their strategies and settings.
6. **Never change code outside *Allowed paths*.** If a test passes on SQLite and fails on Postgres for a reason that is not one of the test-side
   items above (a wrong value, a different order, an exception from `tl_core` or `tl_adapters`), that is a real dialect bug: stop and report it as *Blocked*.

## Specifics for this ticket
- `test_numbering.py` is the plain recipe (`db` fixture and `db: Path` annotations). Its concurrency test must keep running two real threads on one
  database; it is the test that shows numbers stay unique on Postgres.
- The two files under `tests/property/` are Hypothesis tests that made a temporary directory **inside each example**
  (`with tempfile.TemporaryDirectory() as tmp: db = Path(tmp) / "tl.db"`). Replace that with one fresh database per example:
  add `new_db: Callable[[], DbTarget]` as the **first** parameter of the test (before the `@given` argument), call `db = new_db()` where the temporary
  database was made, and delete the `tempfile` and `Path` imports when nothing else uses them. `new_db` is a function-scoped fixture and Hypothesis
  warns about that: add `HealthCheck.function_scoped_fixture` to the existing `suppress_health_check=[...]` list. It is safe because `new_db` is a
  factory and every example calls it for a new database. Keep `max_examples` and the strategies unchanged. Dedent the body one level when the `with` goes away
  (numbering keeps its `with use_numbering(...)`).
- A pytest fixture cannot be module-scoped when it depends on the adapter parameter; do not try to share one database across examples.

## Context (read these, nothing else)
- `AGENTS.md`
- `tests/services/test_numbering.py`
- `tests/property/test_numbering_uniqueness.py`
- `tests/property/test_projection_determinism.py`
- `conftest.py`
- `packages/tl-adapters/src/tl_adapters/db.py`
may explore: (none)

## Allowed paths
- `tests/services/test_numbering.py` (edit)
- `tests/property/test_numbering_uniqueness.py` (edit)
- `tests/property/test_projection_determinism.py` (edit)
- `docs/reports/P0-I5/P0-I5-T04.md` (create: your report; commit it)

## Steps
1. `pg_isready -h localhost` (start the cluster as in *Escalation triggers* if needed). Run `uv sync --all-packages` once in your worktree.
2. Run `uv run pytest tests/services/test_numbering.py tests/property/test_numbering_uniqueness.py tests/property/test_projection_determinism.py --adapters sqlite -q` first and note the count; it must equal the SQLite count below before you start.
3. Apply the recipe file by file. Re-run with `--adapters sqlite,postgres` after each file.
4. `uv run ruff format tests/services/test_numbering.py tests/property/test_numbering_uniqueness.py tests/property/test_projection_determinism.py`, then the acceptance commands, then write and commit the report.

## Acceptance
```
just check
uv run pytest tests/services/test_numbering.py tests/property/test_numbering_uniqueness.py tests/property/test_projection_determinism.py --adapters sqlite -q
uv run pytest tests/services/test_numbering.py tests/property/test_numbering_uniqueness.py tests/property/test_projection_determinism.py --adapters sqlite,postgres -q
just test-parity tests/services/test_numbering.py tests/property/test_numbering_uniqueness.py tests/property/test_projection_determinism.py
git diff --stat p0/i5a -- . ':!docs/reports'
```
Expected: `just check` clean (do not pipe it). Counts of passed tests, with no skips, failures or deselected tests in the first two:

| File | `--adapters sqlite` | `--adapters sqlite,postgres` |
|---|---|---|
| `tests/services/test_numbering.py` | 21 | 41 |
| `tests/property/test_numbering_uniqueness.py` | 1 | 2 |
| `tests/property/test_projection_determinism.py` | 1 | 2 |
| **Total** | **23** | **45** |

`just test-parity` runs only the tests that use the adapter fixtures (it selects by marker), so its total can be lower than the third column when a file
has tests that never touch a database; it must show no failures and no skips. The diff stat must list only the files in *Allowed paths*.

## Tests to add
None. Every existing test keeps its name, body and assertions; the numbers above are the proof. (Pure unit tests in the same files that never use a
database are not parametrised and count once.)

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the three pytest summary lines (sqlite, sqlite+postgres, test-parity); every raw SQL
statement you changed and why (one line each); any test you could not convert (it must be under *Blocked*, not skipped).
Candidate learnings go in the report under *Learnings*; do not edit `docs/memory/LEARNINGS.md`.

## Escalation triggers
- A converted test fails on `postgres` with a wrong value, wrong order, or an exception raised inside `packages/tl-core/src` or
  `packages/tl-adapters/src` (a production dialect bug): do not edit production code, do not skip the test; write the failing test id and
  the assertion or traceback under *Blocked* and stop.
- `pg_isready -h localhost` fails: run `sudo pg_ctlcluster 16 main start`, wait, retry once; if it still fails write *Blocked*.
- A file needs more than the recipe (for example SQLite-only behaviour such as WAL, `PRAGMA`, `sqlite_master`): write *Blocked*; do not delete the test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
