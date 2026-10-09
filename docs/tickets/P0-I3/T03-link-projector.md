# P0-I3-T03 — `LinkProjector`: `cur_links` and `cur_link_counts`

Status: ready
Tier: haiku
Labels: core
Depends on: — (lifecycle rules, DDL and the stub are on the base branch)
Branch: `p0/i3-t03-link-projector`

## Goal
`LinkProjector.apply` turns the eight `Link.*` events into one row per link in `cur_links` and keeps per-record counts in `cur_link_counts`.
The class, its `ddl` and `reset`, the lifecycle rules (`next_status`) and the two generated tables already exist; `apply` is the work. A
provided test file (30 tests) must pass.

## Brief references (pasted)
> **7.1** A link has its own lifecycle. Fields: `from`, `to`, `relation`, `pin` (a specific revision, or floating to current), `note`, `source`, `confidence` (for suggested links), `status` (`suggested`, `active`, `stale`, `broken`, `retracted`), `verified_by/at`. Events: `Link.Suggested`, `Link.Added`, `Link.Accepted/Declined`, `Link.Repinned`, `Link.Verified`, `Link.Flagged`, `Link.Retracted`. **Links are never deleted.**
> **7.3** Declines are remembered, so the same suggestion does not come back. Retract, never delete, with a reason; history stays visible.
> **5.4** Projectors are deterministic: the row depends only on the event and on rows already in the database (no clock, no ids, no outside calls).

### Event payloads and what each does to the row (the provided test checks it)
Every link is its own ledger stream: `event.stream_id` is the `link_id`, `event.scope` is the link's scope, `event.actor` the actor, `event.recorded_at` the time, `event.stream_version` the version, `event.seq` the sequence. Timestamps are written with `iso_utc(event.recorded_at)` (from `tl_core.ledger`).

| Event | Payload keys | Effect on `cur_links` |
|---|---|---|
| `Link.Suggested` | `link_id, from_ref, to_ref, relation, pin, source, confidence, note` | INSERT. `status` from `next_status(None, ...)` (`suggested`). `from_id = from_ref`, `to_id = to_ref`, `pin`, `note`, `confidence` from the payload (missing means NULL), `source` = payload `source` or `"manual"` when missing/empty, `declined = false`, `reason`, `verified_by`, `verified_at` NULL, `created_by = event.actor`, `created_at = updated_at = iso_utc(recorded_at)`, `version`, `last_seq`, `scope = event.scope`, `link_id = event.stream_id` |
| `Link.Added` | same keys (no `confidence`) | INSERT as above; status `active` |
| `Link.Accepted` | `link_id, note?` | `status` via `next_status`; if the payload has a non-null `note`, set `note` |
| `Link.Declined` | `link_id, reason` | `status` via `next_status` (`retracted`); `declined = true`; `reason = payload.get("reason")` |
| `Link.Repinned` | `link_id, pin` | `status` via `next_status` (`active`); `pin = payload.get("pin")` (null means floating) |
| `Link.Verified` | `link_id` | `status` via `next_status`; `verified_by = event.actor`; `verified_at = iso_utc(recorded_at)` |
| `Link.Flagged` | `link_id, status, reason` | `status = next_status(current, type, flag=payload.get("status"))`; `reason = payload.get("reason")` |
| `Link.Retracted` | `link_id, reason` | `status` via `next_status` (`retracted`); `reason = payload.get("reason")`. The row stays |

For every event after the first also set `version = event.stream_version`, `last_seq = event.seq`, `updated_at = iso_utc(recorded_at)`.
For a non-creating event load `status, from_id, to_id` of the row by `link_id`; if there is no row raise `LookupError(f"no cur_links row for stream {event.stream_id}")`. `next_status` raises `InvalidLinkTransitionError` for an impossible event; let it propagate (the transaction rolls back).

