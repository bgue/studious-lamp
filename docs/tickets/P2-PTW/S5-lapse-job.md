# P2-PTW-S5 — The lapse job: `permits.lapse` flags each lapse once

kind: piece
review: full
branch: p2/ptw-s5-lapse-job
worktree: /home/user/wt/ptw/s5
Base: `p2/ip-r3` (PTW-S2 merged). Merge note: **waits for X4 on trunk** (D8) like every merge into `p2/ip`; build, gate and review may start now. Independent of S3 (disjoint files).
Depends on: PTW S1, T00, S2 (merged: `names.py` event `Permit.Lapsed`, projector sets `lapse_flagged_for`, `rules.effective_state`, `handlers/common.py`, `tests/permit_world.py`).
Gated: a system job that writes events on a safety record (reserved source; APPROVALS line: job kind and source). Labels: core, job, safety.

## Why
`docs/build-spec/module-designs/permits.md` §4 ("Lapsed") and §10 clause 2. Lapsed is a derived word everywhere (`rules.effective_state`); the job only writes the fact "this lapse was noticed" so feeds and readiness can see it. A permit already reads Lapsed without the job, so the job is never what makes a permit unsafe or safe: it must not change a state, a `valid_until`, a hold or any other field.

## Goal
1. **Job kind** `tl_mod_permits/lapse.py`, kind `permits.lapse` (`names.JOB_KIND`, `JOB_SOURCE = "job:permits.lapse"`, `JOB_PREFIX`, `JOB_ACTOR` added to `names.py`: one new block, no other edit). Shape to copy exactly: the scaffold job on branch `p2/i4b`, read it with `git show p2/i4b:packages/tl-modules/scaffold/src/tl_mod_scaffold/inspections_due.py` and its test `git show p2/i4b:packages/tl-modules/scaffold/tests/test_inspections_job.py` (never check out that branch): `job_id(project, now)`, `parse_job_id`, `request(uow, project, now) -> bool` (False when that run is already queued or done), a `LapseKind` with `started`, `prepare`, `run`, `settle`, `failed`, `expired` (a job has no record: `started`, `failed`, `expired` write nothing).
2. **Clock is a parameter.** Job id `ptwlapse:<project>:<YYYY-MM-DDTHH:MM>` (UTC, the minute of `now`, which the caller passes: the caller rounds nothing, so two calls in one minute are one run; the run reads no clock itself: `prepare` and `settle` use the `now` parsed from the id).
3. **Run.** `prepare` reads every permit of the project whose stored state is `Active` and whose `valid_until` is not after `now` (a NULL end is lapsed, as `rules.effective_state`), and whose `lapse_flagged_for` is not equal to that `valid_until` (compare as instants, both aware UTC); at most 500 per run, `settle` re-queues the next run once when more remain (same re-queue rule as the rollup job; state the id of the re-queued run in the report). `settle` appends one `Permit.Lapsed` per permit (payload `record_id`, `valid_until` = the one that passed, `feed_policy` per the S1 schema decision: copy what `Permit.Suspended` carries unless the S1 schema says the lapse is a feed event; `at` = `now`), actor `JOB_ACTOR`, source `JOB_SOURCE`, the stream version read through `handlers.common.version_of`, in one unit of work. A second run for the same instant, or any later run before the permit is revalidated, finds nothing and writes nothing (statement-for-statement: no `INSERT` into `events`). A revalidated permit with a new `valid_until` that passes again is flagged again, once.
4. **Only the flag.** The run never changes state, `valid_until`, holds, links or isolations; it appends no `Permit.Suspended`. A suspended, handed-back, closed or cancelled permit is never flagged. A permit the job cannot read (no scope match) is skipped. The job reads typed tables as a system actor; it puts no record text (area, holder, description) in an event, an error or a log line.
5. **Entry for people and demos.** `tl_mod_permits.lapse.run_once(open_uow_factory, project, now) -> int` (queue the run, run the runner until idle, return the number of events appended), the same helper the test and `dev/demos/P2-PTW.sh` call. No CLI command, no schedule: wiring a worker or scheduler is a later ticket (say so in the report).
6. **Reserved source.** `job:` is already a reserved source prefix (`tl_core/services/reserved.py`, `PHASE2_SOURCE_PREFIXES`): a client command that sets `source="job:permits.lapse"` is refused with 422 `reserved_identifier`; test it. If the correlation id you choose needs a reserved prefix, STOP (escalation: that file is core); the plan uses none.
7. **Registration.** The job kind is found the way the scaffold job's is on `p2/i4b` (same module-level `JobRunner` kind list or entry point; copy it). If that needs a file outside Allowed paths, stop and escalate.

