# Runbook — restore a database from the ledger archive

Purpose: rebuild a SQLite or Postgres database from the signed ledger archive alone, so the ledger and its projections come back after total database loss. Brief: §24.4, §24.2, fanout D1.

## When to use
- Trigger: total database loss, with the ledger archive still available. This is the last resort for rebuilding the database.
- Trigger: building a new environment that must start from the archived ledger.
- Trigger: proving that the archive can rebuild a working database (a drill).

Only events up to the archive's last sealed segment come back. Read "What is lost" before you start.

## Before you start
- Access needed: read access to the archive directory, read access to the public key, and write access to the new target path (SQLite) or to an empty Postgres database.
- Keep a copy of the public key apart from the archive. If an attacker can replace the archive, they can also replace a public key stored next to it.
- Know the values recorded when the archive was sealed: the last `seq` and the manifest `sha256`. See `docs/runbooks/ledger-archive-and-verify.md`.
- The target must be empty. Use a new SQLite file (its directory is created) or an empty Postgres database or schema. Never restore into the shared parity-test database `tl_test`.
- Use the same schema packages the ledger used. Promoted pset columns of `cur_core_record` come from the schema packages in force at restore time, not from events.
- Safe to run during business hours: no. The restore itself writes only to the empty target and touches neither the archive nor any other database, but the point of a restore is the cut-over (below), which stops writes to the old database and restarts services. Plan a window. Practising a restore into a scratch target is safe at any time.
- Production key custody, retention classes and object lock are not built. They are human follow-ups.

## Steps
1. Check the archive first, with the values recorded at seal time. Replace `18` and the manifest hash with those values:
   ```
   uv run tl archive verify --archive /path/to/archive --public-key /path/to/archive-signing.pub --expect-last-seq 18 --expect-manifest <sha256 recorded at seal time>
   ```
   Expected: `verified 2 segments, seq 1..18 (18 events)`. If the archive does not verify, stop here. See "If the restore refuses" below.

2. Set the schema directory the ledger used. `schema/fixtures` is the default:
   ```
   export TL_SCHEMA_DIR=schema/fixtures
   ```
   Expected: the shell prints nothing.

3. Restore into a new SQLite file. Run this from the repository root:
   ```
   uv run tl restore --from-archive /path/to/archive --db /path/to/new.db --public-key /path/to/archive-signing.pub
   ```
   Expected:
   ```
   restored 18 events from 2 segments into /path/to/new.db (last seq 18)
   verify 0.01s, insert 0.02s, rebuild 0.01s, total 0.06s
   ```
   Any warning lines go to stderr after these two lines. See "Warnings" below.

4. Restore into Postgres. First create an empty database. The `cd /tmp` lets the `postgres` user read its working directory:
   ```
   cd /tmp && sudo -u postgres createdb tl_restored
   ```
   Expected: no output on success.

   Then change back to the repository root, because the command above leaves the shell in `/tmp`. Run the restore from there:
   ```
   uv run tl restore --from-archive /path/to/archive --db postgresql://postgres:postgres@localhost:5432/tl_restored --public-key /path/to/archive-signing.pub
   ```
   Expected (the password is hidden in the output):
   ```
   restored 18 events from 2 segments into postgresql://postgres:***@localhost:5432/tl_restored (last seq 18)
   verify 0.02s, insert 0.37s, rebuild 0.12s, total 0.52s
   ```
   The URL above is the local dev default. Do not put a real password in a command or a document.

   To keep several ledgers in one Postgres database, use a schema-scoped URL. See `docs/runbooks/postgres-local-setup.md`.

### What the restore does
The command runs these steps in order:
1. Verifies the archive. If it does not verify, it stops at the first divergence and creates nothing.
2. Loads the effective schema of every scope in the archive. If one cannot be loaded, it stops before it writes anything.
3. Creates the tables.
4. In one transaction: inserts the archived events verbatim (`seq`, ids, times and hashes unchanged), adds the promoted columns, replays the events into the projections, and verifies the result against the archive. Then it commits.

If any step fails, the transaction rolls back. The database is left with empty tables. The same command can then be run again.

## If the restore refuses
Every refusal exits with code 1 and prints `error: ...` on stderr.

- **The archive does not verify.** The command also prints the first divergence on stdout and creates nothing. For example:
  ```
  divergence: file_hash segment=000000000011-000000000018 seq=11: events.ndjson differs from its hash
  error: the archive does not verify: file_hash in segment 000000000011-000000000018 at seq 11: events.ndjson differs from its hash
  ```
  Go to `docs/runbooks/ledger-archive-and-verify.md`. Do not restore from a copy that does not verify.

- **A scope's schema cannot be loaded.** Expected text: `error: cannot load the effective schema of scope '<scope>' to add promoted columns: ...; nothing was written`. Check the schema directory (`TL_SCHEMA_DIR`). Nothing was written.

