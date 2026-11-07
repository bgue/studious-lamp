# P2-I2-C2 — Core constraint commands, guard evaluation, confidentiality join

Status: dispatched r4 (C1 merged @945d126)
Tier: builder
Kind: piece
Review: full
Labels: core, access, security
Depends on: C1 (merged); ADR-0024 v2
Branch: `p2/i2-c2-constraint-commands`
Worktree: `/home/user/wt/i2-c2` (from `p2/i2` head)
Gate: orchestrator review (guard evaluation and the confidentiality join are security paths; Sec rows) before merge; ADR-0024 moves to accepted at this merge.

## Goal
After this piece `tl_core.constraints` does what ADR-0024 decisions 5, 6, 7, 8 say: the four commands (`RaiseConstraint`, `AssignConstraint`,
`ClearConstraint`, `WithdrawConstraint`), the three frozen functions with the stub's exact signatures, the projector, the guard
`no_open_blocking_constraints` evaluated by the workflow engine, and the confidentiality join to the subject. awp keeps no constraint code.

## Brief references
ADR-0024 decisions 4 to 8 (read them; they are the spec). Moved rules (from S2, `git show d2409f5:packages/tl-modules/awp/src/tl_mod_awp/constraints.py` and
`handlers/constraint.py`, `projectors/constraint.py`; rename `iwp_id` -> `subject_id`, `need_by` -> `due_at`, `constraint_type` -> `category`, `Void` -> `Withdrawn`): a person raises
only `manual`; other sources need `by_module`; `check` needs `check_name` and `facts_hash`; owner required for `manual`; a module clears only non-`manual`; a person's clear of a
check-raised one needs a reason and stores `suppress_hash` (`Constraint.Cleared.suppress: true`; the projector drops the hash on false); same subject, phase and `check_name` open -> `exists`;
equal hash to a suppressed one -> `suppressed`; `resolves` link on clear when `resolved_by` is given; `blocks` link Constraint -> subject, `targets` Constraint -> target (record kind);
`cleared_at` before `effective_at` refused; `cleared_at`, `effective_at` and `due_at` live in the payload and the row only; `append_in` gets no `effective_at` from them (envelope = capture time, ADR-0026); aging (`constraint_age_days(row, today)`, flag `aging` past a setting; reuse
`awp.constraint.aging_days` via its key if it is still the only one, else say so in the report). Command word `core.constraint.edit`; the subject must be visible to the actor
(a hidden subject answers as an unknown id). Ownership: `owner` `user:<name>` of an existing account.
Phase rule (decision 5): a blocking raise with a phase no guard of the subject's effective workflow names is refused `phase_not_gated`; advisory anywhere. The effective
definition is read as the engine reads it (project override, versioned). `by_module` raises are checked the same way.
Guard (engine): `no_open_blocking_constraints` fails when `open_blocking(conn, record_id, phase)` is non-empty; the phase defaults to the transition name; the message is fixed text
naming constraint keys and the phase only; replaces C1's pass-through branch. It also runs on `by_module` moves.
Confidentiality (decision 8): every read helper of this package takes the class from the subject by join at read time (`tl_core.confidentiality`), never from a copied column; a viewer who
cannot see the subject sees no constraint (lists, counts, events, feed, links); a viewer who sees the subject but not the target sees the constraint with no target, byte-identical to a constraint
raised without one. No `system_view()` anywhere in this package; `open_blocking` is keys-only and needs no viewer.
Offline class `draft_only`: nothing to do beyond the schema.

## Interfaces (open these)
`packages/tl-core/src/tl_core/constraints/__init__.py` (frozen signatures; keep them exactly), the C1 schema, `tl_core/services/{commands,records,links}.py` and one core command module
as the pattern (find a core `create_*_record` handler; the pattern file for a module is `packages/tl-modules/awp/src/tl_mod_awp/handlers/cwp.py` at `d2409f5`), `tl_core/workflow/{engine,loader}.py`, `tl_core/confidentiality.py`,
`tl_api/errors.py` (error row pattern), the registry where core commands are listed (grep `CORE_COMMANDS` or the table `tests/test_commands` pins).

## Context (<= 10 files)
ADR-0024; the stub; the S2 files above; `tl_core/workflow/engine.py`; `tl_core/confidentiality.py`; one core handler; `docs/reports/P2-I2/C1.md` (after C1 merged).

## Allowed paths
- `packages/tl-core/src/tl_core/constraints/**` (create: `commands.py`, `handlers.py`, `projector.py`, `guard.py`, `queries.py`, `errors.py`; `__init__.py` keeps its signatures and re-exports)
- `packages/tl-core/src/tl_core/workflow/engine.py` (the guard branch only), registry lines where core commands and projectors are listed (<= 10 lines; name each in the report)
- `packages/tl-api/src/tl_api/errors.py` (rows for the new errors), `docs/reference/openapi.json` (generated if routes appear)
- consequential pins (rule 12): command counts, controller/user sets, agent-refused counts, error rows; union form, each listed
- `dev/accept/P2-I2/C2.py` (create), `docs/reports/P2-I2/C2.md` (create)
Not allowed: `schema/**`, generated files (a gap is Blocked), awp or any module code, a CLI/API/TUI screen (T04b/T04d/T04c1), new pytest (S5).

## Acceptance (run once each; one package per gate)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/C2.py
just gate packages/tl-core/tests/workflow packages/tl-core/tests/auth
just gate packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_api_proposals.py
just gate packages/tl-modules/awp/tests tests/services/test_modules.py
```
`C2.py` (SQLite tmp db, accounts `viewer`, `user`, `controller`; one `PASS <check>` per check; final `C2 ok`; helper code in a sibling module, script <= 70 lines): the S2 constraint checks
rewritten on a CWP and an IWP subject (manual raise, five sources, refusals from `user` for the module sources, need-by arithmetic gone: `due_at` as given), `phase_not_gated`, suppress and
`suppressed`, `exists`, `resolves` and `targets` links, cleared_at before effective_at refused, envelope effective_at unaffected by the three fields, `viewer` refused; the guard blocks `ready` on an IWP with an open blocking `ready` constraint and
passes with an advisory one or after clear or withdraw, a CWP `start_execution` likewise, message has keys only; the five-reader walk on a constraint of a restricted correspondence item
(absent from every read and count for readers below the class), the no-target twin comparison; the three frozen functions from a module call; rebuild equals incremental.
Seed for later tickets: `--keep .accept/p2-i2.db` rebuilds the S2 seed (3 IWPs, 40 scope items, 2 pinned documents) plus 3 constraints (open manual, Assigned, Cleared) using core commands.

## Guards for S5 (name file:line; run no mutants here)
`phase_not_gated`; the guard's phase default; keys-only message; subject join (no copied class); suppress hash; module clear refusal for `manual`; `cleared_at` vs `effective_at`; the word row.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; pins; acceptance output (<= 5 lines per command); guards file:line; registry lines added; learnings.

## Commit
`P2-I2-C2: <imperative summary>`; body says what and why; end with the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: the join cannot be done without a copied class column; the engine cannot evaluate the guard without a viewer; a frozen signature must change; a registry change exceeds 10 lines.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
