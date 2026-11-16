# P2-I4B-T05b — Readiness check `labour_requested` (replaces the awp placeholder)

Status: staged (r2: provided test and stub committed; dispatch after T05a merged: both edit `packages/tl-modules/scaffold/pyproject.toml` and the exact-set pins)
Tier: haiku
Kind: ticket
Review: full
Labels: core-module, readiness
Depends on: T05a (merged)
Branch: `p2/i4b-t05b-labour-requested`
Worktree: `/home/user/wt/i4b/t05b` (from `p2/i4b` head)

## Goal
`labour_requested` answers for one IWP whether an approved labour requisition serves it and covers its planned window. Today a placeholder of that name (`tl_mod_awp/checks_na.py`, always `n_a`) holds the name; this ticket moves the name to the real check
(a second entry point of one name is refused by `load_checks`). The check lives in the scaffold package beside `scaffold_tagged` (workstream B owns both), reads requisitions tables only and imports `tl_mod_requisitions.names`.

## Brief references (pasted)
> Answer (decision D9c of this increment, open question Q3 for the orchestrator): `n_a` (detail `NO_ESTIMATE`) when `iwp.estimated_hours` is `None` or `<= 0` (nothing to staff yet). Otherwise read the labour requisitions whose `for_record_id` is the IWP, not voided, state not `Rejected` or `Cancelled`, with their `start_date` and `end_date`:
> 1. `ok` (detail `COVERED`) when one is approved or later (`Approved`, `Scheduled`, `In progress`, `Done`, `Closed`) and covers the window: `start_date <= planned_start` and `end_date >= planned_finish`; when the IWP lacks `planned_start` or `planned_finish`, an approved-or-later one is enough. `resolve_via` empty; `count_ok`, `count_total` stay `None`.
> 2. else `pending` (detail `NOT_APPROVED`) when one is `Requested`; `resolve_via` = the `Requested` ones.
> 3. else `blocked` (detail `NOT_COVERED`) when an approved-or-later one exists (none covers); `resolve_via` = those.
> 4. else `blocked` (detail `NO_REQUISITION`), `resolve_via` empty.
> `resolve_via` entries are `RecordRef(record_id, LABOR, key)` by key, at most `MAX_RESOLVE_VIA`. Fixed texts are the constants of the stub; never put a craft, subject or reason in a detail.
> Read, one statement, no viewer (a job runs it): `SELECT t.id, r.key, COALESCE(r.status, 'Requested') AS state, t.start_date, t.end_date FROM cur_requisitions_labor_requisition t JOIN cur_core_record r ON r.id = t.id WHERE t.for_record_id = :iwp AND r.scope = :scope AND r.voided = :no ORDER BY r.key, r.id` (use `LABOR_TABLE`, `ST_*` from `tl_mod_requisitions.names`; dates are ISO text, compare with `planned_start.isoformat()`); filter the states in Python. Any exception is `unknown` with `UNKNOWN`, never raised. `today` is unused (`del today`).
> Entry points: add `labour_requested = "tl_mod_scaffold.labour:labour_requested"` under `[project.entry-points."throughline.readiness_checks"]` of `packages/tl-modules/scaffold/pyproject.toml`; delete the `labour_requested` line of `packages/tl-modules/awp/pyproject.toml` and the `labour_requested` function of `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py` (update that module's docstring: four checks).

## Interfaces (in the tree as a stub: constants, class and factory are final; fill `evaluate`)
`packages/tl-modules/scaffold/src/tl_mod_scaffold/labour.py` (read it first).

## Context (read these, nothing else)
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/{labour.py, readiness.py}` (T05a's body is the pattern), `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py`
- the provided test `docs/tickets/P2-I4B/provided/T05b_test_labour_requested.py` (do not edit it), `packages/tl-modules/requisitions/src/tl_mod_requisitions/names.py` (table, states)

## Allowed paths
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/labour.py` (the body), `packages/tl-modules/scaffold/pyproject.toml` (one entry-point line)
- `packages/tl-modules/awp/pyproject.toml` (remove one line), `packages/tl-modules/awp/src/tl_mod_awp/checks_na.py` (remove one function, docstring)
- `packages/tl-modules/scaffold/tests/test_labour_requested.py` (create: byte-identical copy of the provided test), `docs/reports/P2-I4B/T05b.md` (create)
- Consequential pins (rule 12; list each in the report): `dev/accept/P2-I2/T06b.py` (`EXPECTED` loses `labour_requested`; the other four stay) and anything else that asserts `labour_requested` is `n_a` (`grep -rn labour_requested packages dev tests --include=*.py`); `packages/tl-modules/awp/README.md` lines ~198-202 (the table row moves: say the check now ships in `tl_mod_scaffold/labour.py`). The exact-set pins already carry the name.

## Acceptance
```
uv sync --all-packages
cp docs/tickets/P2-I4B/provided/T05b_test_labour_requested.py packages/tl-modules/scaffold/tests/test_labour_requested.py
just check
just gate packages/tl-modules/scaffold/tests/test_labour_requested.py packages/tl-core/tests/test_readiness_registry.py packages/tl-modules/awp/tests/readiness
uv run python dev/accept/P2-I2/T06b.py
cmp docs/tickets/P2-I4B/provided/T05b_test_labour_requested.py packages/tl-modules/scaffold/tests/test_labour_requested.py
```
Expected: the 12 provided tests pass, the pinned files and `T06b.py` pass, `cmp` silent.

## Tests to add
The provided test (copied): found by name (placeholder gone); `n_a` for no or zero estimate with the contract; no requisition blocks (another package's labour does not count); requested is pending with the ref and key; approved covering the window is ok with the contract, also for a window inside it; a window starting early or ending late blocks with the ref; no planned dates needs only an approved one; a short approved one plus a requested one is pending, then a covering one makes it ok; cancelled and rejected count for nothing; failed read is `unknown`; one statement.

## Escalation triggers
- A demo or accept script that now fails because its IWPs carry hours and no requisition (do not fix; list it under Blocked with the script name: the orchestrator decides Q3); a pin that needs more than a name removed; the provided test fails on a line the ticket does not explain.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, <= 5 decisive lines per command; pins listed. Commit subjects `P2-I4B-T05b: ...`; trailer lines as your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not run the whole suite.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)

## Amendment 1 (orchestrator, 2026-11-15)
As in T05a: the statement-count listener ignores BEGIN, COMMIT and ROLLBACK (the SQLite adapter's `BEGIN DEFERRED`); the
bound stays at one read. The provided copy is updated to the same bytes; both paths are allowed for that.

## Amendment 2 (orchestrator, 2026-11-15)
Q3 ruling: the new `labour_requested` behaviour stands; the demo data is fixed. The seed IWPs carry estimated hours and no
labour requisition, so `python -m dev.seed.demo_project` stopped at the release section ("too few IWPs are Ready to
release"). The seed change is additive and goes through the commands: `dev/seed/demo_project/labour.py` (new) raises and
approves labour requisitions for IWPs, called from the constraints section just before it evaluates readiness.
Allowed path for this amendment: `dev/seed/demo_project/**` (and the seed tests under `tests/tools/test_demo_project*.py`
if a pin needs it; none did).
