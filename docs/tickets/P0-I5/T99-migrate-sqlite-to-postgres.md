# P0-I5-T99 — `tl migrate --from sqlite --to postgres`

Status: draft
Tier: sonnet
Labels: needs-human, cli, adapter, migration
Depends on: P0-I5 workstream A merged (Postgres ledger and unit of work)
Branch: `p0/i5a-t99-migrate-sqlite-to-postgres` (not created)
Approver (migration tickets): needs-human, to be named by the repository owner

## Goal
A command that copies a SQLite ledger into an empty Postgres schema without changing a single event: same `seq`, `event_id`,
timestamps, payload bytes and hashes. It then rebuilds every projection on Postgres and proves the result equal. This is a
data-migration tool, so it is a human gate (`docs/build-spec/04-gates.md` §2); fanout decision A1 of P0-I5 deferred it.
This file is a draft for the human and the next planning round. Nobody builds it from here.

## Why it is not in P0-I5
- `04-gates.md` §2: "Any migration or data conversion job" needs a named human approver and an ADR.
- Nothing in Phase 0 needs it: both adapters start empty, and the parity suite shows they behave the same.
- It is irreversible in effect (a wrong copy yields a ledger whose hash chain no longer verifies).

## Design sketch (for the reviewer, not a decision)
1. Preconditions: the target schema exists (`create_schema`) and `events` is empty; the source is quiescent (read in one
   `read_tx` snapshot, writers stopped or the snapshot's `head_seq` recorded).
2. Copy `events` in `seq` order in pages of 1000 with the target's own `INSERT` (not `append_in`: hashes and ids are copied,
   not recomputed). `payload` and `recorded_at` go in as the exact stored text and ISO string.
3. Verify before commit: row count equal; for each scope the last hash equal; re-walk each scope's chain on the target
   (`prev_hash` of event n = `hash` of n-1; `event_hash(...)` recomputed equals the stored hash).
4. `rebuild_projections` on the target (the projectors are deterministic, so this is the proof) and compare a checksum of each
   `cur_*` table between a SQLite rebuild and the Postgres rebuild.
5. Dry run by default; `--apply` required; refuses a non-empty target; prints the verification report; exit code 1 on any
   mismatch with nothing committed (one write transaction holds the ledger lock for the whole copy).
6. Object-store data is untouched (it is content-addressed and independent of the database).
7. The reverse direction (Postgres to SQLite) is the same code with the roles swapped and is out of scope.

## Open questions for the human
- Is a quiescent source acceptable, or must the tool support catching up from `seq` N after a first bulk copy?
- Who signs off the dry-run report before `--apply` is allowed on a production ledger?
- Should the command write a `Ledger.Migrated` marker event? It would be the first event with no command behind it, and it
  changes the hash chain by one link, so it needs an ADR (§5.2).

## Acceptance (when a human approves building it)
```
just check
just test-parity
uv run pytest tests/migrate -q          # round trip on a seeded ledger: copy, verify, rebuild, compare
```

## Blocked
needs-human: approver and ADR (04-gates.md §2).

## Decision
(none yet)
