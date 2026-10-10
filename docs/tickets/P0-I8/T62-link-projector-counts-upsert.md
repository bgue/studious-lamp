# P0-I8-T62 — LinkProjector: refresh the link counts of a record with one upsert

Status: ready
Tier: haiku
Labels: core
Depends on: P0-I8-S62 (base of this branch)
Branch: `p0/i8d-t62-link-projector-counts-upsert`

## Goal
`LinkProjector` refreshes `cur_link_counts` for each end of a link event with one `INSERT ... SELECT ... ON CONFLICT DO UPDATE` instead of four statements (read the counts, read the record's scope, update, insert when the update found no row). A new link then costs three statements instead of seven to nine. The rows written are identical; the provided test `packages/tl-core/tests/test_link_projector_statements.py` pins the budget and the rows.

## Why (numbers)
The P0-I8 bench rebuilds 10,000 records (36,179 events, 19,985 of them link events) in 52.9 s on SQLite; `links` is 12.6 s of the 47 s spent in projectors, the second largest after the feed. On Postgres every statement is a round trip of about 0.5 ms, so the eight statements of a link event cost about 4 ms of a rebuild's 10 ms per event.

## Brief references (pasted)
> **Link counts (brief §7.1, §5.4):** `cur_link_counts` has one row per record that has ever had a link: `active_out`, `active_in` (links in state `active` leaving or entering the record), `stale`, `broken`, `suggested` (each over both directions) and the `last_seq` of the event that refreshed it. Every link event refreshes both records of the link. The row's `scope` is the record's scope (from `cur_core_record`), or the event's scope when the record has no row yet.

## Interfaces (verbatim from repo at the branch point)
In `packages/tl-core/src/tl_core/projection/links.py`:
```python
_RECORD_SCOPE_SQL = text("SELECT scope FROM cur_core_record WHERE id = :id")
_COUNTS_SQL = text(
    "SELECT "
    "COALESCE(SUM(CASE WHEN status = 'active' AND from_id = :id THEN 1 ELSE 0 END), 0) "
    "AS active_out, "
    "COALESCE(SUM(CASE WHEN status = 'active' AND to_id = :id THEN 1 ELSE 0 END), 0) "
    "AS active_in, "
    "COALESCE(SUM(CASE WHEN status = 'stale' THEN 1 ELSE 0 END), 0) AS stale, "
    "COALESCE(SUM(CASE WHEN status = 'broken' THEN 1 ELSE 0 END), 0) AS broken, "
    "COALESCE(SUM(CASE WHEN status = 'suggested' THEN 1 ELSE 0 END), 0) AS suggested "
    "FROM cur_links WHERE from_id = :id OR to_id = :id"
)
_UPDATE_COUNTS_SQL = text(
    "UPDATE cur_link_counts SET scope = :scope, active_out = :active_out, "
    "active_in = :active_in, stale = :stale, broken = :broken, suggested = :suggested, "
    "last_seq = :last_seq WHERE record_id = :record_id"
)
_INSERT_COUNTS_SQL = text(
    "INSERT INTO cur_link_counts (record_id, scope, active_out, active_in, stale, broken, "
    "suggested, last_seq) VALUES (:record_id, :scope, :active_out, :active_in, :stale, "
    ":broken, :suggested, :last_seq)"
)

    @staticmethod
    def _refresh_counts(conn: Connection, record_id: str, event: Event) -> None:
        counts = conn.execute(_COUNTS_SQL, {"id": record_id}).one()
        scope_row = conn.execute(_RECORD_SCOPE_SQL, {"id": record_id}).first()
        params: dict[str, Any] = {
            "record_id": record_id,
            "scope": scope_row.scope if scope_row is not None else event.scope,
            "active_out": counts.active_out,
            "active_in": counts.active_in,
            "stale": counts.stale,
            "broken": counts.broken,
            "suggested": counts.suggested,
            "last_seq": event.seq,
        }
        updated = conn.execute(_UPDATE_COUNTS_SQL, params).rowcount
        if updated == 0:
            conn.execute(_INSERT_COUNTS_SQL, params)
```
The table (generated, `record_id` is the primary key):
```sql
CREATE TABLE IF NOT EXISTS cur_link_counts (
  record_id TEXT PRIMARY KEY, scope TEXT NOT NULL,
  active_out INTEGER NOT NULL DEFAULT 0, active_in INTEGER NOT NULL DEFAULT 0,
  stale INTEGER NOT NULL DEFAULT 0, broken INTEGER NOT NULL DEFAULT 0,
  suggested INTEGER NOT NULL DEFAULT 0, last_seq INTEGER NOT NULL
);
```

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/projection/links.py` (the file to change)
- `packages/tl-core/tests/test_link_projector_statements.py` (provided; the spec: read every assertion; do not edit)
- `packages/tl-core/tests/test_link_projector.py` (existing behaviour tests; must keep passing; do not edit)
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/projection/links.py`

## Steps
1. Replace `_RECORD_SCOPE_SQL`, `_COUNTS_SQL`, `_UPDATE_COUNTS_SQL` and `_INSERT_COUNTS_SQL` with one statement: `INSERT INTO cur_link_counts (...) SELECT :record_id, COALESCE((SELECT scope FROM cur_core_record WHERE id = :record_id), :scope), <the five COALESCE(SUM(CASE ...), 0) counts as in _COUNTS_SQL>, :last_seq FROM cur_links WHERE from_id = :record_id OR to_id = :record_id ON CONFLICT (record_id) DO UPDATE SET scope = excluded.scope, active_out = excluded.active_out, active_in = excluded.active_in, stale = excluded.stale, broken = excluded.broken, suggested = excluded.suggested, last_seq = excluded.last_seq`.
   An aggregate without `GROUP BY` returns exactly one row even when no link matches, so the first event for a record inserts and later ones update. The `WHERE` clause is required: SQLite parses `INSERT ... SELECT ... ON CONFLICT` without one ambiguously. Every value stays a bound parameter.
2. `_refresh_counts` executes that statement once with `{"record_id": record_id, "scope": event.scope, "last_seq": event.seq}`. `apply`, `_create`, `_change` and the rest of the file do not change.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_link_projector_statements.py packages/tl-core/tests/test_link_projector.py -q --adapters sqlite,postgres
uv run pytest tests/property -q -k projection
just check
```
Expected: all pass on both adapters (Postgres must be reachable at `TL_PG_URL`; `sudo pg_ctlcluster 16 main start` if not); `just check` clean.

## Tests to add
None: the provided test file is the spec. Do not edit it.

## Report requirements
Standard report. Paste the pytest summary lines of all three commands and say how many statements one `Link.Added` costs now (the provided test asserts at most three).

## Learnings to apply (from the project memory)
- Run `just check` before you report: it lints `dev/` as well as the package, and a one-line E501 failed a whole batch once.

## Escalation triggers
- Stop and report *Blocked* if Postgres or SQLite rejects the statement, or an existing test in `test_link_projector.py` fails and the fix would need an edit outside `links.py`. Report the error text; do not add a per-dialect branch.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
