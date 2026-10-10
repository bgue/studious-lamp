# P0-I7-T06 — Runbook: restore a database from the ledger archive

Status: ready
Tier: haiku
Labels: docs
Depends on: P0-I7-T01 to T04 and the drills (S12), merged into the base of this branch
Branch: `p0/i7a-t06-runbook-restore-from-archive`

## Goal
A runbook at `docs/runbooks/restore-from-archive.md` tells an operator how to rebuild a SQLite or Postgres database from the signed ledger archive alone, what each refusal means, and how to verify and cut over.

## Brief references (pasted)
> **24.4 Restore, Rebuild-from-archive (last resort):** fresh database, replay the ledger archive, rebuild projections. Proves the system can survive total database loss.
> **Full disaster recovery:** restore Postgres via PITR, verify against the ledger archive (hash chain continuity, last `seq`), and reconcile against the object store (every referenced hash present).
> **Fanout D1:** restore inserts events verbatim through a per-dialect admin function (`restore_events`), not `Ledger.append`; it refuses a non-empty `events` table.

### Facts (all run by the supervisor on 2026-10-10; copy the commands and output shapes as written)
Inputs: the archive directory (`--from-archive`, or `TL_ARCHIVE_DIR`), the public key (`--public-key`, or `TL_ARCHIVE_PUBLIC_KEY`, default `dev/data/archive-signing.pub`; keep a copy of the public key apart from the archive, or an attacker who can
replace the archive can replace the key), and an **empty** target: a new SQLite file (its directory is created) or an empty Postgres database or schema.

1. Check the archive first, with the values recorded when it was sealed (see `ledger-archive-and-verify.md`):
   ```
   uv run tl archive verify --archive /path/to/archive --public-key /path/to/archive-signing.pub --expect-last-seq 18 --expect-manifest <sha256 recorded at seal time>
   ```
   ```
   verified 2 segments, seq 1..18 (18 events)
   ```
2. Use the same schema packages the ledger used, because promoted pset columns of `cur_core_record` come from the schema packages in force at restore time, not from events (a different set can give different promoted columns):
   ```
   export TL_SCHEMA_DIR=schema/fixtures
   ```
   (`schema/fixtures` is the default.) The restore loads the effective schema of every scope in the archive before it writes anything; if one cannot be loaded it stops with
   `error: cannot load the effective schema of scope '<scope>' to add promoted columns: ...; nothing was written`.
3. Restore into a new SQLite file:
   ```
   uv run tl restore --from-archive /path/to/archive --db /path/to/new.db --public-key /path/to/archive-signing.pub
   ```
   ```
   restored 18 events from 2 segments into /path/to/new.db (last seq 18)
   verify 0.01s, insert 0.02s, rebuild 0.01s, total 0.06s
   ```
4. Restore into Postgres: create an empty database, then restore into its URL (the password is hidden in the output):
   ```
   cd /tmp && sudo -u postgres createdb tl_restored
   uv run tl restore --from-archive /path/to/archive --db postgresql://postgres:postgres@localhost:5432/tl_restored --public-key /path/to/archive-signing.pub
   ```
   ```
   restored 18 events from 2 segments into postgresql://postgres:***@localhost:5432/tl_restored (last seq 18)
   verify 0.02s, insert 0.37s, rebuild 0.12s, total 0.52s
   ```
   To keep several ledgers in one Postgres database use a schema-scoped URL (see `postgres-local-setup.md`). Never restore into the shared parity-test database `tl_test`.
5. What the command does, in order: verifies the archive (refuses with the first divergence if it does not verify); loads the schemas; creates the tables; then in **one transaction** inserts the archived events verbatim (seq, ids, times and hashes unchanged), adds the promoted
   columns, replays the events into the projections, and verifies the result against the archive; then commits. Any failure rolls that transaction back, so the database is left with empty tables and the same command can be run again.
