# P2-SEED-T07 — The schedule section of the demo project

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests
Depends on: —
Branch: `p2/seed-t07-schedule`   (from p2/seed; worktree /home/user/wt/seed/p2-seed-t07)

## Goal
Fill `dev/seed/demo_project/schedule.py` (a stub) so P200 has a schedule: one `DefineSchedule` (code `MAIN`), then four weekly
snapshots built from synthetic XER files and published, so `tl xer`/schedule reads, compare and look-ahead have data. Use the
real path only: `DefineSchedule`, `OpenScheduleSnapshot`, attach the file through `world.upload(record_id, slot="xer", ...)`
(content type `application/octet-stream`, check `XER_TYPE` in `tl_mod_schedule/testing.py`), `StartScheduleSnapshot`, run the
worker, `PublishScheduleSnapshot`. Files come from `tl_xer.synth.series(seed, 4)` then `make_xer` (pure, no clock). The worker is
`tl_mod_schedule.worker.build_worker(db, world.files, worker_id="seed")`, then `worker.runner.run_until_idle()`; copy the exact
calls from `ScheduleWorld.work` and `.publish` in `packages/tl-modules/schedule/src/tl_mod_schedule/testing.py`. Each snapshot
falls on its own Monday: `world.on(date)` for 2026-10-19, 10-26, 11-02 and TODAY. Then `LinkActivity` for 8–10 CWPs of the awp
section to activity ids of the last snapshot (skip with one stdout line when the awp section is absent).
Run as `mokafor` (admin). Only the section's `rng` for choices; no raw SQL writes.

## Context (read these, nothing else)
- `dev/seed/demo_project/quality.py` (section pattern), `registry.py`, `world.py`
- `packages/tl-modules/schedule/src/tl_mod_schedule/testing.py`
- `packages/tl-modules/schedule/README.md`, `docs/runbooks/schedule-snapshots.md`
- `tests/tools/test_demo_project_quality.py` (child-process test pattern)
may explore: `packages/tl-xer/src/tl_xer/synth.py` (head and `series`)

## Allowed paths
- `dev/seed/demo_project/schedule.py`
- `tests/tools/test_demo_project_schedule.py` (create)
- `docs/reports/P2-SEED/T07.md`

## Acceptance
```
just check
just gate tests/tools/test_demo_project_schedule.py tests/tools/test_demo_project.py
```
Expected: pass; no other file changed (registry and `__init__` already name the section).

## Tests to add
`tests/tools/test_demo_project_schedule.py`: `--sections core,awp,schedule` on fresh SQLite: one `schedule.Schedule`, 4
`schedule.ScheduleSnapshot` all published, activity refs exist for the last snapshot, 8+ links when awp ran; the same twice
gives equal counts and key hash; a run without `schedule` leaves the other types' counts unchanged.

## Escalation triggers
- The worker needs a process or setting the seed cannot give (stop; the supervisor decides, no new command is added).
- A command refuses `mokafor`.
