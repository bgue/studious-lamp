# Report — P2-INSP-T08

Branch: `p2/insp-t08-client`   Commit(s): the single commit on the branch (code and report together; sha in the return message)

## Deviations
- Report written to `docs/reports/P2-IP/INSPT08.md` as the dispatch names it, not `docs/reports/P2-INSP/T08.md` (the ticket's Allowed path). Same convention as INSPT06.
- Commit subject is `P2-IP-INSPT08: ...` as the dispatch names it, not the ticket's `P2-INSP-T08: ...`.
- Base is `81f62b46` per the dispatch, not `p2/ip-r3` as the ticket says. The dispatch says it supersedes.
- `packages/tl-tui/tests/fakes_punch.py` is untouched (outside Allowed paths). The insp fake's `quality_command` sits ahead of the punch mixin in `FakeClient`'s bases. It sends punch names to the punch mixin's own function, unchanged, and handles the eleven inspection names itself. Both record in `punch_commands`.
- No pins changed: `test_client_roundtrip.py`, `test_remote_client.py` passed as they are. `test_client_module_roles.py` was not run (not in Acceptance, not needed).

## Changed files
- `packages/tl-api/src/tl_api/client/quality.py` — `list_inspections`, `get_inspection`, `list_checklists`, `get_checklist` decoded with `TypeAdapter`; `quality_command` widened from `PUNCH_COMMANDS` to `QUALITY_COMMANDS`.
- `packages/tl-tui/src/tl_tui/client.py` — the four reads on `ClientInterface` (after the punch block); `quality_command` doc says `QUALITY_COMMANDS`.
- `packages/tl-tui/src/tl_tui/embedded.py` — the four reads call `insp_views` under `current_viewer()` after `_require_punch_view`; missing key raises the route texts; `quality_command` uses `QUALITY_COMMANDS`.
- `packages/tl-tui/tests/fakes_insp.py` (new) — `FakeInspSupport`, `load_inspections`, `load_checklists`, the four reads with view filters, widened door, `seed_inspections`.
- `packages/tl-tui/tests/fakes.py` — import, base (before `FakePunchSupport`), `_init_insp()` call.
- `tests/api/test_client_insp.py` (new) — 28 tests across the parametrized cases.
- `packages/tl-tui/tests/test_fakes_insp.py` (new) — 18 tests.

## Commands and output
```
$ uv run ruff format --check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_insp.py
450 files already formatted
$ uv run ruff check packages/tl-api/src/tl_api/client packages/tl-tui tests/api/test_client_insp.py
All checks passed!
$ uv run pyright <6 files>
0 errors, 0 warnings, 0 informations
$ just gate tests/api/test_client_insp.py packages/tl-tui/tests/test_fakes_insp.py
part 1: exit 0, 28 passed in 24.47s
gate: PASS
$ just gate tests/api/test_client_punch.py packages/tl-tui/tests/test_fakes_punch.py tests/api/test_client_roundtrip.py packages/tl-tui/tests/test_remote_client.py
part 1: exit 0, 27 passed in 29.78s
gate: PASS
```
An earlier gate run failed one punch fake test (`PUN-1` expected) because the insp door shadowed the punch door. Fixed by delegation (see Deviations). The final run above is after the fix.

## Tests added
- `tests/api/test_client_insp.py::test_the_four_reads_give_equal_answers_on_both_clients` (4 readers) — embedded and `ApiClient` agree.
- `…::test_the_command_door_plans_schedules_and_records_through_both` — Plan, Schedule, Record through both; next read shows state.
- `…::test_the_recorder_may_not_verify_through_either_client` — `MSG_SELF_VERIFY` on both.
- `…::test_a_missing_key_is_one_not_found_text_on_both` / `…::test_a_missing_checklist_is_the_checklist_not_found_text_on_both`.
- `…::test_the_lowest_clearance_reader_does_not_see_the_restricted_inspection` — absent from rows and total (4); detail raises for `uma`, visible to `dora`.
- `…::test_a_punch_command_still_runs_through_the_same_door`.
- `packages/tl-tui/tests/test_fakes_insp.py` — seed counts and key order, each filter (parametrized), limit vs total, checklist filters, bad state/point `ValueError`, missing key texts, detail, command door recorded, unknown or wrong-class name forbidden.

## Learnings (proposed)
- The T06 routes take `project` as a query parameter (`/quality/inspections?project=…`), not a path segment. The ticket's interface does not say so. The client follows the routes.
- A fake mixin placed ahead of another in `FakeClient`'s bases shadows the other's method. Calling the shadowed function explicitly (`FakePunchSupport.quality_command(...)`) keeps its behaviour. Calling through `self` recurses.

## Open questions / Blocked
none