6. What it refuses, with exit 1 and `error: ...` on stderr:
   - an archive that does not verify. It also prints the first divergence on stdout and creates nothing:
     ```
     divergence: file_hash segment=000000000011-000000000018 seq=11: events.ndjson differs from its hash
     error: the archive does not verify: file_hash in segment 000000000011-000000000018 at seq 11: events.ndjson differs from its hash
     ```
     Go to `ledger-archive-and-verify.md`; do not restore from a copy that does not verify.
   - a target that already has events: `error: the events table is not empty; restore only into an empty database`. To start over, delete the SQLite file, or drop the Postgres database (`cd /tmp && sudo -u postgres dropdb tl_restored`), and run again.
   - a missing archive directory (`error: no archive at ...`) or an unreadable public key (`error: cannot read the public key ...`).
7. Warnings go to stderr after the two summary lines: `warning: scope <scope>: the ledger last recorded effective schema <hash12>, the schema packages in force now give <hash12>; promoted columns may differ from the original (restore with the TL_SCHEMA_DIR the ledger used)`.
   They do not change the exit code. Fix the schema directory and restore again into a fresh database.
8. Verify the restored database (both must exit 0):
   ```
   uv run tl ledger verify --db /path/to/new.db
   uv run tl archive verify --archive /path/to/archive --public-key /path/to/archive-signing.pub --db /path/to/new.db --deep
   ```
   ```
   verified ledger /path/to/new.db: 18 events, hash chains intact
   verified 2 segments, seq 1..18 (18 events)
   database /path/to/new.db agrees up to seq 18
   ```
9. Know what is lost: only events up to the archive's last seq come back. Events written after the last sealed segment are gone (that gap is the archive RPO: seal often). Records' files are in the object store, not the archive: reconcile them afterwards with
   `uv run tl file reconcile` (see `object-store-reconciliation.md`). Webhook subscriptions come back (status `active`) from their events, but a signing secret is never in the ledger and delivery state is not restored. Before starting the webhook worker, list them with `uv run tl webhook ls` and rotate each secret (`uv run tl webhook rotate-secret <subscription id> --project P123 --overlap-hours 24`; see `webhook-operations.md`), then give each receiver its new secret.
10. Point the services at the new database (`TL_DB` for SQLite, the URL for Postgres) and restart them. New events continue at seq max+1 with the hash chain intact.
11. Roll back: the restore only writes to the empty target. Delete that file or drop that database. The archive and any other database are untouched.

### Must cover
Purpose and when to use (total database loss, new environment, proving the archive works); prerequisites (archive, separately held public key, empty target, same `TL_SCHEMA_DIR`); both targets; what the command does; every refusal and what to do; warnings; verification; what is lost
and the follow-up reconciliation; cut-over; roll back; related runbooks (`ledger-archive-and-verify.md`, `pgbackrest-restore.md`, `sqlite-backup-and-litestream.md`, `rebuild-projections.md`, `object-store-reconciliation.md`, `postgres-local-setup.md`, `webhook-operations.md`).

Learnings that apply:
- Use `docs/templates/runbook.md` (Purpose, When to use, Before you start, Steps, Verify, Roll back, Related). Lead with the purpose; one idea per sentence; numbered steps; commands in fenced blocks that
  can be copied from the repository root; each step names the output to expect. No model names, no secrets: use variable names (`TL_PG_URL`) and the documented dev defaults only.
- Every command in the runbook must be one of the commands in *Facts* below, spelled the same way. If a step needs a command that is not listed, do not invent it: write it under *Blocked*.
- Do not describe features that are not in the facts. Production key custody, retention classes and object lock are human follow-ups: say they are not built.
- `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. ruff does not check Markdown here; `just check` must still pass.

## Interfaces (verbatim from the repo at the branch point)
Not applicable (documentation only).

## Context (read these, nothing else)
- `docs/templates/runbook.md`
- `docs/runbooks/rebuild-projections.md` (style reference only)
may explore: (none)

## Allowed paths
- `docs/runbooks/restore-from-archive.md` (create)
- `docs/reports/P0-I7/P0-I7-T06.md` (create: your report; commit it)

## Acceptance
```
just check
test -s docs/runbooks/restore-from-archive.md
```
Expected: `just check` clean. Then check yourself, and say so in the report, that every fenced command appears in *Facts* and that each *Must cover* item has a section or step.

## Tests to add
None (documentation).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T06.md` and committed. List under *Open questions* anything in the facts that looked inconsistent.

## Escalation triggers
- Stop and report *Blocked* if the facts contradict each other or a step would need a command that is not listed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
