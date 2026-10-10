# Runbook — SQLite snapshots and Litestream for the dev ledger

Purpose: protect the dev SQLite ledger with snapshots and continuous replication, and restore either one. Brief: §24.3.

Run every command from the repository root. The paths below are relative to that root.

## When to use
- Trigger: you want a copy of the dev ledger before risky work. Take a snapshot.
- Trigger: a bad write reached the dev ledger. Restore a snapshot or a Litestream replica, then check it.
- Trigger: the dev ledger file is lost. Restore the Litestream replica into a new file.
- Limit: a snapshot holds only the events written before it was taken. Its RPO is the interval between snapshots.
- Limit: Litestream replicates the dev ledger with a sync interval of 1 s. It is a dev tool.
- Limit: production database backup is pgBackRest, not Litestream. See `docs/runbooks/pgbackrest-restore.md`.
- Limit: production key custody, retention classes and object lock are not built. They are human follow-ups.
- Limit: the ledger archive is the database-independent restore path. See `docs/runbooks/restore-from-archive.md`.

## Before you start
- Access needed: a checkout of this repository with its Python environment installed. Outbound HTTPS to GitHub is needed once, for the Litestream fetch.
- Safe to run during business hours: yes for a snapshot, which is taken while the ledger is in use. Dev only. Do not copy a file over the ledger while anything writes to it.

## Steps

### Snapshot
1. Take a snapshot of the ledger into a new file.
   ```
   uv run tl backup sqlite --to dev/data/backups/tl-snap.db
   ```
   Expected: a line of this shape, with the event count, the file size and the sha256 of the snapshot.
   ```
   backed up 18 events from dev/data/tl.db to dev/data/backups/tl-snap.db (258048 bytes, sha256 349752d3e816147c1d38a539b5a19302ffcee9ec91fbb17dc2bdf071e8793501)
   ```
   The snapshot is one self-contained file. It is taken while the ledger is in use. Its directory is created. The file is read-only.
2. Record the sha256 from the output, next to the snapshot file name.
3. If the snapshot fails, read the error and choose again.
   - `error: destination exists: <path>` (exit 1). Choose a new file name.
   - `error: source database not found: <path>`. Check that the ledger exists at the source path.
   - `error: filesystem does not support hard links; choose another destination (...)`. Choose another destination directory.
   Nothing is left behind after an error.

### Restore a snapshot
1. Stop every process that writes to `dev/data/tl.db` (the TUI, the webhook worker, `tl` commands). Events written after the snapshot are lost when you restore it.
2. Copy the snapshot over the ledger and make the copy writable.
   ```
   cp dev/data/backups/tl-snap.db dev/data/tl.db && chmod 644 dev/data/tl.db
   ```
   Expected: no error message.
3. Verify the restored ledger.
   ```
   uv run tl ledger verify
   ```
   Expected: `verified ledger dev/data/tl.db: 18 events, hash chains intact`

### Fetch Litestream (once)
1. Fetch the pinned Litestream v0.3.13 release into the git-ignored `dev/data/tools/`.
   ```
   bash dev/drills/fetch_litestream.sh
   ```
   Expected: `Litestream v0.3.13 is in dev/data/tools/litestream`, or no output if the binary is already there.
2. If the download fails, do not retry in a loop. The script makes one attempt and checks the checksum. A proxy can refuse the host. Use snapshots and the ledger archive instead (`docs/runbooks/restore-from-archive.md`).

### Run Litestream
1. In a shell, set the ledger path and the replica directory, then start replication in the foreground.
   ```
   export TL_DB=dev/data/tl.db LITESTREAM_REPLICA=dev/data/litestream
   dev/data/tools/litestream replicate -config dev/backup/litestream.yml
   ```
   Expected: the command stays in the foreground. Leave it running. The replica trails the ledger by about one second plus the write time.
2. Use a second shell for the other commands in this runbook. The ledger is in WAL mode; the ledger engine sets it.
3. To stop replication, stop the foreground process. Stopping Litestream changes nothing in the ledger.

### Restore the Litestream replica into a new file
Use this after the ledger file is lost. It writes a new file and leaves `dev/data/tl.db` alone.
1. In the shell where `TL_DB` is set, restore the replica into `dev/data/restored.db`.
   ```
   dev/data/tools/litestream restore -config dev/backup/litestream.yml -o dev/data/restored.db "$TL_DB"
   ```
   Expected: the restore log ends with `renaming database from temporary location`.
2. Verify the restored file.
   ```
   uv run tl ledger verify --db dev/data/restored.db
   ```
   Expected: `verified ledger dev/data/restored.db: <n> events, hash chains intact`.

### Compare with the archive
1. Compare the ledger with the ledger archive.
   ```
   uv run tl archive verify --db dev/data/tl.db --deep
   ```
   Expected: the output described in `docs/runbooks/ledger-archive-and-verify.md`.

## Verify
- A snapshot is good when its sha256 matches the value you recorded at the snapshot step.
- A snapshot's file can be checked against its recorded hash with `sha256sum dev/data/backups/tl-snap.db`.
- A restored snapshot is good when `uv run tl ledger verify` prints `verified ledger dev/data/tl.db: <n> events, hash chains intact`, with the event count you expect.
- A Litestream restore is good when the restore log ends with `renaming database from temporary location` and `uv run tl ledger verify --db dev/data/restored.db` prints a verified line.
- The ledger and the archive agree when `uv run tl archive verify --db dev/data/tl.db --deep` reports success, as described in `docs/runbooks/ledger-archive-and-verify.md`.
- The drill measures RPO and RTO for all the paths: `just drill`. See `docs/runbooks/pgbackrest-restore.md` and `docs/templates/restore-drill.md`.

## Roll back
- A snapshot file and a restored file are new files. Delete them to roll back (snapshots are read-only, which `rm` still removes):
  ```
  rm dev/data/backups/tl-snap.db dev/data/restored.db
  ```
- To stop replication, stop the foreground Litestream process. The ledger is not changed.
- A snapshot restore that copied over `dev/data/tl.db` replaces the ledger. Events written after the snapshot are lost.

## Related
- `docs/runbooks/ledger-archive-and-verify.md` — archive verification, including `--deep`.
- `docs/runbooks/restore-from-archive.md` — the database-independent restore path.
- `docs/runbooks/pgbackrest-restore.md` — production database backup and restore.
- `docs/templates/restore-drill.md` — the drill report template, run with `just drill`.
- `dev/backup/litestream.yml` — the Litestream configuration.
- `dev/drills/fetch_litestream.sh` — the pinned Litestream fetch.
- Brief §24.3; ADR-0002 (Litestream and pgBackRest are configured but not required locally).