## Provided tests
Own tests in `packages/tl-modules/permits/tests/test_lapse_job.py` (names; behaviour in parentheses): `test_a_lapsed_permit_is_flagged_once` (issue, move the clock past `valid_until`, run, one `Permit.Lapsed` event with the right `valid_until`; second run writes nothing, statement counter shows no events insert), `test_the_shown_state_is_lapsed_with_or_without_the_job` (`views.permit_detail` agrees before and after), `test_a_revalidated_permit_lapses_and_is_flagged_again`, `test_only_active_permits_are_flagged` (Requested, Approved, Suspended, Handed back, Closed, Cancelled, Rejected untouched), `test_the_run_changes_nothing_but_the_flag` (diff every `cur_permits_permit` column except `lapse_flagged_for`; the workflow state row unchanged), `test_a_run_is_keyed_by_project_and_minute` (job id round trip, bad ids refused, a re-request of a done run is False), `test_the_limit_requeues_once` (501 lapsed permits seeded through the world's events: two runs, all flagged, none twice), `test_source_is_reserved` (a client command with the source is refused), `test_no_text_leaks` (events, error text and `caplog` hold no area, holder or description), `test_hidden_permits_are_flagged_too` (a permit for a restricted record is flagged: the job is a system actor, the flag carries no text; the permit stays hidden to the viewer). The world helper `permit_world.py` gets only what the tests need (append).

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/lapse.py` (create), `names.py` (the one new block), `packages/tl-modules/permits/tests/test_lapse_job.py` (create), `packages/tl-modules/permits/tests/permit_world.py` (append)
- registration lines as item 7 names them, only if inside `packages/tl-modules/permits/` or the one file the scaffold job on `p2/i4b` uses (list it in the report)
- `docs/reports/P2-PTW/S5.md`, `dev/accept/P2-PTW/S5.py` (SQLite, `PASS <check>` lines, final `S5 ok`, clock fixed)
Read-only: everything else (schema, `tl_core`, surfaces, other modules, `module.py`, `handlers/`).

## Acceptance (once each, one at a time; whole-repo pyright is OOM-killed on this box: when another heavy run is live run ruff plus pyright on `packages/tl-modules/permits` and the test file instead of `just check`)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/permits/tests/test_lapse_job.py
just gate packages/tl-modules/permits/tests/test_views_lapse.py packages/tl-modules/permits/tests/test_permit_commands.py packages/tl-modules/permits/tests/test_projectors.py
just gate tests/contract/test_reserved_prefixes.py
just gate-pg packages/tl-modules/permits/tests/test_lapse_job.py
uv run python dev/accept/P2-PTW/S5.py
```

## Mutation (sentinel and at most 5, in this worktree, 3 lines in the report)
Sentinel: the run flags a Closed permit. Targets: the same `valid_until` flagged twice (the `lapse_flagged_for` comparison removed); `valid_until` equal to `now` treated as not lapsed (off by one against `effective_state`); the run also moves the state or suspends; the source set to a non-reserved value; the 500 limit dropped so the re-queue never happens.

## Report
`docs/reports/P2-PTW/S5.md` (<= 60 lines): deviations first; the registration seam used; the re-queue id; the feed policy chosen and why; gate output (<= 5 lines per command); mutation 3 lines; final signatures for T15 (`request`, `run_once`, `job_id`, `JOB_KIND`, `JOB_SOURCE`). Builder return <= 15 lines. Commit `P2-PTW-S5: ...`.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
