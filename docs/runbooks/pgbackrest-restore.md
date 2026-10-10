# Runbook — pgBackRest backup and restore for Postgres

Purpose: back up the Postgres ledger with pgBackRest, restore it after a loss, and verify the result against the ledger archive. Brief: §24.3, §24.4.

Practise with the drill first. The drill creates its own scratch cluster and removes it when it ends.

Warning: never run these commands against the shared development cluster on port 5432 or its `tl_test` database. The drill does not check its target. It only ever touches cluster `16/drill`.

## When to use
- Trigger: loss or corruption of the Postgres ledger cluster, and the Postgres data directory must be rebuilt.
- Trigger: the quarterly restore drill.
- Trigger: after a Postgres upgrade or a pgBackRest upgrade, to confirm backup and restore still work.

## Before you start
- Access needed: sudo on the database host. The commands run as the `postgres` operating-system user with `sudo -u postgres`.
- Software: the apt package `pgbackrest` (pgBackRest 2.50, MIT). If it is missing, run `sudo apt-get install -y pgbackrest`. The drill also needs the PostgreSQL 16 server packages.
- Config: the template is `dev/backup/pgbackrest.conf.tmpl`. It has three placeholders: `@ROOT@`, `@PGDATA@` and `@PORT@`. The drill fills them in with `sed` and writes the result to the config file, which the commands below call `$CONF`. In the drill, `$CONF` is `/var/lib/postgresql/tl-drill/pgbackrest.conf`. Set `CONF` in your shell to your own config file before you run the commands that use `"$CONF"`.
- Stanza: the commands use the stanza name `drill`. Substitute your own stanza name and cluster name on a real cluster. Step 2 creates the stanza.
- Production repository settings (encrypted S3 repository, cipher, keys) are commented out in the template. They need real keys and a bucket, and they are not configured by this repository.
- Safe to run during business hours: no, for steps 1, 3 and 5 on a live cluster. Step 5 stops the cluster. The drill is safe at any time because it uses its own cluster on port 5440.

## The safe way to practise: the drill
Run this from the repository root. It needs sudo.
```
bash dev/drills/pgbackrest.sh --records 60 --tail 10
```
Expected: progress lines go to stderr. Stdout has tab-separated `pgbackrest_*` lines. The last stdout line is `pgbackrest_status` followed by a tab and `pass`.

The drill does this in order:
1. Removes a leftover `16/drill` cluster from an earlier run, if there is one.
2. Creates cluster `16/drill` on port 5440 with WAL archiving into a pgBackRest repository.
3. Populates a ledger, takes a full backup, and writes more events.
4. Erases the data directory, restores with pgBackRest, and verifies the result against the ledger archive.
5. Prints the measured numbers, and drops the cluster and its files when it ends, even if a step fails.

The full drill covers all backup layers and writes a report. Run it with `just drill`, which runs `bash dev/drills/restore.sh` and fills `docs/templates/restore-drill.md`.

## Steps
These steps are the drill's procedure. Commands are run from the repository root unless a step says otherwise.

1. Turn on WAL archiving. Run this once per cluster. The drill does it when it creates the cluster.
   ```
   sudo pg_conftool 16 drill set archive_mode on
   sudo pg_conftool 16 drill set archive_timeout 15s
   sudo pg_conftool 16 drill set archive_command "pgbackrest --config=$CONF --stanza=drill archive-push %p"
   ```
   Expected: the three settings are written to `postgresql.conf` with no error.

   Then restart the cluster, because `archive_mode` only takes effect after a restart. The facts list no graceful restart command, so this uses the stop and start commands below. Do this in a window with no writes, because the stop is immediate.
   ```
   sudo pg_ctlcluster 16 drill stop -m immediate
   sudo pg_ctlcluster 16 drill start
   ```
   Expected: the cluster starts with no error. `archive_timeout` forces a WAL switch after 15 seconds without one, so it limits how many recent events can be lost.

2. Create the stanza and check the archive path, as the `postgres` user.
   ```
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill stanza-create
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill check
   ```
   Expected: both commands finish with no error.

3. Take a full backup. Production runs a weekly full backup and a daily incremental backup (§24.3). This repository does not schedule either.
   ```
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill backup --type=full
   ```
   Expected: the output ends with `new backup label = <timestamp>F`, a line starting `full backup size = `, and `backup command end: completed successfully`. The `F` at the end of the label marks a full backup.

