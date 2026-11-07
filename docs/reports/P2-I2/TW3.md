# Report — P2-I2-TW3

Branch: `p2/i2-tw3-web`   Commit(s): `TW3: add the readiness page on the web` (report commit follows; final sha in the return value)

## Deviations
- Not-evaluated answer: the ticket asks for `not_evaluated_text` and for a missing number to answer the 404 page (140). The route answers 404 for both. The page reads `get_iwp` (already mirrored) after a `record_not_found` from the readiness read: a visible, never-evaluated IWP shows the text (200); a missing or hidden one raises from `get_iwp` and is the 404 page. See Open questions.
- Panel route: `tl_web/log.py`'s panel route has no query, so the readiness log takes the IWP number from its path (`row_for` sets it). No edit to `log.py`.
- The page does not load labels (the terminal's `ReadinessScreen` passes none to `readiness_rows`).
- No Enter-to-open: `row_open_key` is `None`, so no Open link. A reference is text.
- Trailer names the implementer's own model, not the one the dispatch text named (the dispatch and the harness disagreed; the harness attribution was used). Commit subject uses the dispatch's `TW3:` prefix, as TW2 did.

## Changed files
- `packages/tl-web/src/tl_web/pages/readiness.py` (new) — `ReadinessWebLog` (a `WebLog`), `register("readiness")`, `GET /web/p/{project}/readiness?number=`.
- `packages/tl-web/tests/test_web_TW3.py` (new) — 18 tests: rows, headers, regions, status, panel, filter, not evaluated, hidden vs unknown vs no number (404, byte-identical), person readers, agent 401, no action or record link, real world.
- `packages/tl-web/src/tl_web/present.py` — `readiness_text` in the import list and `__all__`.
- `packages/tl-web/src/tl_web/reads.py` — `MIRRORS["get_iwp_readiness"]` and the method `get_iwp_readiness` (via `awp_routes.get_iwp_readiness`).
- `packages/tl-web/src/tl_web/routers.py` — `tl_web.pages.readiness` appended to `PAGE_MODULES`.
- `packages/tl-web/tests/test_web_imports.py` — same module in `PAGE_MODULES`.
- `packages/tl-web/tests/walk.py` — TW3 row (`_readiness` builder: the record's number as the IWP number, 404 both sides).
- `packages/tl-web/tests/test_web_reads_mirror.py` — count pin 47 to 48, `get_iwp_readiness` in `ABSENT` and in `cases`.

Pins (union form): `routers.PAGE_MODULES` and `test_web_imports.PAGE_MODULES` (+ `tl_web.pages.readiness`); `walk.WALK` (+ readiness row); `MIRRORS` 47 to 48 (+ `get_iwp_readiness`); `ABSENT` (+ `get_iwp_readiness`).

## Commands and output
```
$ uv run python -m pytest -q packages/tl-web/tests/test_web_TW3.py
18 passed in 3.23s
$ NODE_OPTIONS=--max-old-space-size=6144 just check
All checks passed!
2357 files already formatted
generated files are up to date (843 files)
licences ok                                  (exit 0)
$ just gate packages/tl-web/tests/test_web_TW3.py packages/tl-web/tests/test_web_imports.py packages/tl-web/tests/test_web_confidentiality_walk.py packages/tl-web/tests/test_web_reads_mirror.py
part 1: exit 0, 84 passed in 127.10s (0:02:07)
gate: PASS
```

## Tests added
- `test_web_TW3.py::test_the_regions_headers_and_rows_equal_the_text_module` — rows equal `readiness_rows` projected onto the headers.
- `::test_every_person_reader_sees_the_same_rows` (boss, ctl, bob, amy) and `::test_the_agent_is_refused_the_page` (401).
- `::test_the_status_line_is_the_summary`, `::test_the_page_carries_the_panel_of_the_readiness`, `::test_the_panel_of_one_row_is_the_readiness_page`.
- `::test_a_filter_keeps_the_checks_that_match`, `::test_an_iwp_never_evaluated_says_so`.
- `::test_a_hidden_and_an_unknown_iwp_are_the_same_404`, `::test_no_number_is_the_same_404`, `::test_the_panel_of_an_unknown_iwp_is_the_same_404`.
- `::test_the_page_offers_no_action_and_no_link_to_a_record`, `::test_no_cookie_is_a_redirect_to_sign_in`, `::test_the_real_world_has_no_readiness_to_show`.

## Learnings (proposed)
- `test_web_imports` forbids a runtime `tl_core` import in `tl_web` (only `tl_core.auth`). The not-found test therefore uses `tl_api.errors.body_for`, as `reads.py` does, not `RecordNotFoundError`.
- A readiness route answers 404 for missing, hidden and never-evaluated alike. To show "not evaluated" for a visible IWP, a page needs a second read; without it the terminal's one text cannot be reproduced on the web.
- `WebLog`'s panel route (`/p/{project}/{log}/panel/{number}`) has no query string: a log whose rows are not IWP rows must take its key from the path.

## Open questions / Blocked
- Please confirm the not-evaluated behaviour: (a) visible but never evaluated shows the `not_evaluated_text` line with 200 (as built), and missing or hidden shows the 404 page; or (b) every case answers the 404 page, in which case `not_evaluated_text` is unused on the web. Option (a) needs the extra `get_iwp` read.
- Backlog tile: not in this ticket (per brief). Follow-up line in STATE for T08's `backlog_text`.
