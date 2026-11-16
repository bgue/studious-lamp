# Report — P2-PTW-T07b

Branch: `p2/ptw-t07b-api-iso-routes`   Commit(s): the single commit that adds this report (sha in `git log -1`)

## Deviations
- Agent expectation (ticket Tests 2): the ticket expects an agent token to get a closed 403 on the new routes. It does not: the routes use `document.read`, which is in the agent action set (as the T07 list is), so the agent gets 200 with the restricted rows left out, and its detail is the unknown-key 404. Adding a guard action would have changed `tl_core` (outside Allowed paths), and the ticket says no new guard action, so none was added. The test asserts the 200/hidden behaviour. Needs a supervisor decision.
- Base: the worktree was created from `ac81ec58` as the dispatch says, not from `p2/ip-r3` as the ticket header says. T02 (`iso_views.py`) and T07 (`routes.py`) are present at that base.
- Commit trailer: the model named in the trailer is Haiku 5.5 (my own model), not "Opus 5.5" as the dispatch text says.
- Pins changed as the ticket allows: `packages/tl-api/tests/expected/route_order.txt` (+4 lines) and `docs/reference/openapi.json` (regenerated with `uv run python -m tl_api.openapi`; only additions). `test_auth_review.py` not changed (no guard action). `openapi.baseline.json` not touched.

## Changed files
- `packages/tl-modules/permits/src/tl_mod_permits/routes.py` — four routes added: `list_isolations`, `export_isolations`, `get_isolation` (declared before the T07 `{key}` route), `list_gas_tests` (after it). Same `_view_reader` guard, `current_viewer()`, `ctx.backend(True)`. T07 routes unchanged.
- `packages/tl-api/tests/test_api_permit_iso.py` — new, 14 tests; reuses T07's `seed` and `Rig` by import, extends the ledger with real commands.
- `packages/tl-api/tests/expected/route_order.txt` — 4 lines inserted in declaration order.
- `docs/reference/openapi.json` — regenerated.
- `docs/reports/P2-IP/PTWT07b.md` — this report.

## Commands and output
```
$ uv run ruff format --check packages/tl-modules/permits packages/tl-api/tests/test_api_permit_iso.py
50 files already formatted
$ uv run ruff check packages/tl-modules/permits packages/tl-api/tests/test_api_permit_iso.py
All checks passed!
$ uv run pyright packages/tl-modules/permits/src/tl_mod_permits/routes.py packages/tl-api/tests/test_api_permit_iso.py
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-api/tests/test_api_permit_iso.py
part 1: exit 0, 14 passed in 8.15s
gate: PASS
$ just gate packages/tl-api/tests/test_api_permits.py
part 1: exit 0, 12 passed in 6.45s
gate: PASS
$ just gate packages/tl-api/tests/test_module_hooks_api.py
part 1: exit 0, 9 passed in 13.60s
gate: PASS
```
Extra (not in Acceptance, one targeted run): `just gate packages/tl-api/tests/test_auth_review.py` → `part 1: exit 0, 31 passed`, `gate: PASS`. `uv run python -m tl_api.openapi --check` passes after regeneration.

## Tests added (`packages/tl-api/tests/test_api_permit_iso.py`)
- `test_no_token_is_401_on_every_new_route` — the four paths, no token.
- `test_the_lowest_clearance_reader_gets_no_restricted_point` — list rows and `total` exclude the restricted point's isolation.
- `test_the_restricted_point_is_not_in_the_export` — csv export as uma vs dora.
- `test_a_restricted_isolation_answers_as_an_unknown_key_on_the_detail_route` — same 404 body as an unknown key.
- `test_a_hidden_permit_has_no_gas_tests_as_an_unknown_permit` — same 404 body as an unknown permit.
- `test_the_agent_reader_gets_no_restricted_point` — see Deviations.
- `test_the_view_word_is_checked_before_any_read` — 403 `forbidden` on all four routes; no view runs.
- `test_the_fixed_isolation_paths_are_not_taken_for_a_key`, `test_the_export_rows_equal_the_list_rows` (csv and jsonl), `test_the_export_filters_reach_the_list_view`.
- `test_a_visible_permit_with_no_gas_test_is_an_empty_list` — 200 `[]`.
- `test_gas_tests_are_listed_newest_first_and_exported` — order, csv, jsonl.
- `test_bad_isolation_state_energy_format_and_limit_are_422`.
- `test_the_new_routes_are_in_the_openapi_document`.

## Learnings (proposed)
- Clock: API tests run the real clock in the handlers. `RecordGasTest` rejects a future `taken_at` against it, so tests must date gas tests from `datetime.now(UTC)`, not `world.at`.
- `Link` of an isolation is refused for an Active or Lapsed permit; the test links to an Approved one.
- `jsonable_encoder` turns a `Decimal` reading into a JSON number (`20.90` becomes `20.9`), while the export text keeps the exact decimal. Not covered by a test here.

## Open questions / Blocked
- Agent 403 vs 200 (Deviations): please decide whether the agent should be closed on these routes (a new guard action, which needs a `tl_core` change outside this ticket) or read as the T07 list does.
- Gas-tests JSON: the route uses `response_model=None` because the return is a union with `Response`; OpenAPI therefore shows no body schema for it, and readings are JSON numbers. Confirm this is acceptable or ask for a typed response.
- Export `limit`: the isolation export uses `iso_views.MAX_LIMIT` (500) rather than the list default of 100, so export and list agree up to 500 rows.
