# P2-I5-S4b — waive word on clearing a check-raised constraint, hold rule, worker word (S4 part B)

Status: ready, dispatch now (r4: plan check F1, F2, F11 applied; human gate, owner approver, and orchestrator APPROVALS before merge; independent of S3 and S4a)
Tier: builder
Kind: piece
Review: full
Labels: core, security, guard
Depends on: S1 (words `core.constraint.waive` controller, `awp.worker.run` controller, `awp.iwp.hold` controller); S2 not needed
Branch: `p2/i5-s4b-waive-hold`
Worktree: `/home/user/wt/i5-s4b`
Approver: human gate (core constraint handler, words `core.constraint.waive` and `awp.worker.run`), the owner is the approver; orchestrator APPROVALS also (access words, guard); security rows S4 B of the README SR3 list

## Goal
Three changes, each small. (1) A person clears a constraint that a check raised only if they hold `core.constraint.waive`; the reason stays required (cap 300) and the cleared constraint reads as waived. (2) A blocking constraint raised on an Issued IWP puts the IWP On hold, run by the awp follower worker
(closes P2-I2 Q1). (3) `tl awp worker` needs the word `awp.worker.run`.

## Brief references (pasted)
- D6: no `WaiveConstraint` command and no new event. `handle_clear_constraint` -> `_clear(by_module=False)` (`tl_core/constraints/handlers.py`) already keeps `suppress_hash` when a person clears a `source == check` constraint (payload `suppress: true`). That case is exactly "waived".
- D9: hold rule: follower worker, Issued only, state re-checked when applied, idempotent on replay, `by_module`. It must not run inside the raise (loop).
- Modules clear their own constraints through `clear_by_module` and are never asked for the word. Manual-source constraints are cleared with `core.constraint.edit` as before.

## Interfaces to build
```python
# tl_core/constraints/handlers.py   in _clear, after require_edit and _load, for not by_module and held.source == SOURCE_CHECK:
#   require the word core.constraint.waive on the project (same call pattern as require_edit); refusal text MSG_WAIVE_WORD (errors.py), fixed, names the word
# tl_core/constraints/queries.py   the constraint read row gains `waived: bool` (additive, default False): state Cleared and source check and suppress_hash not null. No new payload key, no column.
# tl_mod_awp/readiness/hold_rule.py (new)
class HoldFollower:  # same shape as readiness/follow.py Follower; cursor name "awp.hold" in rule_cursor; poison after 3 like the Follower
    def poll(self) -> int          # holds applied
def hold_by_module(uow, iwp_id: str, reason: str) -> bool   # shared with handle_hold_iwp (extract, no behaviour change); False when not applicable
# tl_cli/awp_run.py   `worker` runs both followers in its loop and refuses a caller without awp.worker.run (fixed text)
```
Hold rule: on an outbox event `Constraint.Raised` whose subject is an IWP and whose severity is the one `guards`' `no_open_blocking_constraints` counts as blocking (reuse that predicate, do not copy it): in its own unit of work re-read the IWP state; only `Issued` moves to On hold
(Ready and In progress are not touched: D9); reason text `blocking constraint raised: <constraint key>` (cap 300); actor `svc:awp.hold`, source `job:awp.hold`; a replay of the same event finds On hold and changes nothing; a constraint raised and cleared before the follower runs still holds only if it is open when applied (re-read the constraint state too).
No new event type and no new payload key (the move is the existing `IWP.Held` path); say so in the report.

## Context (<= 12 files)
`packages/tl-core/src/tl_core/constraints/{handlers,errors,queries,guard}.py`; `packages/tl-modules/awp/src/tl_mod_awp/{guards.py,handlers/signoff.py (`handle_hold_iwp` at line 207 and `_held`),readiness/follow.py,worker.py (build_worker)}`; `packages/tl-cli/src/tl_cli/awp_run.py`; `schema/settings/access-words.yaml` (read);
`packages/tl-core/tests/constraints/test_constraint_commands.py`; `packages/tl-cli/src/tl_cli/constraint_read.py` lines 45-60 (the CLI word check: copy its `require_word(conn, holder_for_actor(conn, actor), scope=, module=, word=normalise_word(...), what=...)` call and its `ForbiddenError` handling for `awp.worker.run`; if the shape does not fit a non-command verb, escalate with the smallest shape that works).

