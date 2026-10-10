# P0-I7-T08 — Runbook: SQLite snapshots and Litestream

Status: ready
Tier: haiku
Labels: docs
Depends on: P0-I7-T01 to T04 and the drills (S12), merged into the base of this branch
Branch: `p0/i7a-t08-runbook-sqlite-backup-litestream`

## Goal
A runbook at `docs/runbooks/sqlite-backup-and-litestream.md` tells a developer how to snapshot the dev SQLite ledger, replicate it with Litestream, and restore either, and verify the result.

## Brief references (pasted)
> **24.3 Backup, Database, dev:** Litestream continuous replication to MinIO/S3; **SQLite online backup API for snapshots**. Targets: RPO <= 5 min for the database.
> **ADR-0002:** Litestream and pgBackRest are configured but not required locally; the dev backup path is the SQLite online-backup API plus the ledger archive, which is the database-independent restore path.

### Facts (all run by the supervisor on 2026-10-10; copy the commands and output shapes as written)
1. Snapshot (a single self-contained file, taken while the ledger is in use; the destination must not exist; its directory is created; the file is read-only):
   ```
   uv run tl backup sqlite --to dev/data/backups/tl-snap.db
   ```
   ```
   backed up 18 events from dev/data/tl.db to dev/data/backups/tl-snap.db (258048 bytes, sha256 349752d3e816147c1d38a539b5a19302ffcee9ec91fbb17dc2bdf071e8793501)
   ```
   The source is the root `--db` (`TL_DB`). An existing destination prints `error: destination exists: <path>` and exits 1; a missing ledger prints `error: source database not found: <path>`. A filesystem without hard links prints
   `error: filesystem does not support hard links; choose another destination (...)`. Nothing is left behind after an error.
2. Restore from a snapshot: copy it to the ledger location, make it writable, verify:
   ```
   cp dev/data/backups/tl-snap.db dev/data/tl.db && chmod 644 dev/data/tl.db
   uv run tl ledger verify
   ```
   ```
   verified ledger dev/data/tl.db: 18 events, hash chains intact
   ```
   Events written after the snapshot are lost: take snapshots as often as the RPO needs, or use Litestream. Compare with the archive: `uv run tl archive verify --db dev/data/tl.db --deep` (see `ledger-archive-and-verify.md`).
3. Litestream v0.3.13 (Apache-2.0) replicates the ledger continuously. It is not a Python dependency and is not in the repository. Fetch the pinned release once (one attempt, checksum checked, into the git-ignored `dev/data/tools/`):
   ```
   bash dev/drills/fetch_litestream.sh
   ```
   It prints `Litestream v0.3.13 is in dev/data/tools/litestream`, or nothing if it is already there. If the download fails (the container's proxy can refuse hosts), do not retry in a loop: use snapshots and the ledger archive instead.
4. The config is `dev/backup/litestream.yml` (variables `TL_DB`, default `./dev/data/tl.db`, and `LITESTREAM_REPLICA`, a directory for the file replica; an S3/MinIO replica block is in the file, commented out, with credentials from the environment). Replicate in the foreground (leave it running):
   ```
   export TL_DB=dev/data/tl.db LITESTREAM_REPLICA=dev/data/litestream
   dev/data/tools/litestream replicate -config dev/backup/litestream.yml
   ```
   The sync interval is 1 s, so the replica trails the ledger by about a second plus the write time. The ledger must be in WAL mode (the ledger engine sets it).
5. Restore the replica into a new file after the ledger is lost, then verify:
   ```
   dev/data/tools/litestream restore -config dev/backup/litestream.yml -o dev/data/restored.db "$TL_DB"
   uv run tl ledger verify --db dev/data/restored.db
   ```
   The restore log ends with `renaming database from temporary location`. In the drill, losing the ledger right after a batch of writes recovered all of them (RPO 0 events; a worst case can lose the last second).
6. The drill exercises snapshot, Litestream, the archive and pgBackRest and measures RPO and RTO: `just drill` (see `pgbackrest-restore.md` and `docs/templates/restore-drill.md`). A Litestream or snapshot restore is a copy of the database layer only; the ledger archive remains the database-independent path (`restore-from-archive.md`).
7. Roll back: a snapshot or restored file is a new file; delete it. Stopping Litestream changes nothing in the ledger.

### Must cover
Purpose and when to use (dev SQLite protection; a bad write; a lost file); snapshots; restoring a snapshot; Litestream fetch, run and restore; limits (RPO of a snapshot is the interval between snapshots; Litestream is dev, production database backup is pgBackRest); verification; roll back; related runbooks (`ledger-archive-and-verify.md`, `restore-from-archive.md`, `pgbackrest-restore.md`).

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
- `dev/backup/litestream.yml`
- `dev/drills/fetch_litestream.sh`
may explore: (none)

## Allowed paths
- `docs/runbooks/sqlite-backup-and-litestream.md` (create)
- `docs/reports/P0-I7/P0-I7-T08.md` (create: your report; commit it)

## Acceptance
```
just check
test -s docs/runbooks/sqlite-backup-and-litestream.md
```
Expected: `just check` clean. Then check yourself, and say so in the report, that every fenced command appears in *Facts* and that each *Must cover* item has a section or step.

## Tests to add
None (documentation).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T08.md` and committed. List under *Open questions* anything in the facts that looked inconsistent.

## Escalation triggers
- Stop and report *Blocked* if the facts contradict each other or a step would need a command that is not listed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
