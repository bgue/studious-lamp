# Report — P2-INSP-T06

Branch: `p2/insp-t06-api-routes`   Commit(s): see the commit on the branch (report and code in one commit)

## Deviations
`docs/reference/openapi.json` is regenerated (in Allowed paths): five paths and six schemas, plus reordered existing schema entries that are generator output. `docs/reference/openapi.baseline.json` is NOT regenerated (`--baseline` is a release step; `--compat` passes without it).
Commit subject follows the dispatch (`P2-IP-INSPT06: ...`), not the ticket's `P2-INSP-T06: ...`.

## Changed files
- `packages/tl-api/src/tl_api/routes/insp.py` (new) — five GET routes on `router`; each one calls one `insp_views` function under `current_viewer()`; `ValueError` from the views maps to 422 `invalid_argument`; missing, hidden and other-project keys give 404 `record_not_found` with `no inspection` / `no checklist`.
- `packages/tl-modules/quality/src/tl_mod_quality/module.py` — `read_routers` gets `"tl_api.routes.insp:router"` appended (one line).
- `packages/tl-api/tests/test_api_insp.py` (new) — 15 tests (see below).
- `packages/tl-api/tests/expected/route_order.txt` — five lines added after the punch routes.
- `docs/reference/openapi.json` — regenerated (5 new paths, 6 new schemas).
- `docs/reports/P2-IP/INSPT06.md` — this report.

## Commands and output
```
$ uv run ruff format --check <3 files>
3 files already formatted
$ uv run ruff check <3 files>
All checks passed!
$ uv run pyright <3 files>
0 errors, 0 warnings, 0 informations
$ just gate packages/tl-api/tests/test_api_insp.py
part 1: exit 0, 15 passed in 10.10s
gate: PASS
$ just gate packages/tl-api/tests/test_module_hooks_api.py
part 1: exit 0, 9 passed in 16.22s
gate: PASS
$ just gate packages/tl-api/tests/test_openapi_baseline.py   (extra, not in Acceptance)
gate: PASS
$ uv run python -m tl_api.openapi --compat
(no output, exit 0)
```

## Tests added
- `test_api_insp.py::test_the_five_routes_are_registered` — five paths and operation ids in OpenAPI.
- `test_api_insp.py::test_no_token_is_401_on_every_route` — no token is 401.
- `test_api_insp.py::test_a_person_without_quality_view_gets_403_before_any_read` — a user whose word is withdrawn gets 403 `forbidden`; no view runs (patched to raise).
- `test_api_insp.py::test_every_reader_gets_the_checklist_routes` — all five readers see both checklists.
- `test_api_insp.py::test_the_lowest_reader_sees_no_restricted_inspection` — no row, `total` excludes it, detail 404.
- `test_api_insp.py::test_the_cleared_reader_and_the_admin_see_the_restricted_inspection`.
- `test_api_insp.py::test_a_hidden_inspection_answers_as_an_unknown_key` — hidden and unknown keys: same status and body.
- `test_api_insp.py::test_a_hidden_inspection_is_not_counted_or_exported`.
- `test_api_insp.py::test_the_list_filters_each_reach_the_view` — state, point, inspector and subject filters.
- `test_api_insp.py::test_the_list_limit_bounds_the_rows_and_total_counts_the_matches`.
- `test_api_insp.py::test_the_detail_carries_the_answers_of_a_done_inspection` — answers, punch keys.
- `test_api_insp.py::test_export_rows_equal_the_list_rows_in_csv_and_jsonl` — content types and keys.
- `test_api_insp.py::test_export_is_not_read_as_a_key`.
- `test_api_insp.py::test_a_bad_state_or_point_is_422` (also export format and checklist state).
- `test_api_insp.py::test_a_limit_above_the_maximum_is_422` (also limit 0).

## Learnings (proposed)
- `schema/settings/module-roles.yaml` derives the module `user` role for every account role, so every non-admin account holds `quality.view`. A 403 "no word" test needs the word withdrawn (patch `module_roles.holds_word` for one actor, as `test_api_requisitions.py` does); an account with no role cannot be created (`InvalidAccountError`).
- `insp_world.py` imports `punch_world` by name, so a test that loads it by path must load `punch_world` first.

## Open questions / Blocked
- The ticket names five readers as "no clearance, cleared, restricted subject, company admin, agent token". I read "restricted subject" as no separate reader class and used `vera` (a viewer grant) in its place; the restricted-subject case is covered by the hidden-inspection tests. Confirm, or name the reader you want.
- Baseline `docs/reference/openapi.baseline.json` left unchanged (release step). Say if the supervisor wants it refreshed in this ticket.
