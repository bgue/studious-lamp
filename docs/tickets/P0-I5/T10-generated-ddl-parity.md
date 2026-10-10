# P0-I5-T10 — The generated DDL executes and stores values alike on both dialects

Status: merged
Tier: haiku
Labels: tests, adapter
Depends on: —
Branch: `p0/i5a-t10-generated-ddl-parity`

## Goal
A new test module executes every generated current-state table on SQLite and on Postgres (twice, to prove the DDL is idempotent) and checks that unique keys, booleans, timestamps, JSON and double-precision numbers behave the same on both. Until now the generated Postgres DDL was only compared to a golden file.

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
This ticket **adds** a test file (there is nothing to convert). It is the first time the generated Postgres DDL is executed in a test.
Write `tests/schema/test_generated_ddl_parity.py`. It uses only the fixtures `new_engine` and `dialect` and `tl_schema.ddl_loader.statements`.
```python
from tl_schema.ddl_loader import statements       # statements(table: str, dialect: "sqlite" | "postgres") -> list[str]
TABLES = ["cur_core_record", "cur_files", "cur_link_counts", "cur_links", "cur_numbering", "cur_pset_values", "cur_workflow_state"]
STAMP = "2026-10-09T12:00:00.123456+00:00"
```
Build the dialect argument with `kind = "postgres" if dialect == "postgres" else "sqlite"` (annotate `kind: Dialect`, `from tl_schema.generators.ddl_types import Dialect`).
Run statements with `conn.exec_driver_sql(statement)` inside `with engine.begin() as conn:`. Write these tests, each exactly as described:
1. `test_every_generated_table_can_be_created_twice` (parametrised over `TABLES`): create the table's statements twice (two separate transactions), then
   `table in inspect(conn).get_table_names()`.
2. A module fixture `engine(new_engine, dialect)` that creates all seven tables once, used by the rest.
3. `test_a_key_is_unique_within_a_scope_only`: insert into `cur_core_record (id, key, type, scope, title, version, last_seq, created_at, updated_at)`
   with values `(:id, :key, 'core.Record', :scope, 't', 1, 1, :ts, :ts)`: ids a/b with key `K-1` in scopes `project:P1` and `project:P2` succeed; id c with `K-1` in
   `project:P1` raises `sqlalchemy.exc.IntegrityError`.
4. `test_a_missing_key_never_collides`: two rows with `key` None in the same scope both insert; count is 2.
5. `test_timestamps_booleans_and_json_come_back_as_they_went_in`: insert one `cur_core_record` row with `psets_json` = `'{"a":{"b":1},"z":[1,2]}'` (bound),
   `voided` = `TRUE` (SQL keyword), `created_at`/`updated_at` = STAMP; read it back with `.mappings().one()`; assert both timestamps `== STAMP`, `voided == 1`,
   `psets_json == '{"a":{"b":1},"z":[1,2]}'`.
6. `test_numbers_keep_double_precision`: insert into `cur_pset_values (record_id, scope, path, pset, property_name, layer, value_type, value_num, value_bool, last_seq, updated_at)`
   the values `('r', 'company', 'p.x', 'p', 'x', 'standard', 'number', :n, :b, 1, :ts)` with `n = 1234567.891`, `b = True`; read `value_num, value_bool`;
   assert `value_num == 1234567.891` and `value_bool == 1`. (This catches a 4-byte `REAL` on Postgres.)
Module docstring: one line, at most 100 columns. Type-annotate everything (pyright runs on tests). Do not import from `tl_adapters` in this file.

## Context (read these, nothing else)
- `AGENTS.md`
- `conftest.py`
- `packages/tl-adapters/src/tl_adapters/db.py`
- `packages/tl-schema/src/tl_schema/ddl_loader.py`
may explore: (none)

## Allowed paths

- `tests/schema/test_generated_ddl_parity.py` (create)
- `docs/reports/P0-I5/P0-I5-T10.md` (create: your report; commit it)

## Steps
1. `pg_isready -h localhost` (start the cluster as in *Escalation triggers* if needed). Run `uv sync --all-packages` once in your worktree.
2. There is nothing to convert; confirm `tests/schema/test_generated_ddl_parity.py` does not exist yet.
3. Apply the recipe file by file. Re-run with `--adapters sqlite,postgres` after each file.
4. `uv run ruff format tests/schema/test_generated_ddl_parity.py`, then the acceptance commands, then write and commit the report.

## Acceptance
```
just check
uv run pytest tests/schema/test_generated_ddl_parity.py --adapters sqlite -q
uv run pytest tests/schema/test_generated_ddl_parity.py --adapters sqlite,postgres -q
just test-parity tests/schema/test_generated_ddl_parity.py
git diff --stat p0/i5a -- . ':!docs/reports'
```
Expected: `just check` clean (do not pipe it). Counts of passed tests, with no skips, failures or deselected tests in the first two:

| File | `--adapters sqlite` | `--adapters sqlite,postgres` |
|---|---|---|
| `tests/schema/test_generated_ddl_parity.py (new)` | 11 | 22 |
| **Total** | **11** | **22** |

`just test-parity` runs only the tests that use the adapter fixtures (it selects by marker), so its total can be lower than the third column when a file
has tests that never touch a database; it must show no failures and no skips. The diff stat must list only the files in *Allowed paths*.

## Tests to add
The file described above: 11 test cases per adapter (5 test functions; the first is parametrised over 7 tables).

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

## Review notes (for the reviewer)
- Fixture use: every test in the diff that touches a database takes `new_db`, `db`, `adapter_name` or `new_engine`, so it runs once per adapter. Grep the
  diff for a leftover `tmp_path / "...db"` or an import from `tl_adapters.sqlite`, and run
  `uv run pytest tests/schema/test_generated_ddl_parity.py --adapters sqlite,postgres --collect-only -q | grep -c '\[postgres'`: it must not be zero.
- Counts: re-run the acceptance commands; the pytest totals must equal the table, with no skip, xfail or deselect.
- Raw SQL: no `0`/`1` literal in a boolean column, no non-ISO timestamp, no `?` placeholder, no `sqlite_master`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
