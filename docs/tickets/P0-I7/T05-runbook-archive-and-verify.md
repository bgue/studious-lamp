# P0-I7-T05 — Runbook: seal and verify the ledger archive

Status: ready
Tier: haiku
Labels: docs
Depends on: P0-I7-T01 to T04 and the drills (S12), merged into the base of this branch
Branch: `p0/i7a-t05-runbook-archive-and-verify`

## Goal
A runbook at `docs/runbooks/ledger-archive-and-verify.md` tells an operator how to create the signing key, seal the ledger into segments, record the last seq and manifest, verify the archive and the database, and read the first divergence.

## Brief references (pasted)
> **24.3 Ledger archive:** sealed segments every N minutes or M events: NDJSON + Parquet, with a signed hash manifest continuing the hash chain, written to an **independent** location (production: with object lock).
> A database-independent restore path. **24.5 Tampering suspicion:** hash-chain verification tool over the database and the archive. Reports the first divergence.
> **24.6:** every operational command, alert and recovery path has a runbook.

### Facts (all run by the supervisor on 2026-10-10; copy the commands and output shapes as written)
Defaults: archive directory `./dev/data/archive` (`--archive` or `TL_ARCHIVE_DIR`); private key `dev/data/archive-signing.key` (`--key` or `TL_ARCHIVE_KEY`), mode 0600, git-ignored, with the public key
as hex beside it (`dev/data/archive-signing.pub`; `--public-key` or `TL_ARCHIVE_PUBLIC_KEY`). The ledger is the root `--db` (`TL_DB`, default `./dev/data/tl.db`) or `--db TARGET` (a SQLite file or a `postgresql://` URL).
Production key custody (KMS, HSM), retention classes and object lock are later, human decisions and are not built. The archive directory is independent of the object store and of the database.

1. Create the key once (it refuses to replace one; `--force` replaces it, and then older segments no longer verify with the new public key):
   ```
   uv run tl archive keygen --key dev/data/archive-signing.key
   ```
   ```
   wrote private key dev/data/archive-signing.key (key id 4fbaab9366b76523)
   wrote public key dev/data/archive-signing.pub
   ```
2. Seal everything not yet archived (several segments if more than `--max-events`, default 10000, are new). Run it as often as the RPO needs (dev: hourly):
   ```
   uv run tl archive seal
   ```
   ```
   sealed segment 000000000001-000000000010 (10 events, seq 1..10)
   sealed segment 000000000011-000000000018 (8 events, seq 11..18)
   sealed 2 segments; archive is at seq 18
   record outside the archive: last_seq 18 manifest_sha256 dab83c9a325152d42d82b9c2937e5fcdc97b0f807b9d974f0528c12dcbdb99c2
   ```
   Nothing new prints `nothing new to seal; archive is at seq 18` and the same `record outside the archive` line. Each segment is a directory `segments/<first_seq>-<last_seq>/` with `events.ndjson`, `events.parquet` and `manifest.json`,
   all read-only. The store never overwrites a file. `events.parquet` has the ledger `events` column names, with payload and timestamps as the exact text that was hashed.
3. **Keep the `record outside the archive` line somewhere the archive store cannot write** (a ticket, a vault note). Nothing inside an archive can show that whole trailing segments were removed. Pass the recorded values back later:
   ```
   uv run tl archive verify --expect-last-seq 18 --expect-manifest dab83c9a325152d42d82b9c2937e5fcdc97b0f807b9d974f0528c12dcbdb99c2
   ```
   An archive that reaches at least that seq, with that manifest still in its chain, prints the normal success line; a longer archive is fine. A shorter one prints
   `divergence: seq_gap segment=- seq=19: the archive ends at seq 18 but the record says it reached 99: trailing segments are missing` (example with `--expect-last-seq 99`) and exits 1.
