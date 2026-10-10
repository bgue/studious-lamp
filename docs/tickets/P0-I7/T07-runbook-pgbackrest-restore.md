# P0-I7-T07 — Runbook: pgBackRest backup and restore for Postgres

Status: ready
Tier: haiku
Labels: docs
Depends on: P0-I7-T01 to T04 and the drills (S12), merged into the base of this branch
Branch: `p0/i7a-t07-runbook-pgbackrest-restore`

## Goal
A runbook at `docs/runbooks/pgbackrest-restore.md` tells an operator how pgBackRest is set up for the Postgres ledger, how to take a backup, how to restore after a loss, how to verify the result against the ledger archive, and how to practise it safely with the drill script.

## Brief references (pasted)
> **24.3 Backup, Database:** pgBackRest in production: weekly full, daily incremental, continuous WAL archive (**PITR**). Encrypted, to a separate account/region. Targets (prod): RPO <= 5 min for the database (WAL); RTO <= 1 h for a single-database failover.
> **24.4 Full disaster recovery:** restore Postgres via PITR, verify against the ledger archive (hash chain continuity, last `seq`), and reconcile against the object store.
> **Fanout D5:** pgBackRest and the drill run only against a scratch cluster or database created by the drill script. The shared `tl_test` database is never touched.

### Facts (all run by the supervisor on 2026-10-10 against a scratch cluster; copy the commands as written)
pgBackRest 2.50 (MIT) comes from apt: `sudo apt-get install -y pgbackrest`. The configuration template is `dev/backup/pgbackrest.conf.tmpl` (placeholders `@ROOT@`, `@PGDATA@`, `@PORT@`; the encrypted S3 repository settings for production are in it, commented out,
because they need real keys and a bucket). The drill `dev/drills/pgbackrest.sh` creates the cluster `16/drill` on port 5440, runs everything below, and drops the cluster and its files when it ends, whatever happens. It needs `sudo`:
```
bash dev/drills/pgbackrest.sh --records 60 --tail 10
```
It prints `pgbackrest_*<TAB>value` lines on stdout, among them `pgbackrest_backup_seconds`, `pgbackrest_restore_seconds`, `pgbackrest_rto_seconds`, `pgbackrest_rpo_events` and `pgbackrest_status pass`. One run on 2026-10-10 (30 records, 5 events per tail): full backup 3.2 s,
restore command 1.1 s, RTO 13.9 s including cluster start and recovery, 50 of 55 events recovered (the 5 written after the last WAL switch were lost; `archive_timeout` was set to 15 s to bound that).
The full drill (all backup layers, with a report) is `just drill` (`bash dev/drills/restore.sh`) and fills `docs/templates/restore-drill.md`.

What the drill does, which is also the procedure (run these against **your** cluster only after reading the warning below; the commands use the stanza name `drill`, the config file `$CONF` and a cluster `16/drill`; substitute your own):
1. Enable WAL archiving on the cluster (`pg_conftool` writes `postgresql.conf`; restart after changing `archive_mode`):
   ```
   sudo pg_conftool 16 drill set archive_mode on
   sudo pg_conftool 16 drill set archive_timeout 15s
   sudo pg_conftool 16 drill set archive_command "pgbackrest --config=$CONF --stanza=drill archive-push %p"
   ```
2. Create the stanza and check the archive path, as the `postgres` user:
   ```
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill stanza-create
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill check
   ```
3. Take a full backup (`--type=incr` or `--type=diff` for the others; weekly full and daily incremental is the production schedule from the brief, which is not scheduled by this repository):
   ```
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill backup --type=full
   ```
   The output ends with `new backup label = <timestamp>F`, `full backup size = ...` and `backup command end: completed successfully`.
4. Force the current WAL segment into the archive when you need a recovery point now: `SELECT pg_switch_wal()`. WAL not yet archived when the machine is lost is lost; `archive_timeout` bounds how much that can be.
5. After a loss: stop the cluster, empty its data directory, restore, start, and wait until recovery has finished (`SELECT pg_is_in_recovery()` returns `f`):
   ```
   sudo pg_ctlcluster 16 drill stop -m immediate
   sudo find /var/lib/postgresql/16/drill -mindepth 1 -delete
   cd /tmp && sudo -u postgres pgbackrest --config="$CONF" --stanza=drill restore
   sudo pg_ctlcluster 16 drill start
   ```
   The restore output includes `restore backup set <label>` and `restore command end: completed successfully`. By default pgBackRest recovers to the end of the archived WAL. Point-in-time recovery (`--type=time --target=...`) is a pgBackRest option that this drill does not exercise; say so.
6. Verify against the ledger archive, as in `restore-from-archive.md` step 8 (use the cluster's URL, for example `postgresql://postgres:drill@localhost:5440/tl_drill` in the drill):
   ```
   uv run tl ledger verify --db postgresql://postgres:drill@localhost:5440/tl_drill
   uv run tl archive verify --archive /path/to/archive --public-key /path/to/archive-signing.pub --db postgresql://postgres:drill@localhost:5440/tl_drill --deep
   ```
   Expect `hash chains intact` and `database ... agrees up to seq N` (N is the archive's last seq; events newer than the archive are chain-checked too).
7. **Warning:** never run the drill's commands against the shared development cluster on port 5432 or its `tl_test` database. The drill refuses nothing by itself; it simply only ever touches cluster `16/drill`. A leftover scratch cluster from an interrupted run is removed at the start of the next run
   (`pg_lsclusters` shows it; `sudo pg_dropcluster 16 drill --stop` removes it by hand).
8. Roll back: a failed restore leaves the data directory half written; empty it and run the restore again. The repository (`repo1-path`) is never modified by a restore.

### Must cover
Purpose and when to use (Postgres loss, quarterly drill, after upgrades); prerequisites (apt package, sudo, the config template, a stanza); the drill as the safe way to practise; the procedure steps above; the measured numbers (labelled as one dev run on a small dataset); verification against the ledger archive; what the drill does not
exercise (point-in-time recovery, incremental and differential backups, the encrypted S3 repository); roll back; related runbooks (`restore-from-archive.md`, `ledger-archive-and-verify.md`, `postgres-local-setup.md`).

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
- `dev/backup/pgbackrest.conf.tmpl`
- `dev/drills/pgbackrest.sh` (read it to check the facts; do not copy its text wholesale)
may explore: (none)

## Allowed paths
- `docs/runbooks/pgbackrest-restore.md` (create)
- `docs/reports/P0-I7/P0-I7-T07.md` (create: your report; commit it)

## Acceptance
```
just check
test -s docs/runbooks/pgbackrest-restore.md
```
Expected: `just check` clean. Then check yourself, and say so in the report, that every fenced command appears in *Facts* and that each *Must cover* item has a section or step.

## Tests to add
None (documentation).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T07.md` and committed. List under *Open questions* anything in the facts that looked inconsistent.

## Escalation triggers
- Stop and report *Blocked* if the facts contradict each other or a step would need a command that is not listed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
