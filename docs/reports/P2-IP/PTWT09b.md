# Report — P2-PTW-T09b (dispatched as P2-IP-PTWT09b)

Branch: `p2/ptw-t09b-card-lines`   Commit(s): code `6eba7ecb`; this report is the next commit on the branch (`git log -1`)

## Deviations
- Commit subject uses the ticket ID `P2-PTW-T09b:` (AGENTS.md rule 9 and the ticket's Report requirements), not the dispatch's `P2-IP-PTWT09b:`.
- Report path is `docs/reports/P2-IP/PTWT09b.md` (dispatch and Allowed paths), not the ticket's header path.
- Statement-count test skipped: `test_views.py` has no statement-count helper. (`test_lapse_job.py` has a `before_cursor_execute` spy, but the ticket names `test_views.py` and says to skip if none.)

## Changed files
- `packages/tl-modules/permits/src/tl_mod_permits/scan_card.py` — `_gas_value` and `_isolation_value` read `iso_views.gas_tests_for` and `iso_views.isolation_list` plus `guards.linked_isolations`; `_lines(detail, gas, isolations)` and `_card(detail, now, gas, isolations)` take the values; `card()` computes them inside the viewer context.
- `packages/tl-modules/permits/tests/test_scan_card.py` — one exact-lines assertion updated (`test_lines_are_bounded_and_a_missing_value_is_left_out` now expects `"Gas test": "none taken"`); eight tests added.
- `docs/reports/P2-IP/PTWT09b.md` — this report.

## Commands and output
```
$ uv run ruff format --check <scan_card.py> <test_scan_card.py>
2 files already formatted
$ uv run ruff check <scan_card.py> <test_scan_card.py>
All checks passed!
$ uv run pyright <scan_card.py> <test_scan_card.py>
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-modules/permits/tests/test_scan_card.py packages/tl-modules/permits/tests/test_iso_views.py tests/contract/test_scan_card_contract.py
part 1: exit 0, 48 passed in 26.35s
gate: PASS
```
Extra, not in Acceptance: `uv run pytest test_scan_card.py -k "gas or isolation or full_card or hidden"` gave `8 passed, 17 deselected`.

## Tests added
- `test_scan_card.py::test_no_gas_test_reads_none_taken_and_a_pass_is_shown_with_its_time` — `none taken`, then `Pass at 07:00 UTC` after a real RecordGasTest.
- `::test_the_newest_gas_test_decides_and_a_failure_suspends_the_permit` — `Fail at 07:02 UTC` is newest; banner `SUSPENDED`/stop; state Suspended.
- `::test_no_linked_isolation_means_no_isolations_line` — no line when none linked.
- `::test_the_isolation_line_counts_the_verified_of_the_linked` — `0 of 1`, `1 of 2`, `2 of 2 verified`.
- `::test_the_isolation_count_follows_an_unlink` — `1 of 2` then `1 of 1` after UnlinkIsolation.
- `::test_a_hidden_isolation_counts_in_neither_number_and_its_text_is_never_shown` — lowest viewer `1 of 1`, cleared `1 of 2`, "Secret" absent from card JSON.
- `::test_a_permit_hidden_for_the_viewer_is_still_none_with_the_new_lines` — hidden permit still None.
- `::test_a_full_card_with_every_optional_line_stays_within_the_bound` — exactly 8 lines in order, `<= MAX_LINES`.

## Learnings (proposed)
- A failing gas test only suspends a permit that is Active or Lapsed, so a failure test needs an issued permit first (`live_hot` pattern in `test_gas_commands.py`). A ticket that says "a later failing one" should state the required state.
- `permit_world.World.isolation(permit)` and `World.link` append events directly and bypass the link command guards; use `world.call("uma", "LinkIsolation", ...)` where the command path matters.

## Open questions / Blocked
- `_isolation_value` calls `iso_views.isolation_list(..., limit=500)`, as the ticket says. A scope with more than 500 isolations would undercount `m` silently. The ticket does not say what to do there; accepted as written, flagged for the supervisor.
- None blocking. Whole suite and `just check` not run, per the ticket.
