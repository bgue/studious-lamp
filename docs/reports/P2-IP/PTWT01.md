# Report — P2-PTW-T01 (harness id P2-IP-PTWT01)

Branch: `p2/ptw-t01-views`   Commit(s): one commit, final sha reported by the harness

## Deviations
BLOCKED, not done: the provided test cannot pass without editing it or changing S2 behaviour (see Open questions). Report path is the harness path `docs/reports/P2-IP/PTWT01.md`, not the ticket's Allowed path `docs/reports/P2-PTW/T01.md`. Worktree base is `7f2e512d` (harness), not `p2/ip-r3` (ticket); the harness says its branch supersedes the ticket Branch field.

## Changed files
- `packages/tl-modules/permits/src/tl_mod_permits/views.py` — bodies of `permit_list`, `permit_detail`, `permit_counts`, `permit_board`, `permits_for`, `export_rows`, plus private helpers; signatures and dataclasses unchanged.
- `packages/tl-modules/permits/tests/test_views.py` — byte-identical copy of `docs/tickets/P2-PTW/provided/T01_test_views.py`.
- `docs/reports/P2-IP/PTWT01.md` — this report.

## Commands and output
```
$ cmp docs/tickets/P2-PTW/provided/T01_test_views.py packages/tl-modules/permits/tests/test_views.py
(silent)
$ just check
0 errors, 1 warning, 0 informations
  tests/confidentiality/twin_channels.py:758:5 - warning: Expression value is unused (not in scope)
CHECK_EXIT=0
$ just gate packages/tl-modules/permits/tests/test_views.py
gate: FAIL
part 1: exit 1, 1 failed, 4 passed, 15 errors in 27.42s
```
Failure cause, all in the test's own setup: `IssuePermit` by `pam` at test line 107 (fixture `built`) and line 292 raises `RecordNotFoundError: no record with that id` from `handlers/common.py:111` (`load_record`, via `confidentiality.require_visible`). The permit's subject is restricted; `pam` is a superuser but not a controller, so it cannot read the subject.

Throwaway check (file deleted, not committed): the same copy with lines 107 and 292 changed from `"pam"` to `"ada"` gives `20 passed in 34.07s`, including the statement-count test (each view at most two statements). Before two view fixes it failed 10 of 20: Requested permits were missing (no state row) and precautions were read as dicts.

## Tests added
- `packages/tl-modules/permits/tests/test_views.py` — the 20 provided tests, unmodified. Not green on the trunk fixture (see Blocked).

## Learnings (proposed)
- A Requested permit has no `cur_workflow_state` row; `handlers.common.record_state` defaults it to Requested. Views must LEFT JOIN the state row and COALESCE, or Requested permits vanish from every list and count.
- `precautions_json` stores `{"id", "text"}` objects, not bare ids; a view that returns the raw list fails the "ticked precaution ids" contract.
- The ticket's stub and provided test assume a pam issue on a restricted subject succeeds; the handler's viewer rule says it cannot. The fixture and the rule disagree.

## Open questions / Blocked
Blocked on the provided test (`docs/tickets/P2-PTW/provided/T01_test_views.py`, lines 107 and 292). The ticket says do not edit the test and write the question here.
Question for the supervisor: should the fixture issue as a controller (ada or dora, and dora cannot issue a permit it requested, so ada), or should the issue rule for a restricted subject change? I did not change S2 handlers or the test. Decision needed before the gate can pass.
Also: the report path differs from the ticket's Allowed path; confirm which location the supervisor reads.
