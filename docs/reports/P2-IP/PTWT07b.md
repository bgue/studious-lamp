# Report — P2-PTW-T07b

Branch: `p2/ptw-t07b-api-iso-routes`   Commit(s): `c9c5fb9f` (feature), plus the gate-fix commit that revises this report (sha in `git log -1`)

## Deviations
- Agent expectation (ticket Tests 2): the ticket expects a closed 403 for an agent token. It does not get one: the routes use `document.read`, which the agent action set includes (as the T07 list does), so the agent gets 200 with restricted rows left out, and its detail is the unknown-key 404. A guard action would change `tl_core` (outside Allowed paths), so none was added. The test asserts 200/hidden. Needs a supervisor decision.
- Base and paths: the worktree was based on `ac81ec58` as the dispatch says (ticket header says `p2/ip-r3`). The report lives at the dispatch path `docs/reports/P2-IP/PTWT07b.md`, not the ticket's `docs/reports/P2-PTW/T07b.md`.
- Gate fix (this revision): the gate was red only because the `just check` exit status was unverified. Re-ran it: exit 0 (see below). No code changed in this commit.
- Pins changed as the ticket allows: `packages/tl-api/tests/expected/route_order.txt` (+4 lines), `docs/reference/openapi.json` (regenerated, additions only). `test_auth_review.py` and `openapi.baseline.json` untouched.

## Changed files
- `packages/tl-modules/permits/src/tl_mod_permits/routes.py` — `list_isolations`, `export_isolations`, `get_isolation` (before the T07 `{key}` route), `list_gas_tests` (after it). Same guard, `current_viewer()`, `ctx.backend(True)`. T07 routes unchanged.
- `packages/tl-api/tests/test_api_permit_iso.py` — new, 14 tests; reuses T07's `seed` and `Rig` by import.
- `packages/tl-api/tests/expected/route_order.txt`, `docs/reference/openapi.json` — pins (above).
- `docs/reports/P2-IP/PTWT07b.md` — this report.

## Commands and output
```
$ just check ; echo "exit $?"
0 errors, 1 warning, 0 informations   (warning: tests/confidentiality/twin_channels.py:758, pre-existing, not in Allowed paths)
generated files are up to date (1071 files)
event schemas are additive over the baseline
licences ok
exit 0
$ uv run ruff format --check packages/tl-modules/permits packages/tl-api/tests/test_api_permit_iso.py
50 files already formatted
$ uv run ruff check packages/tl-modules/permits packages/tl-api/tests/test_api_permit_iso.py
All checks passed!
$ uv run pyright packages/tl-modules/permits/src/tl_mod_permits/routes.py packages/tl-api/tests/test_api_permit_iso.py
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-api/tests/test_api_permit_iso.py   → part 1: exit 0, 14 passed in 8.67s / gate: PASS
$ just gate packages/tl-api/tests/test_api_permits.py      → part 1: exit 0, 12 passed in 7.26s / gate: PASS
$ just gate packages/tl-api/tests/test_module_hooks_api.py → part 1: exit 0, 9 passed in 12.68s / gate: PASS
```

## Tests added (`packages/tl-api/tests/test_api_permit_iso.py`)
- `test_no_token_is_401_on_every_new_route` — four paths, no token.
- `test_the_lowest_clearance_reader_gets_no_restricted_point` — list rows and `total` exclude the restricted point.
- `test_the_restricted_point_is_not_in_the_export` — csv export as uma vs dora.
- `test_a_restricted_isolation_answers_as_an_unknown_key_on_the_detail_route` — same 404 body as unknown key.
- `test_a_hidden_permit_has_no_gas_tests_as_an_unknown_permit` — same 404 body as unknown permit.
- `test_the_agent_reader_gets_no_restricted_point` — see Deviations.
- `test_the_view_word_is_checked_before_any_read` — 403 `forbidden` on all four routes.
- `test_the_fixed_isolation_paths_are_not_taken_for_a_key`, `test_the_export_rows_equal_the_list_rows`, `test_the_export_filters_reach_the_list_view`.
- `test_a_visible_permit_with_no_gas_test_is_an_empty_list` — 200 `[]`.
- `test_gas_tests_are_listed_newest_first_and_exported`.
- `test_bad_isolation_state_energy_format_and_limit_are_422`.
- `test_the_new_routes_are_in_the_openapi_document`.

## Learnings (proposed)
- API tests run the real clock in handlers; `RecordGasTest` rejects a future `taken_at`, so date gas tests from `datetime.now(UTC)`, not `world.at`.
- An isolation `Link` is refused for an Active or Lapsed permit; tests link to an Approved one.

## Open questions / Blocked
- Agent 403 vs 200 (Deviations): decide whether agents are closed on these routes (new guard action, needs a `tl_core` change) or read as the T07 list does.
- Gas-tests JSON uses `response_model=None` (union with `Response`), so OpenAPI shows no body schema. Confirm or ask for a typed response.
