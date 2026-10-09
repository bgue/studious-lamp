# P0-I7-T21 — Lake demo queries

Status: ready
Tier: haiku
Labels: tests, docs
Depends on: P0-I7-S1, S2, S3 (merged into the base of this branch)
Branch: `p0/i7b-t21-demo-queries`

## Goal
Six named SQL files under `dev/lake/queries/` answer real questions over the lake, and a test proves each one runs through the guarded `lake_query` service and returns the
expected rows on a small known ledger. The demo script (`dev/demos/P0-I7-lake.sh`, written by the supervisor) will print these files' results.

## Brief references (pasted)
> **28.2 Layers:** Bronze `events` (raw, append-only). Silver `cur_<class>` (the generated current-state schema plus promoted pset columns), `links`, `pset_values` (long form). Gold marts are SQL models over silver, versioned in the repo and tested.
> **28.3:** Every lake snapshot records the ledger `seq` range it covers; reports state "data as of seq N". `_tl_sync(snapshot_id, first_seq, last_seq, synced_at)` has one row per sync.

### The lake tables (columns you may use)
- `events(seq, event_id, stream_id, stream_type, stream_version, event_type, schema_version, scope, payload, actor, recorded_at, effective_at, correlation_id, causation_id, source, prev_hash, hash)`; `payload`, `recorded_at` and `effective_at` are VARCHAR (JSON text, ISO text).
- `cur_core_record(id, key, type, scope, title, description, status, psets_json, voided, version, last_seq, effective_schema_hash, conformance, created_at, updated_at, pset__valve_data__size_in, pset__valve_data__body_material)`; `voided` is BOOLEAN, `*_at` are TIMESTAMP (UTC).
- `links(link_id, scope, from_id, to_id, relation, status, pin, note, source, confidence, reason, declined, verified_by, verified_at, created_by, created_at, updated_at, version, last_seq)`.
- `pset_values(record_id, scope, path, pset, property_name, layer, value_type, value_text, value_num, value_bool, value_json, unit, last_seq, updated_at)`.
- `_tl_sync(snapshot_id, first_seq, last_seq, synced_at)`.

### The queries (file name: what it answers; the test below pins the result)
1. `events_by_type.sql`: how many events of each `event_type`: columns `event_type`, `n`; most frequent first, ties by `event_type`.
2. `records_overview.sql`: one row per record: `key`, `title`, `voided`, `conformance`, `last_seq`; ordered by `key`.
3. `links_by_relation.sql`: `relation`, `status`, `n` links, ordered by `relation`, `status`.
4. `valve_sizes.sql`: records with a nominal valve size, from the promoted column: `key`, `size_in` (the column `pset__valve_data__size_in` renamed), ordered by `key`; only rows where it is not null.
5. `pset_coverage.sql`: per pset, how many distinct records have a value and how many values there are: `pset`, `records`, `values`, ordered by `pset`.
6. `as_of.sql`: one row, one column `as_of_seq`: the greatest `last_seq` in `_tl_sync`.

Each file is one SELECT, starts with a `--` comment line saying what it answers, and has no trailing semicolon problems (a single trailing `;` is fine).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-lake/tests/builder.py (existing helper; importable in tl-lake tests as `from builder import LedgerBuilder`)
class LedgerBuilder:
    @classmethod
    def create(cls, db: Path) -> LedgerBuilder
    def engine(self) -> Engine
    def record(self, key: str, *, title: str | None = None, scope: str = SCOPE) -> str   # returns the record id
    def values(self, record_id: str, pset: str, values: dict[str, Any]) -> None
    def link(self, from_id: str, to_id: str, relation: str | None = None) -> str
    def head(self) -> int
# packages/tl-lake/tests/conftest.py fixtures: `ledger` (a LedgerBuilder on a fresh SQLite ledger), `lake` (a LakeConfig under tmp_path)
# tl_lake: read_snapshot(engine) -> context manager yielding a Connection; sync_lake(config, conn) -> SyncResult;
#          LakeQueryService(config).query(sql, limit=...) -> LakeQueryResult(.columns, .rows, .truncated, .as_of_seq)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-lake/tests/builder.py`
- `packages/tl-lake/tests/conftest.py`
- `packages/tl-lake/tests/test_query.py` (how a test syncs a ledger and queries it)
may explore: (none)

## Allowed paths
- `dev/lake/queries/events_by_type.sql`, `records_overview.sql`, `links_by_relation.sql`, `valve_sizes.sql`, `pset_coverage.sql`, `as_of.sql` (create)
- `packages/tl-lake/tests/test_demo_queries.py` (create)
- `docs/reports/P0-I7/P0-I7-T21.md` (create: your report; commit it)

## Steps
1. Write the six SQL files.
2. Write `test_demo_queries.py`: a fixture builds this ledger with `ledger`, then syncs it with `sync_lake` inside `read_snapshot(ledger.engine())`:
   records `A-1`, `B-1`, `C-1` (titles default); `values(A, "valve_data", {"size_in": 4, "manufacturer": "Acme"})`; `values(B, "valve_data", {"manufacturer": "Beta"})`;
   one link `A -> B` (default relation).
3. For each file, read it from `dev/lake/queries/` (find the repo root from `Path(__file__).resolve().parents[3]`) and run it with `LakeQueryService(lake).query(sql)`. Assert:
   - `events_by_type`: columns `["event_type", "n"]`; the row for `Record.Created` is `["Record.Created", 3]`; the rows are ordered by `n` descending.
   - `records_overview`: keys `["A-1", "B-1", "C-1"]`, all `voided` false.
   - `links_by_relation`: exactly one row, with `n` equal to 1.
   - `valve_sizes`: `[["A-1", 4.0]]`.
   - `pset_coverage`: `[["valve_data", 2, 3]]`.
   - `as_of`: `[[ledger.head()]]`, and the result's `as_of_seq` is the same number.
   - every query result has `truncated` false.
4. Run the acceptance commands, write the report, commit everything.

## Acceptance
```
uv run pytest packages/tl-lake/tests/test_demo_queries.py -q
just check
just test
```
Expected: the new test passes, `just check` and `just test` exit 0.

## Tests to add
- `packages/tl-lake/tests/test_demo_queries.py`: as in step 2 and 3 (one test function per query, one shared module-scoped fixture is fine).

## Report requirements
Standard report plus the decisive lines of the three acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a query's result differs from the expectation above for a reason you cannot explain from the table definitions.
- Stop rather than change anything under `packages/tl-lake/src/`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
