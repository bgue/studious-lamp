# P2-I1-T04e — `tl awp rollup` and `tl awp worker`

Status: ready (S5, T04c, T04d merged; r9 batch)
Tier: haiku
Review: full
Labels: cli
Depends on: T04c (merged)
Branch: `p2/i1-t04e-rollup-worker`
Worktree: `/home/user/wt/i1/t04e` (from `p2/i1` head)

## Goal
The budget rollup is requested and run from the CLI: `tl awp rollup` queues it through `RequestRollup`; `tl awp worker` runs the awp job queue (D12). Mounting `awp_run.register(app)` in `tl_cli/awp.py` is supervisor glue.

## Verbs (fixed; both take `--project` where a scope is needed)
```
rollup --project P [--actor A]            -> RequestRollup via awp_write._execute; prints `rollup requested  job <result.stream_id>`  (idempotent: a second call queues nothing new; the handler gives no flag, print the same line)
worker [--once] [--requeue] [--idle S]    -> tl_mod_awp.worker.build_worker(db) as a context manager; the loop and the output lines are those of `tl derive worker` (tl_cli/derive_run.py lines 260-300): `ran <job id> <kind> <outcome>` per job, `requeued <n>` first with --requeue (requeue_orphans(db)), then `worker done: ran=<n>`; Ctrl-C ends it cleanly
```
`worker` takes no `--timeout` or `--factory` (the awp kind has one extractor-free job); `worker` is not project-scoped.

## Interfaces (verbatim)
```python
# tl_mod_awp.commands.RequestRollup (actor, source, scope) ; handle via AWP_COMMANDS ; CommandResult.stream_id = rollup.job_id(scope), key None, version 0
# tl_mod_awp.worker: build_worker(target, *, worker_id=None, lease_s=..., clock=...) -> Worker (context manager; .runner.run_once() -> result|None with .job_id .kind .outcome; .runner.run_until_idle()) ; requeue_orphans(target) -> int
# tl_cli.awp_write: _execute(db, build) -> CommandResult ; register pattern at the end of the file (verbs on the awp app itself here, no group)
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_write.py` lines 1-135 and 430-end, `packages/tl-cli/src/tl_cli/derive_run.py` lines 255-300
- `packages/tl-modules/awp/src/tl_mod_awp/worker.py` lines 195-250, `dev/accept/P2-I1/S5.py` lines 100-135 (queue and run), `dev/accept/P2-I1/T04c.py` (script pattern)

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_run.py` (create; not `awp_write.py`, `awp.py`, `main.py`)
- `dev/accept/P2-I1/T04e.py` (create), `docs/reports/P2-I1/T04e.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T04e.py --db .accept/p2-i1.db
```
`T04e.py` (seed copy; `CliRunner` on a local app with `awp_run.register(app)`; `TL_ENV=dev`, temp `TL_SESSION_FILE`; the seed has no rollup rows, D25): `rollup` prints `rollup requested  job ...` and a second `rollup` exits 0 (`PASS rollup`); `worker --once` prints one `ran ... awp.rollup ...` line and `worker done: ran=1`, and `views.wbs_tree(...)` then has a node with `total_hours` not None (`PASS worker`); a second `worker --once` prints `worker done: ran=0` (`PASS idle`); `rollup` then `worker --once --requeue` prints `requeued 0` first (`PASS requeue`). Ends `T04e ok`. No pytest, no `just gate`.

## Tests to add
none (T11: `packages/tl-cli/tests/test_awp_run.py`).

## Report requirements
`docs/reports/P2-I1/T04e.md` <= 60 lines; deviations first; both verbs with sample output. Subject `P2-I1-T04e: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if `--once` cannot end without a job in the queue, or `build_worker` needs an argument not shown here: write what it says.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