4. Verify the archive alone (signatures, manifest chain, gap-free seq, every event hash, every scope's hash chain):
   ```
   uv run tl archive verify
   ```
   ```
   verified 2 segments, seq 1..18 (18 events)
   ```
5. Verify the archive against a database (also checks the database agrees up to the last sealed seq). `--deep` additionally checks each Parquet file against its NDJSON and, for the database, recomputes every event hash from its stored fields,
   compares every field with the archive, and checks the events newer than the archive. Without `--deep` only the stored hash columns are compared, which catches fewer edits (a payload-only edit passes):
   ```
   uv run tl archive verify --db dev/data/tl.db --deep
   ```
   ```
   verified 2 segments, seq 1..18 (18 events)
   database dev/data/tl.db agrees up to seq 18
   ```
6. Verify the database alone, without any archive (gap-free seq, hashes recomputed, per-scope chains):
   ```
   uv run tl ledger verify
   ```
   ```
   verified ledger dev/data/tl.db: 18 events, hash chains intact
   ```
7. A divergence prints one line per issue and exits 1; only the first is shown unless `--all` (then one per broken segment):
   ```
   divergence: file_hash segment=000000000011-000000000018 seq=11: events.ndjson differs from its hash
   ```
   Format: `divergence: <kind> segment=<directory or -> seq=<number or ->: <detail>`.

   | kind | meaning | first thing to do |
   |---|---|---|
   | `missing_file` | a segment lacks one of its three files | restore the file from a copy of the archive |
   | `file_hash` | a file differs from the hash in its signed manifest (or Parquet differs from NDJSON with `--deep`) | compare with a copy; treat as tampering or storage corruption |
   | `signature` | the manifest is unsigned, unreadable, signed by another key, or edited | check you hold the right public key; then treat as tampering |
   | `manifest_chain` | `prev_manifest_sha256` does not match, the directory does not match its manifest, or a recorded manifest is missing from the chain | a segment was removed, replaced or reordered |
   | `seq_gap` | seq is not gap-free, or the archive ends before the recorded last seq | a segment or event is missing |
   | `event_hash` | an event's hash does not match its fields (in the archive, or in the database with `--deep` / `tl ledger verify`) | the event was edited |
   | `scope_chain` | a scope's `prev_hash` chain is broken, or the manifest's scope summary is wrong | an event was removed, inserted or reordered |
   | `db_mismatch` | the database has a different row, or none, where the archive has an event | the database or the archive diverged; decide which copy is true by the other copies |
8. Sealing refuses to continue from a broken state, with `error: ...` and exit 1: the database has diverged from what is sealed (`the database has diverged from what is sealed: scope ...`), the database is behind the archive
   (`the database head (N) is behind the last sealed seq (M)`), a leftover file differs from what the ledger yields, or the chain is structurally broken. Do not delete anything to get past it: verify first (steps 4 to 6).
9. A crash while sealing is safe. A segment is written in the order `events.ndjson`, `events.parquet`, `manifest.json`; the manifest is the commit marker. A directory without a manifest is unsealed, and the next `tl archive seal` seals exactly the same
   seq range, even if newer events arrived. Just run it again. (The re-run records a new `sealed_at`; that is expected.)
10. Limits to state plainly: sealing checks the database against the archive at each scope's newest sealed event, not in the middle of history; full detection is step 5 or 6, and the restore drill runs both. Fields added to a manifest are not covered by its own
    signature, but they are covered by the next manifest's chain hash, so adding one to any manifest except the newest breaks the chain.
11. Roll back: nothing to undo. Segments are never deleted or rewritten. To start a fresh archive (for example after replacing the key), use a new archive directory and keep the old one.

### Must cover
Purpose and when to use (hourly sealing in dev; after an incident; on a tampering suspicion); setup; seal; recording the last seq and manifest; verify (archive, with database, database only); the divergence table; what a refused seal means; crash safety;
the limits (step 10); roll back; related runbooks (`restore-from-archive.md`, `sqlite-backup-and-litestream.md`, `pgbackrest-restore.md`, `rebuild-projections.md`).

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
- `docs/runbooks/ledger-archive-and-verify.md` (create)
- `docs/reports/P0-I7/P0-I7-T05.md` (create: your report; commit it)

## Acceptance
```
just check
test -s docs/runbooks/ledger-archive-and-verify.md
```
Expected: `just check` clean. Then check yourself, and say so in the report, that every fenced command appears in *Facts* and that each *Must cover* item has a section or step.

## Tests to add
None (documentation).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T05.md` and committed. List under *Open questions* anything in the facts that looked inconsistent.

## Escalation triggers
- Stop and report *Blocked* if the facts contradict each other or a step would need a command that is not listed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
