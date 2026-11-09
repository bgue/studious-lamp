# P2-I5-S4b report: waive word, hold rule, worker word

## Deviations
- `MSG_WAIVE_WORD` is in `errors.py` as the spec says; it is raised as `ForbiddenError` (the word class), so the text is fixed and names `core.constraint.waive`. The constant `WAIVE_WORD` sits in `constraints/commands.py` next to `EDIT_WORD` (a path not listed in Allowed paths; two lines, no behaviour).
- `tl awp worker` had no `--actor`; it gains the standard `Actor` option (default dev) so the word can be asked of someone. The word is asked at company scope (the worker is not project scoped), so a project-only superuser (`user:sue`) is refused; company admin passes. Open question below.
- `waived` on `ConstraintView` is `field(default=False, kw_only=True)` so `ConstraintRow` (tl-api) and a tl-tui fake that builds rows keep compiling; `_build` always sets it.
- A new hold follower starts at the head of the outbox like `Follower` (no catch-up sweep): a constraint raised before the very first poll of a fresh ledger is not held.

## Core paths touched (for the APPROVALS line)
- `packages/tl-core/src/tl_core/constraints/handlers.py` (`require_waive`, call in `_clear`: not by_module, source check, after `require_edit` and `_load`)
- `packages/tl-core/src/tl_core/constraints/{errors.py,commands.py,queries.py}`
- access words: `core.constraint.waive` (asked in core), `awp.worker.run` (asked in `tl_cli/awp_run.py`); both already in `schema/settings/access-words.yaml` (S1), no schema change.
- awp: `readiness/hold_rule.py` (new), `handlers/signoff.py` (`_apply`, `hold_by_module`), `worker.py` (`Worker.hold`), `tl_cli/awp_run.py`.

## No new event, field or payload (D18)
The clear is the existing `Constraint.Cleared` with `suppress` true; `waived` is derived (state Cleared, source check, `suppress_hash` not null): no column, no key. The hold is the existing `IWP.Held` plus the `hold` transition.

## The three greps
- The word check precedes any read of the constraint's text: `_clear` loads only `_ROW_SQL` fields (no description); `require_waive` follows `_load`, so a hidden constraint answers `no record` before the word is asked (test `hidden constraint reads as missing`).
- `hold_rule.py` never calls `raise_by_module` or `raise_constraint` (pinned by a source test).
- Payload keys: the hold reads none (the constraint id is the outbox stream id; subject, phase and severity come from `cur_core_constraint`); it writes `IWP.Held` {`by`, `reason`}, both declared. `Constraint.Cleared` keys unchanged.

## Consequential pins
- `dev/accept/P2-I2/c2_checks.py`: person `waiver` with a `*` superuser grant (the word is a controller word); `test_constraint_commands.py::test_person_clear_keeps_suppress_hash...` clears as `waiver` (the only existing test that broke).
- `packages/tl-cli/tests/test_awp_run.py`: existing worker tests run `--actor user:ada`.
- `packages/tl-api/tests/test_auth_review.py` `AGENT_MAY_NOT`: `core.constraint.waive`, `awp.worker.run`.
- `docs/reference/openapi.json` regenerated (`waived` on `ConstraintRow`).
- `dev/seed/demo_project/constraints.py`: comment only (its check clear is by ADMIN, which holds the word); `test_demo_project_constraints.py` passes.
- Checked, no change: sim (client, testing, actors, iwp_planner test: fake client), `constraint_write.py`, `t04a_checks`, `s1_world` and `P2-I2.sh` (manual constraints), `access-words` table test. `tests/tools/proposable_exclusions.toml` does not exist: nothing added.

## Gates
`just check` ok; `S4b.py` prints `S4b ok`; gate-pg constraints 36 passed; gate readiness + test_awp_run 48 passed; gate test_iwp_planner 14 passed (`.gate/summary.txt`).

## Mutation
sentinel (remove the word check) killed; 5 of 5 killed: source-check branch flipped, word check before `_load`, Issued-only guard widened, constraint re-read at apply removed, worker word check removed. No survivors, no test added for a survivor.

## Open questions
- Scope of `awp.worker.run`: company (as built). Project controllers cannot run the worker; say if it should be per project.
