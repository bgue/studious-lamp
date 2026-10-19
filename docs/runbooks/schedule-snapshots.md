# Runbook — schedule snapshots, the worker, reconcile and the flagging job

Purpose: upload and publish P6 schedules, run the worker that builds snapshots and flags links, recover after a restore, and import a cost snapshot. Brief: §9 M11, §24.6. Decision: ADR-0015.

## When to use
- A planner sends a new XER file or a cost export.
- A snapshot stays in `Processing`, or a link shows an activity that is no longer in the schedule.
- After a restore from the archive or a backup (the queue and the typed `sched_*` rows are not part of it).

## Before you start
- Access: define, publish and void need the document controller or admin; `tl xer worker`, `tl xer reconcile` and `tl cost import --apply` need admin. Opening, attaching, queueing and linking need any signed-in person.
- The worker is the only process that reads XER files. Run one per ledger. Safe to run during business hours: yes; a build reads the file in a child process with its own limits (60 s, 1 GiB by default), and the settle holds the writer lock for about 13 s (SQLite) or 25 s (Postgres) at the largest legal snapshot, a few seconds for a normal one.
- Dev defaults: `TL_DB` as in `docs/runbooks/postgres-local-setup.md` or `run-on-postgres.md`; the commands take `--actor`, default the signed-in user (the dev actor in a dev ledger).

## Steps: upload, build, publish
1. Define the schedule once (controller).
   ```
   uv run tl xer define MAIN --project P123 --name "Main schedule" --type current
   ```
   Expected: `defined MAIN <id>`.
2. Upload a file. This opens snapshot *n*, attaches the file and queues the build.
   ```
   uv run tl xer upload week1.xer --project P123 --schedule MAIN
   ```
   Expected: `queued MAIN#1 <id>`. The same file is never queued twice for a schedule. `--no-start` attaches without queueing; `uv run tl xer start 1 --project P123 --schedule MAIN` queues it later.
3. Run the worker (admin). `--once` runs what is queued and exits; without it the worker waits for more (Ctrl-C ends it cleanly).
   ```
   uv run tl xer worker --once
   ```
   Expected: `ran <snapshot id> schedule.build done` per build and `worker done: ran=<n>`.
4. Look at the result (the schedule's snapshot list in the TUI, `tl xer` reads, or `GET /projects/P123/schedules/MAIN`): the snapshot is `Valid` (counts in the report) or `Invalid` (the report lists problems with a code, a place and a fixed message; fix the file and upload again).
5. Publish (controller). A data date more than 31 days after today, or not after the current one, is refused.
   ```
   uv run tl xer publish 1 --project P123 --schedule MAIN
   ```
   Expected: `published MAIN#1`. If the schedule has links to activities a flagging job is queued (step: the flagging job).
6. Void a snapshot that is not published (controller): `uv run tl xer void 2 --project P123 --schedule MAIN --reason "wrong project"`.

## Too many snapshots waiting
`error: schedule MAIN already has 20 snapshots waiting for a build` (`too_many_open_snapshots`, 409): a schedule holds at most 20 snapshots in `Uploaded` or `Processing`. Anyone signed in may open one, so one person can fill the places; that is accepted. Run `tl xer worker --once` to build what waits (a built snapshot frees its place), or void the ones nobody wants with `tl xer void <number> --project <project> --schedule <code> --reason "..."` (a controller's act). The count is taken inside the write transaction, which Postgres and SQLite serialise, so concurrent openers cannot go over the cap.

## The flagging job
Publishing queues `schedule.flag_orphans` (job id `flag:<schedule id>:<ulid>`); the same worker runs it. Each run does at most 500 operations (a reference changed, a link flagged or restored) and queues the next run if work is left. **Until it has finished, a link to a removed activity still reads as current**; the schedule's detail view says `links_being_checked`. Run `uv run tl xer worker --once` after a publish to close the window. A flag written by the job has the actor and source `svc:schedule`; the job restores only those.

If a run fails with `typed rows missing`, the current snapshot's `sched_*` rows are not there: run `tl xer reconcile` (below).

## After a restore
1. Restore the database from the archive (`docs/runbooks/restore-from-archive.md`). The ledger comes back; the `job_queue` and the `sched_*` tables do not.
2. Write the typed rows again from the source files, then queue what was lost. Admin.
   ```
   uv run tl xer reconcile
   ```
   Expected: `requeued <n>`, one `<key> <outcome> <detail>` per built snapshot, a summary. It checks each file against the typed hash the ledger recorded. Exit code 1: a file no longer gives the rows the ledger recorded (`mismatch`; the file in the object store is not the one that was read, see `docs/runbooks/object-store-reconciliation.md`) or cannot be read. `--project P123` limits it to one project.
3. Run the worker: `uv run tl xer worker --once`. (`reconcile` already queued the lost builds and flagging jobs; `worker --requeue` does the same first.)

## Import a cost snapshot
1. Preview (any signed-in person; writes nothing).
   ```
   uv run tl cost import cost-2026-09.csv --project P123 --period 2026-09 --as-of 2026-09-30
   ```
   Expected: the codes it would create and change, the problems that would refuse it (at most 100 shown), and `dry run: nothing written`.
2. Apply (admin): add `--apply`. A period already imported becomes the next revision (`2026-09@2`).

## Read the schedule
```
uv run tl xer ls --project P123
uv run tl xer show --project P123 --schedule MAIN
uv run tl xer compare --project P123 --schedule MAIN              # the current snapshot against the one before
uv run tl xer look-ahead --project P123 --schedule MAIN --weeks 4
uv run tl xer resolve A1230 --project P123 --schedule MAIN --as-of 1       # or a date, or `current`
uv run tl xer health --project P123 --schedule MAIN                # links whose activity left
uv run tl xer unscheduled --project P123 --type core.Record        # records with no activity
uv run tl cost report budget --project P123 --unit quantity --over
uv run tl cost report uncoded --project P123 --type core.Record
```
The TUI shows the same on `F12`; an agent reads them with the MCP tools of `tl_mcp.schedule_read_tools`. Any signed-in person may read (`document.read`).

## Verify
- `uv run tl xer worker --once` prints `ran=0` when the queue is empty.
- A snapshot is `Valid` or `Invalid`, never stuck in `Processing` once the worker has run. A snapshot still `Processing` with no job means a lost queue: `uv run tl xer worker --once --requeue`.
- After reconcile, `uv run tl xer reconcile` again prints only `ok` outcomes.

## Roll back
- A published snapshot cannot be unpublished; publish the correct snapshot next (the old one becomes Superseded). A wrongly linked record is fixed with the core link commands (retract, re-pin).
- A wrong cost import is corrected by importing the corrected file (the next revision of the period).

## Related
- ADR-0015, ADR-0014, `docs/modules/schedule/README.md`, `docs/modules/cost/README.md`
- `docs/runbooks/derivation-pipeline.md` (the same job queue and worker rules), `docs/runbooks/restore-from-archive.md`