- **The target already has events.** Expected text: `error: the events table is not empty; restore only into an empty database`. To start over, delete the SQLite file, or drop the Postgres database:
  ```
  cd /tmp && sudo -u postgres dropdb tl_restored
  ```
  Then run the restore again from step 3 or step 4.

- **The archive directory is missing.** Expected text: `error: no archive at ...`. Check the `--from-archive` path or `TL_ARCHIVE_DIR`.

- **The public key cannot be read.** Expected text: `error: cannot read the public key ...`. Check the `--public-key` path or `TL_ARCHIVE_PUBLIC_KEY`. The default key path is `dev/data/archive-signing.pub`.

## Warnings
Warnings go to stderr after the two summary lines. They do not change the exit code. Two kinds exist. The webhook ones are described under "What is lost". This one means the schema packages in force now differ from the ledger's:
```
warning: scope <scope>: the ledger last recorded effective schema <hash12>, the schema packages in force now give <hash12>; promoted columns may differ from the original (restore with the TL_SCHEMA_DIR the ledger used)
```
Fix the schema directory and restore again into a fresh database.

## Verify
Run both commands on the restored database. Both must exit 0. The examples use a SQLite file; for the Postgres database created in step 4 pass its URL to `--db` instead.

1. Check the ledger hash chains:
   ```
   uv run tl ledger verify --db /path/to/new.db
   ```
   Expected: `verified ledger /path/to/new.db: 18 events, hash chains intact`

2. Check the archive against the restored database:
   ```
   uv run tl archive verify --archive /path/to/archive --public-key /path/to/archive-signing.pub --db /path/to/new.db --deep
   ```
   Expected:
   ```
   verified 2 segments, seq 1..18 (18 events)
   database /path/to/new.db agrees up to seq 18
   ```

Postgres variants (the password is hidden in the output):
```
uv run tl ledger verify --db postgresql://postgres:postgres@localhost:5432/tl_restored
uv run tl archive verify --archive /path/to/archive --public-key /path/to/archive-signing.pub --db postgresql://postgres:postgres@localhost:5432/tl_restored --deep
```
Expected:
```
verified ledger postgresql://postgres:***@localhost:5432/tl_restored: 18 events, hash chains intact
verified 2 segments, seq 1..18 (18 events)
database postgresql://postgres:***@localhost:5432/tl_restored agrees up to seq 18
```

## What is lost
- Only events up to the archive's last `seq` come back. Events written after the last sealed segment are gone. That gap is the archive recovery point: seal often.
- Record files are in the object store, not in the archive. Reconcile them after the restore:
  ```
  uv run tl file reconcile
  ```
  For the output and what to do with missing files, see `docs/runbooks/object-store-reconciliation.md`.
- Webhook subscriptions come back with status `active`, because they are rebuilt from their events. A signing secret is never in the ledger, and delivery state is not restored. A subscription without a secret sends nothing: the worker keeps its deliveries pending (none are sent unsigned or dead-lettered) and logs one warning per subscription per cycle, and `tl webhook ls` shows it as `needs_secret`. The restore prints one `warning: webhook subscription ...` line per subscription, then a line saying the dispatcher starts again from seq 0, so events since each subscription was created are queued and are sent once its secret exists (receivers dedupe on the event id). To release them:
  1. List the subscriptions (`needs_secret` in the second column):
     ```
     uv run tl webhook ls
     ```
  2. Rotate the secret of each subscription. Replace the subscription id:
     ```
     uv run tl webhook rotate-secret <subscription id> --project P123 --overlap-hours 24
     ```
  3. Give each receiver its new secret. The pending deliveries are then sent signed.

  The `tl webhook` and `tl file` commands take a SQLite file (`--db`) in this phase, not a Postgres URL.

  See `docs/runbooks/webhook-operations.md`.

## Cut over
1. Run the verify commands above and confirm both exit 0.
2. Point the services at the new database. For SQLite set `TL_DB` to the new file. For Postgres use the URL in the service's configuration (the parity tests and drills read it from `TL_PG_URL`); the URL printed above has its password hidden, so take the real one from your own configuration.
3. Stop the services that write to the old database, then restart them against the new one. Events written to the old database after the archive's last seq are not in the new one.
4. New events continue at seq max+1, with the hash chain intact.

## Roll back
- The restore writes only to the empty target. To undo it, delete the SQLite file at the `--db` path, or drop the Postgres database (see "If the restore refuses").
- The archive and any other database are untouched by the restore.

## Related
- `docs/runbooks/ledger-archive-and-verify.md` (sealing, verifying and the first divergence).
- `docs/runbooks/pgbackrest-restore.md` (Postgres point-in-time recovery, checked against the archive).
- `docs/runbooks/sqlite-backup-and-litestream.md` (SQLite backup and continuous replication).
- `docs/runbooks/rebuild-projections.md` (rebuilding projections from the ledger).
- `docs/runbooks/object-store-reconciliation.md` (record files after a restore).
- `docs/runbooks/postgres-local-setup.md` (local Postgres and schema-scoped URLs).
- `docs/runbooks/webhook-operations.md` (subscriptions and secret rotation).
