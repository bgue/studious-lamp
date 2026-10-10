# Runbook — seal and verify the ledger archive

Purpose: seal the ledger into signed archive segments kept apart from the database, then verify the archive and the database so that edits, removed segments and loss are found, and the first divergence is read. Brief: §24.3, §24.5, §24.6.

## When to use
- Trigger: scheduled sealing. In dev, seal hourly (step 2 of Steps).
- Trigger: after an incident that touched the database or the archive directory.
- Trigger: a tampering suspicion, or a `divergence:` line from a verify run (see Verify).
- Trigger: a refused seal (`error: ...`, exit 1; see Steps).

## Before you start
- Run every command from the repository root, with `uv run`. The `UV_NATIVE_TLS is deprecated` warning from uv is harmless.
- Access needed:
  - write access to the archive directory: `./dev/data/archive` by default, or `--archive` / `TL_ARCHIVE_DIR`;
  - write access to the private key `dev/data/archive-signing.key` (mode 0600, git-ignored), or `--key` / `TL_ARCHIVE_KEY`;
  - read access to the public key `dev/data/archive-signing.pub` (hex), or `--public-key` / `TL_ARCHIVE_PUBLIC_KEY`;
  - read access to the ledger: the root `--db` / `TL_DB` (default `./dev/data/tl.db`), or `--db TARGET` for a SQLite file or a `postgresql://` URL. Pass a URL with `--db`; do not paste credentials into tickets;
  - a place the archive store cannot write, for the recorded seal line (a ticket or a vault note).
- Safe to run during business hours: not established for production. In dev the sealing commands are run hourly; whether sealing blocks writers is not stated (see open questions in the report).
- Not built: production key custody (KMS, HSM), retention classes and object lock. These are later human decisions. Until they are made, the key is a file on disk and the archive is not object-locked.

## Steps
1. Create the signing key once. The command refuses to replace an existing key.
   ```
   uv run tl archive keygen --key dev/data/archive-signing.key
   ```
   Expected: `wrote private key dev/data/archive-signing.key (key id <16 hex>)` and `wrote public key dev/data/archive-signing.pub`. The key id is printed; yours will differ.
   `--force` replaces the key. Use it only on purpose: older segments then no longer verify with the new public key (see Roll back).

2. Seal everything not yet archived. Run it as often as the recovery point objective needs; in dev, hourly.
   ```
   uv run tl archive seal
   ```
   Expected, when new events exist: one `sealed segment <first>-<last> (<n> events, seq <first>..<last>)` line per new segment, then `sealed <n> segments; archive is at seq <N>`, then the record line (step 3).
   Example output: `sealed segment 000000000001-000000000010 (10 events, seq 1..10)`, `sealed segment 000000000011-000000000018 (8 events, seq 11..18)`, `sealed 2 segments; archive is at seq 18`.
   Several segments are written when more than `--max-events` (default 10000) events are new.
   Each segment is a directory `segments/<first_seq>-<last_seq>/` in the archive directory, holding `events.ndjson`, `events.parquet` and `manifest.json`. All three are read-only. The store never overwrites a file.
   When nothing is new, the output is `nothing new to seal; archive is at seq <N>` followed by the same record line.

3. Record the last seq and the manifest hash outside the archive. Copy the line `record outside the archive: last_seq <N> manifest_sha256 <64 hex>` from step 2 into a place the archive store cannot write (a ticket or a vault note). Example: `record outside the archive: last_seq 18 manifest_sha256 dab83c9a325152d42d82b9c2937e5fcdc97b0f807b9d974f0528c12dcbdb99c2`.
   Nothing inside an archive shows that whole trailing segments were removed. The recorded values are what let verify (step 2 of Verify) detect that.

### If a seal is refused
Sealing stops with `error: ...` and exit 1 when:
- the database has diverged from what is sealed (`the database has diverged from what is sealed: scope ...`);
- the database is behind the archive (`the database head (N) is behind the last sealed seq (M)`);
- a leftover file differs from what the ledger yields;
- the chain is structurally broken.

Do not delete anything to get past the refusal. Run the verify steps below (archive alone, archive with database, database alone) and read the first divergence. Stop sealing until the cause is known; write the question in the ticket.

### Crash safety
A segment is written in the order `events.ndjson`, `events.parquet`, `manifest.json`. The manifest is the commit marker. A directory without a manifest is unsealed. The next `uv run tl archive seal` seals exactly the same seq range, even if newer events arrived. Run it again. The re-run records a new `sealed_at`; that is expected.

