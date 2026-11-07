# P2-I1-S5 — The rollup run: `awp.rollup` job, rollup projector, worker

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: core
Depends on: S3 (merged @f482aad); built beside S4 (disjoint paths)
Branch: `p2/i1-s5-rollup`
Worktree: `/home/user/wt/i1-s5` (from `p2/i1` head)

## Goal
After this piece a queued `rollup:<scope>` job (S3's `rollup.request`) is run by a worker: it computes the CWP budget
hours per WBS node and cost code from the typed tables, appends `WBSNode.BudgetRolledUp` for the nodes whose figures
changed, and `cur_awp_rollup` holds them. Same ledger sequence gives the same figures; a rebuild never calls the job.

## Brief references (pasted; spec `docs/build-spec/specs/m3-wbs-cwp.md` §4 is authoritative)
Run (one scope, `JobRunner` kind `awp.rollup`, lease 300 s): read `as_of_seq`; for each leaf node n, `budget(n) =
Σ budget_hours(c) × pct(c,n) / 100` over non-void CWPs (all states count: it is budget); parents sum children; per leaf
the cost-code split is `budget(n) × pct(n,k) / 100`; a leaf with no cost codes puts its hours on an `unallocated` line.
Exact `Decimal`, then quantize to 0.1 h `ROUND_HALF_EVEN`; a node's split uses largest remainder so the parts sum to its
rounded total. Compare with `cur_awp_rollup`; append `WBSNode.BudgetRolledUp` {run_id, as_of_seq, total,
by_cost_code[...]} only for nodes whose figures differ, at most 500 nodes per run; settle re-queues when more remain.
Correlation `rollup:<run id>`, source `job:awp.rollup`. Event carries `feed_policy: none` (`common.silent`).
`cur_awp_rollup`: `scope`, `subject_kind` (`wbs_node`), `subject_id`, `line` (`total`, `cost_code`, `unallocated`),
`cost_code_id` (set only on `cost_code` lines), `measure` (`budget_hours`), `value`, `as_of_seq`, `run_id`.
Reads honour the viewer filter only in views (T10); the run is a system job and reads typed tables, but it must not put
record text in an event, an error or a log.

**D-c (decision):** `rollup.request()` leaves a `running` row alone (S3 report open question 3). So at settle the run
re-reads the ledger head; if a request arrived while it ran (head moved past `as_of_seq` and an awp event that changes
budget, allocation, retirement or void came after it) it queues itself again, once. A request while running must never
be lost; two requests while running queue one run. Extend `rollup.py` for this; keep `request()`'s signature.

## Interfaces
- `packages/tl-modules/awp/src/tl_mod_awp/rollup.py` (S3: `request`, `job_id`), `names.py` (`JOB_KIND_ROLLUP`, tables).
- Job runner and a worker module to copy the shape of: `packages/tl-core/src/tl_core/jobs/runner.py`
  (`JobKind`, `JobRunner`, `JobFailure`, `RunResult`) and `packages/tl-modules/documents/src/tl_mod_documents/derivation/worker.py`
  (`build_worker`, `requeue_orphans`).
- Projector seam: `projectors/rollup.py` `rollup_projectors()` (empty now; return your projector from it). Projector
  shape: `projectors/wbs.py`. Do not edit `module.py`, `projectors/__init__.py`, `names.py` (put new names in `rollup.py`
  or `worker.py`), `commands.py` or any handler: S4 owns them.
- `tl awp worker` itself is a CLI command and belongs to T04; you leave `tl_mod_awp.worker.build_worker(...)` and
  `requeue_orphans(...)` for it (decision: the spec's "`tl awp worker` entry" is this function).

## Context (<= 8 files)
- `docs/build-spec/specs/m3-wbs-cwp.md` §4; `docs/reports/P2-I1/S3.md` open question 3
- the interface files above; `schema/modules/awp/rollup.yaml`; `packages/tl-modules/awp/src/tl_mod_awp/projectors/wbs.py`
may explore: the jobs package for lease and re-queue behaviour.

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/{rollup,worker}.py`, `projectors/rollup.py`
- `dev/accept/P2-I1/S5.py` (create), `docs/reports/P2-I1/S5.md` (create)
Not allowed: any `schema/**` or generated file; `tl_core`; `packages/tl-modules/awp/pyproject.toml` (T02's); S4's files; new pytest files (tests at T11).

## Acceptance (run these once; no pytest)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S5.py
```
`S5.py` (SQLite tmp db, then the same on `TL_PG_URL` when set: same figures; one `PASS <check>` per check; final
`S5 ok`; <= 40 lines). S4's CWP commands do not exist yet, so the script seeds a WBS with the S3 commands and inserts
`cur_awp_cwp` and `cur_awp_cwp_allocation` rows directly by SQL (a fixture of the script only, say so in a comment);
it checks: leaf and parent totals and the cost-code split (a 60/40 leaf with 100.0 h gives 60.0 and 40.0); largest
remainder keeps parts summing to the rounded total (a 33.3/33.3/33.4 case and a 0.05 h tie to even); a leaf with no
cost codes lands on `unallocated`; void CWPs excluded, every non-void state counted; a second run with no change
appends nothing; a changed figure appends only the nodes that differ; the 500-node bound (seed 501 changed nodes:
500 appended, a re-queue left); D-c (a request made while the row is `running` queues one new run at settle); rebuild
of projections equals the incremental table; the event makes no feed card; correlation id and source on the events.
Benchmark: 5 000 nodes by 2 000 CWPs in one run, wall time printed (no pass bar; record it in the report for the
orchestrator).

## Guards T11 will mutate (name file:line in the report; run no mutants here)
Largest remainder; the unallocated bucket; the 500-node batch bound and re-queue; the D-c settle re-check;
`ROUND_HALF_EVEN`; void exclusion.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; acceptance output (<= 5 lines per
command); guards file:line; the benchmark line; candidate learnings. Builder return <= 15 lines.

## Commit
Subject `P2-I1-S5: <imperative summary>`; body says what and why; end with the harness attribution line, then the line
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not
merge; do not push.

## Escalation triggers
- *Blocked* if: a column the run needs is not in the generated rollup table; the queue cannot express the D-c re-queue
  without a `tl_core` change; the Postgres figures differ from SQLite's.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
