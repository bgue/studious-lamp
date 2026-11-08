# Report — P2-I2-TW2

Branch: `p2/i2-tw2-web`   Commit(s): `0849073 TW2: add the constraint log page on the web` (report commit follows)

## Deviations
- Trailer names Claude Haiku 5.5, my own model (the dispatch text said Opus 5.5). Nothing else outside scope.
- The two constraint mirrors do not go through `guard_action`: the routes nest `guard(core.constraint.view)` in the `Reader` dependency, so `guard_action` returns `None`. `WebReadClient._call_viewed` runs the same authorizer checks, then the route's own access-word check (`_view_reader`), so the web refuses what the API refuses.
- `tl_web` may not import `tl_core` beyond `tl_core.auth`, so the word (`"core.constraint.view"`) and the read limit (`MAX_ROWS = 500`) are spelled out in the web code and pinned by `test_the_literals_of_the_web_client_are_the_core_constants`.
- `?subject=` is read from `request.query_params` in `load_rows`, not declared as a route parameter. The panel and Open links do not carry it; the panel finds its row in the unfiltered list.
- The summary counts blocking and aging in the page (as `ConstraintScreen.summary_text` does); the text module has no count function and it may not change.
- The `(first 500 only)` note is set when `total > rows held`, per the ticket, not only when grouped (the page has no groups yet).

## Changed files
- `packages/tl-web/src/tl_web/pages/constraints.py` (new) — `ConstraintWebLog`, `register("constraints")`, `GET /p/{project}/constraints`.
- `packages/tl-web/tests/test_web_TW2.py` (new) — 16 tests: rows, headers, summary, empty, subject, panel, filter, not-found 404, readers, agent 401, real world.
- `packages/tl-web/src/tl_web/reads.py` — import, two `MIRRORS` lines, `_call_viewed`, `list_constraints`, `get_constraint`.
- `packages/tl-web/src/tl_web/present.py` — `constraint_text` in the import list and `__all__`.
- `packages/tl-web/src/tl_web/routers.py` — `tl_web.pages.constraints` in `PAGE_MODULES`.
- `packages/tl-web/tests/walk.py` — TW2 row for the log (its panel probes come from `_panels`).
- `packages/tl-web/tests/test_web_imports.py` — same module in `PAGE_MODULES`.
- `packages/tl-web/tests/test_web_reads_mirror.py` — count pin 45 to 47, `get_constraint` in `ABSENT`, two cases.

Pins (union form): `routers.PAGE_MODULES`, `test_web_imports.PAGE_MODULES`, `walk.WALK` row, `MIRRORS` 45 to 47.

## Commands and output
```
$ NODE_OPTIONS=--max-old-space-size=6144 just check      (exit 0)
All checks passed!
2352 files already formatted
0 errors, 0 warnings, 0 informations
generated files are up to date (843 files)
licences ok

$ just gate packages/tl-web/tests/test_web_TW2.py packages/tl-web/tests/test_web_imports.py packages/tl-web/tests/test_web_confidentiality_walk.py packages/tl-web/tests/test_web_reads_mirror.py   (exit 0)
part 1: exit 0, 82 passed in 118.11s (0:01:58)
gate: PASS

$ uv run python -m pytest -q packages/tl-web/tests/test_web_TW2.py
16 passed in 2.46s
```

## Tests added
- `packages/tl-web/tests/test_web_TW2.py::test_the_rows_and_headers_equal_the_text_module` — rows equal `constraint_cells`, log regions present.
- `::test_every_person_reader_sees_the_same_rows` (boss, ctl, bob, amy) and `::test_the_agent_is_refused_the_page` (401).
- `::test_the_status_line_is_the_summary`, `::test_an_empty_list_has_the_empty_summary`, `::test_a_subject_keeps_one_subjects_constraints`.
- `::test_the_panel_of_one_constraint_is_its_page_as_plain_lines`, `::test_the_filter_and_an_unknown_key`.
- `::test_a_read_that_says_not_found_is_the_same_404` — hidden and missing panels are byte-identical.
- `::test_the_real_world_has_an_empty_constraint_log` — unpatched world, empty table, 404 panel.
- `::test_the_literals_of_the_web_client_are_the_core_constants` — the two spelled-out constants match `tl_core`.

## Learnings (proposed)
- `guard_action` only sees a direct `guard(...)` on the `actor` parameter. A route whose guard sits inside a shared dependency (`Reader = Annotated[str, Depends(_view_reader)]`) is invisible to it; a mirror then skips the authorizer unless it calls the checks itself.
- Pyright (`reportPrivateImportUsage`) rejects `tl_api.routes.constraints.MAX_LIMIT` and `VIEW_WORD` as re-exports; import them from `tl_core` where allowed, or spell them out.
- `ConstraintList` and other pydantic models take keyword arguments only; a test lambda that builds one positionally fails at runtime.

## Open questions / Blocked
none. The web now enforces the route's access-word check (the stricter `require_word` model), the same as the embedded client.