## Verify
1. Verify the archive alone: signatures, manifest chain, gap-free seq, every event hash, and every scope's hash chain.
   ```
   uv run tl archive verify
   ```
   Expected: `verified 2 segments, seq 1..18 (18 events)` (the example archive; yours shows its own counts).

2. Verify the archive against the values recorded in step 3 of Steps. A longer archive is fine.
   ```
   uv run tl archive verify --expect-last-seq 18 --expect-manifest dab83c9a325152d42d82b9c2937e5fcdc97b0f807b9d974f0528c12dcbdb99c2
   ```
   Expected: the normal success line, if the archive reaches at least seq 18 with that manifest still in its chain.
   If the archive is shorter, the output is one divergence line and exit 1. Example, for a record that says the archive reached seq 99: `divergence: seq_gap segment=- seq=19: the archive ends at seq 18 but the record says it reached 99: trailing segments are missing`.

3. Verify the archive against the database. This also checks that the database agrees up to the last sealed seq.
   ```
   uv run tl archive verify --db dev/data/tl.db --deep
   ```
   Expected: `verified 2 segments, seq 1..18 (18 events)` then `database dev/data/tl.db agrees up to seq 18`.
   `--deep` also checks each Parquet file against its NDJSON. For the database it recomputes every event hash from its stored fields, compares every field with the archive, and checks the events newer than the archive.
   Without `--deep`, only the stored hash columns are compared. That catches fewer edits: a payload-only edit passes. Use `--deep` when tampering is suspected.

4. Verify the database alone, without any archive: gap-free seq, hashes recomputed, per-scope chains.
   ```
   uv run tl ledger verify
   ```
   Expected: `verified ledger dev/data/tl.db: 18 events, hash chains intact`.

### Reading a divergence
A divergence prints one line per issue and exits 1. Only the first line is shown, unless `--all` is passed; then there is one line per broken segment. Read the first line first.

Format: `divergence: <kind> segment=<directory or -> seq=<number or ->: <detail>`

Example: `divergence: file_hash segment=000000000011-000000000018 seq=11: events.ndjson differs from its hash`

| kind | meaning | first thing to do |
|---|---|---|
| `missing_file` | a segment lacks one of its three files | restore the file from a copy of the archive |
| `file_hash` | a file differs from the hash in its signed manifest (or Parquet differs from NDJSON with `--deep`) | compare with a copy; treat as tampering or storage corruption |
| `signature` | the manifest is unsigned, unreadable, signed by another key, or edited | check you hold the right public key; then treat as tampering |
| `manifest_chain` | `prev_manifest_sha256` does not match, the directory does not match its manifest, or a recorded manifest is missing from the chain | a segment was removed, replaced or reordered |
| `seq_gap` | seq is not gap-free, or the archive ends before the recorded last seq | a segment or event is missing |
| `event_hash` | an event's hash does not match its fields (in the archive, or in the database with `--deep` or `tl ledger verify`) | the event was edited |
| `scope_chain` | a scope's `prev_hash` chain is broken, or the manifest's scope summary is wrong | an event was removed, inserted or reordered |
| `db_mismatch` | the database has a different row, or none, where the archive has an event | the database or the archive diverged; decide which copy is true by the other copies |

### Limits
- Sealing checks the database against the archive at each scope's newest sealed event. It does not check the middle of history. Full detection is the deep archive verify (step 3 above) or the database verify (step 4 above). The restore drill runs both.
- Fields added to a manifest are not covered by that manifest's own signature. They are covered by the next manifest's chain hash, so adding a field to any manifest except the newest breaks the chain.

## Roll back
- Nothing to undo. Segments are never deleted or rewritten, and sealing and verifying do not change the ledger.
- Replacing the key with `--force` makes older segments fail to verify with the new public key. Keep the old key pair with the old archive.
- To start a fresh archive (for example after replacing the key), use a new archive directory and keep the old one.

## Related
- `docs/runbooks/rebuild-projections.md` (rebuild the current-state tables from the ledger).
- Named in the build spec but not yet in `docs/runbooks/`: `restore-from-archive.md`, `sqlite-backup-and-litestream.md`, `pgbackrest-restore.md`.
- Brief §24.3 (ledger archive), §24.5 (tampering suspicion), §24.6 (runbooks).
