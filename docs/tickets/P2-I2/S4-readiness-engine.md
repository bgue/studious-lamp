# P2-I2-S4 — Readiness engine: job, evaluation, projector, `request`, `evaluate_now`, `constraints_cleared`

Status: staged (dispatch after C1 merged; its tests that call the constraint functions run after C2 merged)
Tier: builder
Kind: piece
Review: full
Labels: core, job, event
Depends on: S1, S2 (merged), C1 (merged); codes against the FROZEN functions of ADR-0024 decision 6 (`tl_core.constraints`, stub in tree)
Branch: `p2/i2-s4-readiness-engine`
Worktree: `/home/user/wt/i2-s4` (from `p2/i2` head)

## Goal
After this piece an IWP can be evaluated against every registered readiness check (the 4 real ones: `documents_current`, `rfis_answered`,
`materials_reserved`, `constraints_cleared`, plus the five `n_a` ones), the result is one `IWP.ReadinessEvaluated` event projected to
`cur_awp_readiness` and its child table, `IWP.Ready` is appended when the IWP turns ready, and the IWP moves Constraint check <-> Ready by
itself. Everything lives under `tl_mod_awp/readiness/`; the awp module imports no other module.

## Brief references (pasted; the contract `packages/tl-core/src/tl_core/readiness/types.py` is frozen and its trailing comment is the signature list)
- Job kind `awp.readiness` (`JOB_KIND`), one IWP per run, job id `ready:<iwp id>`, lease `EVALUATION_LEASE_S`, per-check bound `CHECK_MAX_SECONDS`; a check that
  exceeds a bound or returns more than the contract allows is `unknown` with a fixed detail, never truncated; a check that raises is `unknown`.
  Worker: add the kind to `tl_mod_awp/worker.py` next to `awp.rollup` (same `JobRunner` shape; a run reads with `iwp_facts`, calls each check on a read connection, settles with the event).
- `tl_mod_awp.readiness.request(uow, iwp_ids, *, reason) -> int`, `evaluate_now(uow, iwp_id, today) -> ReadinessView`, `views.readiness(conn, scope, iwp_key) -> ReadinessView`
  exactly as the contract comment says. `ready` is true when every check is `ok` or `n_a` (D9). A check `unknown` makes `ready` false.
- Event `IWP.ReadinessEvaluated` {iwp_id, evaluated_at, today, ready, checks[<= 32], facts_hash} on the IWP's stream (schema is S1's; projector writes `cur_awp_readiness` and
  `cur_awp_readiness_check`, last evaluation only; history is the events). `IWP.Ready` {iwp_id, evaluated_at} when `ready` turns true from not-ready or none.
- Moves (by_module, `Workflow.Transitioned`, through the awp `move` helper, source `job:awp.readiness`): evaluation ready and state Constraint check -> transition `ready`; not ready and
  state Ready -> `unready`; any other state: no move. The `ready` transition carries the ADR-0024 guard (phase `ready`): if it refuses, the evaluation records the guard message as the
  `constraints_cleared` detail and stays in Constraint check (do not catch the error silently: the refusal is the outcome).
- Check `constraints_cleared` (name, version "1", watches `core.Constraint`, shipped in `readiness/checks.py`, entry point in the awp `pyproject.toml` table only): counts open blocking constraints of
  phase `ready` on the IWP by a plain read of `cur_core_constraint` joined to `cur_core_record` (open = status not Cleared/Withdrawn, NULL = Open): none -> `ok` (`count_ok = count_total = 0`... use
  the closed/total counts of that phase), some -> `blocked`, `resolve_via` the constraint records (key, `core.Constraint`), detail `<open> open blocking constraints` fixed text plus count. It never reads descriptions or owners.
- Check-sourced constraints (F6): when a check other than `constraints_cleared` is `blocked`, the job raises one constraint through `raise_constraint(uow, subject_id=<iwp>, phase="ready",
  severity="blocking", category=<check's category map below>, source="check", check_name=<name>, facts_hash=<sha256 of the check's name, state, detail>, by_module="awp", due_at=<planned start minus
  awp.iwp.ready_lead_weeks weeks, ISO date; omit when no planned start>, description=<fixed text "readiness check <name> is blocked">)`; when it turns `ok` or `n_a` it calls `clear_constraint(uow,
  constraint_id=..., reason="check passed", by_module="awp")` for the open one of that `check_name`. Category map: `materials_reserved` materials, `documents_current` engineering, `rfis_answered` rfi, other
  names `other`. `suppressed`/`exists` outcomes are fine and recorded nowhere. Per run: at most 9 raises and clears.
