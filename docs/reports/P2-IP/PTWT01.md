# Report - P2-PTW-T01 (harness id P2-IP-PTWT01)

Branch: `p2/ptw-t01-views`   Commit(s): see the branch log

## Deviations
- Amendment 1: the provided test issues the restricted-subject permits as `ada` (a controller), not `pam`, because `pam` cannot read a restricted subject. S2 handlers are unchanged.
- Review fix: the shown state is built in `_row` by `rules.effective_state`. The SQL CASE (`_SHOWN`) stays only for the state filter, the counts and the board split.
- `permits_for` has no `now` and returns the stored state by contract (`PermitRef`), so it is unchanged.
- Report path is the harness path `docs/reports/P2-IP/PTWT01.md`. Worktree base is the harness one.

## Changed files
- `packages/tl-modules/permits/src/tl_mod_permits/views.py` - view bodies; `_row(raw, now)` uses `rules.effective_state`.
- `packages/tl-modules/permits/tests/test_views.py` - the provided tests with Amendment 1 (ada issues).
- `packages/tl-modules/permits/tests/test_views_lapse.py` - the SQL filter and `rules.effective_state` agree for valid_until == now, NULL, past, future.
- `docs/reports/P2-IP/PTWT01.md` - this report.

## Commands and output
```
$ just gate packages/tl-modules/permits/tests/test_views.py packages/tl-modules/permits/tests/test_views_lapse.py packages/tl-modules/permits/tests/test_rules.py
part 1: exit 0, 88 passed
gate: PASS
```
ruff format and check clean; pyright on the touched files: 0 errors.

## Learnings (proposed)
- A Requested permit has no `cur_workflow_state` row; views LEFT JOIN and COALESCE to Requested.
- `precautions_json` stores `{"id", "text"}` objects; views return the ids.
- Keep the lapse rule in one place (`rules.effective_state`); a SQL copy needs an agreement test.

## Open questions / Blocked
None.