### Counts
After every event refresh `cur_link_counts` for **both** records of the link (`from_id` and `to_id`). For record `:id`, run:
```sql
SELECT
 COALESCE(SUM(CASE WHEN status = 'active' AND from_id = :id THEN 1 ELSE 0 END), 0) AS active_out,
 COALESCE(SUM(CASE WHEN status = 'active' AND to_id = :id THEN 1 ELSE 0 END), 0) AS active_in,
 COALESCE(SUM(CASE WHEN status = 'stale' THEN 1 ELSE 0 END), 0) AS stale,
 COALESCE(SUM(CASE WHEN status = 'broken' THEN 1 ELSE 0 END), 0) AS broken,
 COALESCE(SUM(CASE WHEN status = 'suggested' THEN 1 ELSE 0 END), 0) AS suggested
FROM cur_links WHERE from_id = :id OR to_id = :id
```
then write the row for `record_id = :id` with those five counts, `last_seq = event.seq`, and `scope` = the `scope` of the record in `cur_core_record` (`SELECT scope FROM cur_core_record WHERE id = :id`), or `event.scope` when that record has no row. Upsert portably: `UPDATE cur_link_counts SET ... WHERE record_id = :id`; if `rowcount == 0` then `INSERT`. (Lines of the query are long: split the SQL string over several literals to stay within 100 columns.)

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- No SQLite- or Postgres-specific SQL: no `INSERT OR REPLACE`, no `ON CONFLICT`. Use bound parameters only; column names in `UPDATE ... SET` come from fixed literals, never from event data.
- pyright is `strict` for `packages/tl-core/src`: annotate dicts that mix value types as `dict[str, Any]`. ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I3-T03)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/projection/links.py (existing stub; keep name, handles, ddl, reset)
class LinkProjector:
    name = "links"
    handles = LINK_EVENT_TYPES
    def ddl(self, dialect: str) -> list[str]: ...           # implemented
    def apply(self, conn: Connection, event: Event) -> None: ...   # the work
    def reset(self, conn: Connection) -> None: ...          # implemented
```
```python
# packages/tl-core/src/tl_core/links/lifecycle.py (existing)
LinkStatus = Literal["suggested", "active", "stale", "broken", "retracted"]
LINK_EVENT_TYPES: frozenset[str]          # the eight Link.* event types
CREATING_EVENTS: frozenset[str]           # {"Link.Suggested", "Link.Added"}
def next_status(current: LinkStatus | None, event_type: str, *, flag: str | None = None) -> LinkStatus: ...
```
```sql
-- generated: packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_links.sql (the Postgres file differs only in types)
CREATE TABLE IF NOT EXISTS cur_links (
  link_id TEXT PRIMARY KEY, scope TEXT NOT NULL, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
  relation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', pin TEXT, note TEXT, source TEXT NOT NULL,
  confidence REAL, reason TEXT, declined INTEGER NOT NULL DEFAULT 0, verified_by TEXT, verified_at TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL,
  last_seq INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cur_link_counts (
  record_id TEXT PRIMARY KEY, scope TEXT NOT NULL, active_out BIGINT NOT NULL DEFAULT 0,
  active_in BIGINT NOT NULL DEFAULT 0, stale BIGINT NOT NULL DEFAULT 0, broken BIGINT NOT NULL DEFAULT 0,
  suggested BIGINT NOT NULL DEFAULT 0, last_seq BIGINT NOT NULL
);
```
```python
# Event (tl_core.ledger): .event_type .payload (dict) .seq .stream_id .stream_version .scope .actor .recorded_at (datetime)
# from tl_core.ledger import Event, iso_utc          # iso_utc(datetime) -> str
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/projection/links.py`
- `packages/tl-core/src/tl_core/links/lifecycle.py`
- `packages/tl-core/src/tl_core/projection/pset.py` (style of a projector; read only its `apply` and SQL constants)
- `docs/tickets/P0-I3/provided/test_link_projector.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/projection/links.py` (edit)
- `packages/tl-core/tests/test_link_projector.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T03.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_link_projector.py.txt packages/tl-core/tests/test_link_projector.py`
2. Implement `apply`; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_link_projector.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_link_projector.py.txt packages/tl-core/tests/test_link_projector.py
```
Expected: 30 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the table above, or if `lifecycle.py` or the DDL would need a change.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