## Allowed paths
- `packages/tl-core/src/tl_core/constraints/{handlers.py,errors.py,queries.py}`
- `packages/tl-modules/awp/src/tl_mod_awp/{readiness/hold_rule.py (new),handlers/signoff.py (extract only: `hold_by_module` out of `_held`/`handle_hold_iwp`),worker.py (wire the follower)}`
- `packages/tl-cli/src/tl_cli/awp_run.py`
- tests: `packages/tl-core/tests/constraints/{test_constraint_waive.py (new),test_constraint_commands.py (consequential)}`, `packages/tl-modules/awp/tests/readiness/test_hold_rule.py` (new), `packages/tl-cli/tests/test_awp_run.py`
- **consequential pins, updated here and listed in the report (the old form stays pinned for a holder of the word and for a manual or module clear):** every test, script or seed that clears a check-raised constraint as an ordinary user: `grep -rln "ClearConstraint\|constraint clear" packages tests dev` found `packages/tl-core/tests/constraints/test_constraint_commands.py`,
  `packages/tl-sim/src/tl_sim/{client,testing}.py` and `actors/{base,iwp_planner}.py`, `packages/tl-sim/tests/test_iwp_planner.py`, `packages/tl-cli/src/tl_cli/constraint_write.py` (help text only), `dev/seed/demo_project/constraints.py`, `dev/accept/P2-I2/{t04a_checks,c2_checks}.py`, `dev/accept/P2-INS/s1_world.py`; re-grep and add `core.constraint.waive` to the actor that needs it (a grant in the seed or fixture), never loosen the word
- pinned lists as the union, listed in the report: access-word tables and agent `AGENT_MAY_NOT` (add `core.constraint.waive`, `awp.worker.run` if that list exists), `tests/tools/proposable_exclusions.toml` (`ClearConstraint` line with the reason `a waived clear is a person's act`, if the file exists and lacks it)
- `docs/reference/openapi.json` (regenerated: `python -m tl_api.openapi`, if the clear route text changes) and `packages/tl-api/tests/test_auth_review.py` (`AGENT_MAY_NOT` gains the two words if that set lists words; consequential pin, listed in the report; plan check F2)
- `dev/accept/P2-I5/S4b.py`, `docs/reports/P2-I5/S4b.md` (create)
Not allowed: schema, other modules, `tl-api` source, `tl-tui`, `tl-mcp`, `docs/reference` pages other than `openapi.json` (a changed message that a reference page pins is a consequential pin: list it and stop for the orchestrator).

## Acceptance (run once each)
```
just check
uv run python dev/accept/P2-I5/S4b.py
just gate packages/tl-core/tests/constraints
just gate packages/tl-modules/awp/tests/readiness packages/tl-cli/tests/test_awp_run.py
just gate packages/tl-sim/tests/test_iwp_planner.py
```
`S4b.py` (SQLite, dialect-neutral; helper `check(name, ok)` prints `PASS <name>` only when true, else exits 1; final `S4b ok`): a plain user clearing a check-raised constraint is refused with `MSG_WAIVE_WORD`; the same person with the word and a reason clears it and the read row has `waived` true; an empty reason and a 301-character reason are refused; a manual constraint still clears with
`core.constraint.edit` alone and reads `waived` false; a module clear of a check constraint needs no word and reads `waived` false; an agent actor is refused the word; the waived clear keeps the suppress hash (the check does not re-raise on the next evaluation);
a blocking constraint raised on an Issued IWP holds it after one `HoldFollower.poll()`, a second poll and a replay of the same outbox rows change nothing, an IWP in Ready, In progress or On hold is untouched, a constraint cleared before the poll holds nothing, and a non-blocking severity holds nothing; `tl awp worker --once` without `awp.worker.run` is refused with the fixed text.

## Tests to add
- `packages/tl-core/tests/constraints/test_constraint_waive.py`: the first block above, plus rebuild equality of `cur_core_constraint` after a waived clear.
- `packages/tl-modules/awp/tests/readiness/test_hold_rule.py`: the second block, plus rebuild equality of `cur_awp_iwp` and `cur_core_record` after a hold, and "the hold does not raise a constraint and does not loop" (event count stable after three polls).
- `packages/tl-cli/tests/test_awp_run.py`: the worker word.

## Report requirements
Deviations first; <= 60 lines; consequential pins listed; the three `grep` answers (the word check precedes any read of the constraint's text; `hold_rule.py` never calls `raise_by_module`; payload keys written by the hold vs declared); mutation: sentinel plus <= 5 (the word check, `source == check` branch, Issued-only guard, re-read of state at apply, the severity predicate) in 3 lines.
## Escalation triggers
`waived` cannot be derived without a column or payload key; the CLI has no word-check pattern for a verb; a hold needs a new event; more than ~15 consequential test files break; a frozen contract change.
## Blocked
(builder writes here)
## Decision
(supervisor or orchestrator writes here)
