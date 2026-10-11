# Runbook — rebuild projections from the ledger

Purpose: rebuild the current-state tables (`cur_*`) from the append-only ledger so they match what the events say. Brief: §5.2, §5.4, §24.2.

## When to use
- Trigger: a current-state row disagrees with the ledger (found by a test, an audit, or `tl record show` against `tl events tail`).
- Trigger: a projector or the generated DDL changed and existing rows must be recomputed.
- Trigger: a restore brought back the ledger but not the projections.

## Before you start
- Access needed: read and write access to the ledger: the SQLite file or the `postgresql://` URL in `TL_DB` (default `./dev/data/tl.db`; for Postgres see `docs/runbooks/run-on-postgres.md`).
- Safe to run during business hours: yes for the dev ledger. The rebuild holds the database write lock for its duration, so writers wait (up to the 5 s busy timeout) and may fail on a large ledger; stop writers first on a busy ledger. On Postgres the rebuild takes the ledger advisory lock in the same way: a writer waits up to 10 s and then gets `LockTimeoutError`, and the rebuild itself is statement-bound (about 160 events a second), so give a large ledger hours, not minutes.

## Steps
0. In a new environment with no ledger file yet, create it first:
   ```
   uv run tl init
   ```
1. Note the state you expect to keep, for example a record:
   ```
   uv run tl record show --project P123 DEMO-0001
   ```
2. Rebuild all projections, or one by projector name:
   ```
   uv run tl projections rebuild
   just rebuild-projections core_record
   ```
   Expected: `replayed <n> events`, where `<n>` equals the number of events in the ledger.
   A rebuild of all projectors (no name) also records that the `rebuild` and `reindex` effects of settings were carried out: `uv run tl config get <key> --long` stops showing `pending rebuild` for a change made before it. A rebuild of named projectors records nothing.
   Rebuild `core_record` and `pset_values` together (the default): `pset_values` replays pset events over whatever `cur_core_record` holds, so a rebuild of only `pset_values` can resurrect older values.

## Verify
- `uv run tl record show --project P123 DEMO-0001` prints the same values as before when nothing was corrupted, or the values the events imply when a row had drifted.
- `uv run tl events tail --project P123 -n 5` shows the events the rows are built from; each line ends with its 64-hex hash.
- Running the rebuild a second time prints the same count and changes no row (the rebuild is deterministic).

## Roll back
- The rebuild runs in one transaction: it resets the selected projectors and replays every event, and if any step fails nothing changes and the old rows remain.
- The ledger is never modified by a rebuild, so there is nothing to undo there. A projector bug is fixed in code and the rebuild is run again.

## Related
- `docs/adr/0002-build-environment-constraints.md` (SQLite is the Phase 0 store).
- `packages/tl-adapters/README.md` (`rebuild_projections`), `packages/tl-core/README.md` (projector contract).
- `docs/runbooks/run-on-postgres.md` (the same commands on a Postgres ledger).