4. Force a recovery point now, when you need one. Run this SQL in a PostgreSQL client connected to the cluster. In the drill the URL is `postgresql://postgres:drill@localhost:5440/tl_drill`.
   ```
   SELECT pg_switch_wal()
   ```
   Expected: the statement returns a log sequence number. WAL that is not yet archived when the machine is lost is lost. `archive_timeout` bounds how long that can be.

5. After a loss, stop the cluster, empty its data directory, restore, start it, and wait for recovery to finish. The `find` command deletes everything under the data directory. Check that the path is the cluster's own data directory (`/var/lib/postgresql/16/drill` in the drill) before you run it.
   ```
   sudo pg_ctlcluster 16 drill stop -m immediate
   sudo find /var/lib/postgresql/16/drill -mindepth 1 -delete
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill restore
   sudo pg_ctlcluster 16 drill start
   ```
   Expected: the restore output includes `restore backup set <label>` and `restore command end: completed successfully`.

   Then run this SQL in a PostgreSQL client connected to the restored cluster. Repeat it until it returns `f`.
   ```
   SELECT pg_is_in_recovery()
   ```
   Expected: `f`. Recovery has finished. By default, pgBackRest recovers to the end of the archived WAL. Point-in-time recovery (`--type=time --target=...`) is a pgBackRest option that the drill does not exercise.

6. Verify the restored database against the ledger archive. Use the cluster's own URL. The drill's URL is shown; do not write a real password into a runbook.
   ```
   uv run tl ledger verify --db postgresql://postgres:drill@localhost:5440/tl_drill
   uv run tl archive verify --archive /path/to/archive --public-key /path/to/archive-signing.pub --db postgresql://postgres:drill@localhost:5440/tl_drill --deep
   ```
   Expected: `hash chains intact`, and `database ... agrees up to seq N`. N is the archive's last seq. Events newer than the archive are chain-checked too.

## Verify
- `SELECT pg_is_in_recovery()` returns `f` (step 5).
- `ledger verify` reports `hash chains intact` (step 6).
- `archive verify --deep` reports that the database agrees up to the archive's last seq (step 6).
- Events written after the last archived WAL switch are not in the restored database. The drill reports that count as `pgbackrest_rpo_events`.

## Measured numbers (one dev run, small dataset)
This is one dev run on 2026-10-10 with 30 records and 5 events per tail. It is not a benchmark, and it did not use the 60 records and 10 events per tail shown in the drill command above.
- Full backup: 3.2 s.
- Restore command: 1.1 s.
- RTO: 13.9 s. The drill starts this timer when it erases the data directory. It stops the timer after the restore, the cluster start, the recovery wait, `ledger verify` and `archive verify`.
- Recovered: 50 of 55 events. The 5 events written after the last WAL switch were lost. `archive_timeout` was 15 s.

The brief sets production targets of RPO at most 5 minutes and RTO at most 1 hour for a single-database failover (§24.3). One small dev run does not show that production meets them.

## What the drill does not exercise
- Point-in-time recovery (`--type=time --target=...`).
- Incremental and differential backups (`--type=incr`, `--type=diff`).
- The encrypted S3 repository. It is commented out in the template, and it needs keys and a bucket.
- Production key custody, retention classes and object lock are not built. They are human follow-ups.

## Roll back
- A failed restore leaves the data directory half written. Empty it with the `find` command in step 5, then run the restore again.
- A restore never modifies the repository (`repo1-path`).
- If an interrupted drill leaves cluster `16/drill` behind, the next drill run removes it. To remove it by hand, first check with `pg_lsclusters`, then run `sudo pg_dropcluster 16 drill --stop`.
- The step 1 settings have no listed rollback. See the report's open questions.

## Related
- `docs/runbooks/postgres-local-setup.md` — local Postgres setup.
- `restore-from-archive.md` and `ledger-archive-and-verify.md` — added by P0-I7-T06 and P0-I7-T05. They are not on this branch yet. Step 6 follows the verify steps in `restore-from-archive.md`.
- `docs/templates/restore-drill.md` — the report that `just drill` fills.
- `dev/backup/pgbackrest.conf.tmpl` and `dev/drills/pgbackrest.sh` — the config template and the drill.
- Brief §24.3 (backup) and §24.4 (full disaster recovery).
