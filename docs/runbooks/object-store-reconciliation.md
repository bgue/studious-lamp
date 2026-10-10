# Runbook — object-store reconciliation (missing or corrupt objects)

Purpose: find files whose bytes are missing or damaged in the object store, and decide what to restore, by comparing the hashes the ledger references with the store. Brief: §24.5 ("Missing or corrupt objects"), §5.2, §20.

## When to use
- Trigger: `tl file get` fails with "does not match its recorded SHA-256", or an API download answers `object missing` (HTTP 503).
- Trigger: after restoring the ledger or the store from a backup, or on a schedule (weekly, `--verify` monthly).
- Trigger: before deleting anything under the object root or bucket, to see what is unreferenced.

## Before you start
- Access needed: read access to the ledger (`TL_DB`) and the object store (`TL_OBJECT_ROOT` for the `fs` backend; the bucket and AWS credentials for `s3`). The command is read-only and never repairs.
- Configuration: the same environment the service runs with. `TL_OBJECT_SECRET` must be set, or `TL_ENV=dev` in a development shell (the store factory fails closed without one; `just` exports `TL_ENV=dev`). `TL_OBJECT_STORE=s3` also needs `TL_S3_BUCKET` and, for MinIO, `TL_S3_ENDPOINT`.
- Safe to run during business hours: yes without `--verify`. `--verify` reads every object, so on a large store run it off-peak.

## Steps
1. Check that every referenced hash has an object (cheap):
   ```
   uv run tl file reconcile
   ```
   Expected output (clean): `checked <n>`, `verified false`, `missing 0`, `corrupt 0`, `orphans <k>`, `staging <m>`, exit code 0.
2. Find damaged bytes (reads everything):
   ```
   uv run tl file reconcile --verify
   ```
   Each problem is a line `missing <sha256> files=<file ids>` or `corrupt <sha256> files=<file ids> <detail>`; the exit code is 1 when there is any.
3. For each problem, find what it belongs to, then restore the object:
   ```
   uv run tl file ls --project P123 --record <record key> --all
   ```
   - **Restore from the replica or object versions** (preferred): copy the object back to its key `sha256/<aa>/<bb>/<sha256>` (`aa`, `bb` are the first two and next two hex digits). For `s3`, restore the previous version of the key or copy it from the replica bucket. For `fs`, copy the file from the backup of `TL_OBJECT_ROOT`. Run step 2 again.
   - **Re-upload the original** when you hold the bytes: `uv run tl file put <path> --project P123 --record <key> --slot <slot>`. The upload service writes the object again when the store lacks it (the ledger already has the file row, so the command reports `already attached` and the object is restored).
   - **Nothing to restore from:** the bytes are lost. The ledger rows stay (history is never rewritten). Void or supersede the file by attaching a replacement to the slot, and record the loss in the incident notes. A `corrupt` object must first be moved aside (`fs`: rename the file; `s3`: keep the bad version) so that a restore or re-upload can write the correct bytes: an existing content key is never overwritten by the store.
4. Orphans (`orphan <key>` lines, counted as `orphans`): content keys that no ledger row references. A rolled-back upload leaves one; it is harmless. Delete them only after the retention period and after a second run confirms they are still unreferenced.
5. Staging keys (`staging <m>`): leftovers of presigned uploads. They hold unverified client bytes and are never served. Remove keys older than a day with a bucket lifecycle rule on the `staging/` prefix (`s3`), or `find "$TL_OBJECT_ROOT/staging" -type f -mtime +1 -delete` (`fs`).

## Verify
- `uv run tl file reconcile --verify` exits 0 and prints `missing 0` and `corrupt 0`.
- `uv run tl file get <file id> --project P123 --out /tmp/check.bin` writes the file and prints its `sha256`; the command compares the bytes with the ledger's hash itself and fails when they differ.

## Roll back
- The reconciliation never writes. A restore step only adds an object at a key that was missing or that you moved aside, so undoing it means removing that object again; no ledger event is involved.

## Related
- `docs/memory/LEARNINGS.md` L-P0-I4-B4 (the object store has no delete or list in its Protocol), `docs/tickets/P0-I4/README-B.md` D7, D11.
- `docs/runbooks/rebuild-projections.md` (`cur_files` is a projection; rebuilding it does not touch the store).
- ADR-0002 (`fs` and `s3` backends).