- Event-to-IWP mapping (F3): a subscriber on each check's `watches` types (read through `load_checks()`); an event naming a record whose type is `awp.IWP` evaluates it; otherwise map by
  `work_package_id` for types that carry the column (MTO lines, reservations: the materials tables point to an IWP by it) with a plain read of the column named in the report; when no mapping
  exists, call `evaluate_now` for the scope's IWPs in states Constraint check and Ready only, at most 200, queued by `request`. Subscription is registered where the module registers its projectors
  (C2 glue adds that one hook line to `module.py`; you provide `readiness.hooks.on_event(uow, event)` and say the exact line in the report).
- The watched-types subscriber never reads a record's text and never the viewer filter's output: system job, keys only.

## Interfaces (open these)
`tl_core/readiness/{types,harness,registry}.py`; `tl_mod_awp/{facts,worker,common,names,checks_na}.py`; `packages/tl-modules/materials/src/tl_mod_materials/readiness.py` (check shape);
`tl_core/jobs` (JobRunner and `Claim`); the readiness tables in `schema/modules/awp/readiness.yaml`; ADR-0024 decision 6 and the stub `tl_core/constraints/__init__.py`.

## Context (<= 10 files)
The contract; `facts.py`; `worker.py`; `common.py` (`move`, `append`); one check (`checks_na.py`); `docs/reports/P2-I2/S1.md`, `docs/reports/P2-I2/T06b.md`; ADR-0024; the stub; README of this increment (D9, D13).

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/readiness/**` (create: `__init__.py`, `engine.py`, `job.py`, `projector.py`, `views.py`, `checks.py`, `hooks.py`)
- `packages/tl-modules/awp/src/tl_mod_awp/worker.py` (add the kind; nothing else), `names.py` (constants), `pyproject.toml` (the entry-point table only: add `constraints_cleared`)
- consequential pins (rule 12): lists of readiness checks, job kinds, event subscribers; union form, each listed
- `dev/accept/P2-I2/S4.py` (create), `docs/reports/P2-I2/S4.md` (create)
Not allowed: `module.py` (C2 glue), `schema/**`, `tl_core/**`, other modules, any command or route, new pytest (S5).

## Acceptance (run once each; one package per gate)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/S4.py
just gate packages/tl-modules/awp/tests tests/services/test_modules.py
```
`S4.py` (SQLite tmp db, helper code in a sibling module, script <= 70 lines): with test stand-in checks (names never reuse a real module name) and the real `constraints_cleared`:
a fresh IWP evaluates, one event, projection rows equal `views.readiness`; ready false with a blocked stand-in, true when `n_a`/`ok`; `IWP.Ready` appended once on the turn; Constraint check -> Ready
and back through `unready`; the `ready` guard refusal is the outcome when an open blocking `ready` constraint exists (needs C2: the script SKIPs those steps with a printed `SKIP needs C2` when
`tl_core.constraints` raises `NotImplementedError`; the orchestrator reruns after C2); a check that raises, one over the bound and one returning 33 results are `unknown`; `request` is idempotent per id;
watched event maps by `work_package_id`, else falls back to `evaluate_now`; a job rebuild equals incremental; `evaluate_now` returns the same view; the job writes no record text. Final `S4 ok`.

## Guards for S5 (name file:line; run no mutants here)
`ready` = all ok or n_a; unknown blocks; the move table; the bounds; `Ready` appended once; `constraints_cleared` phase filter; raise and clear idempotence; fallback cap 200; job id uniqueness.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; the `work_package_id` column used; the exact `module.py` hook line; pins; acceptance output (<= 5 lines per command); guards file:line; learnings.

## Commit
`P2-I2-S4: <imperative summary>`; body says what and why; end with the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: a frozen signature does not fit a call; a frozen contract field must change; the materials tables carry no `work_package_id`; the `ready` transition cannot carry the guard; a pyproject table needs more than one line.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
