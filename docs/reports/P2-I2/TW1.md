# Report — P2-I2-TW1

Branch: `p2/i2-tw1-web`   Commit(s): one commit `P2-I2-TW1: ...` (code and report; sha in the return)

## Deviations
- Commit subject uses the ticket ID form `P2-I2-TW1: ...` (AGENTS.md rule 9 and the ticket's Report requirements). The harness text said `TW1: ...`; the ticket form contains it. Same choice as T07b.
- Trailer names Claude Haiku 5.5 (my own model, per the session). The harness text said Opus 5.5, which does not match this session.
- Read beyond the Context list: `tl_web/log.py`, `tests/{walk,conftest,htmlkit}.py`, the two pinned tests, `tl_api/routes/awp.py` 238-290, `tl_tui/client.py`. No file outside Allowed paths changed.
- The ticket's Brief writes the summary as `iwp_summary(rows)`. The real signature is `iwp_summary(total, shown, *, state, foreman)`; the page calls `iwp_summary(n, n)`.

## Changed files
- `packages/tl-web/src/tl_web/pages/iwps.py` (new): `IwpWebLog` (WebLog subclass), `register("iwps", ...)`, `GET /p/{project}/iwps`. Module docstring says the s/d/m/r filters are not on this page.
- `packages/tl-web/src/tl_web/present.py`: `iwp_text` added to the import list and `__all__`.
- `packages/tl-web/src/tl_web/reads.py`: three `MIRRORS` entries (`list_iwps`, `get_iwp`, `list_iwp_scope`, operation ids of the same names) and three methods at the class end.
- `packages/tl-web/src/tl_web/routers.py`: `tl_web.pages.iwps` appended to `PAGE_MODULES`.
- `packages/tl-web/tests/test_web_TW1.py` (new): 14 tests.
- `packages/tl-web/tests/walk.py`: one `WALK` row for `/web/p/{project}/iwps` under a TW1 comment.
- `packages/tl-web/tests/test_web_imports.py`: `tl_web.pages.iwps` appended to the pinned `PAGE_MODULES`.
- `packages/tl-web/tests/test_web_reads_mirror.py`: MIRRORS count pin 42 to 45; `cases` entries for the three reads; `get_iwp` and `list_iwp_scope` added to `ABSENT` (the real world has no IWPs, so the route and the mirror both answer 404).

## Pins (union form)
- `PAGE_MODULES` in `routers.py` and in `test_web_imports.py`: `tl_web.pages.iwps` appended at the end.
- `WALK` in `walk.py`: `("GET", "/web/p/{project}/iwps")`. The panel probe is added automatically by `_panels`.
- `MIRRORS` count: 45. Methods: `list_iwps`, `get_iwp`, `list_iwp_scope`.

## Commands and output
```
$ NODE_OPTIONS=--max-old-space-size=6144 just check
All checks passed!          (ruff check last)
0 errors, 0 warnings, 0 informations
generated files are up to date (843 files)
licences ok
exit 0
$ just gate packages/tl-web/tests/test_web_TW1.py packages/tl-web/tests/test_web_imports.py packages/tl-web/tests/test_web_confidentiality_walk.py packages/tl-web/tests/test_web_reads_mirror.py
part 1: exit 0, 80 passed in 104.15s (0:01:44)
gate: PASS
```

## Tests added
- `packages/tl-web/tests/test_web_TW1.py::test_the_page_is_mounted_and_registered` — router in `page_routers()`, slug `iwps`.
- `::test_the_log_rows_and_headers_equal_the_text_module` — regions, headers, cells equal `iwp_cells` over `seed_iwp` rows.
- `::test_every_person_reader_sees_the_same_rows[boss|ctl|bob|amy]` — four person readers see the same rows.
- `::test_the_agent_is_refused_the_page` — `bot` gets 401.
- `::test_the_status_line_is_the_summary` — `4 IWPs`.
- `::test_the_panel_of_one_iwp_is_the_iwp_page_as_plain_lines` — panel facts equal `iwp_page(panel=True)`.
- `::test_the_filter_and_an_unknown_number` — `?q=` finds one row; two unknown panels are byte-equal 404s.
- `::test_a_read_that_says_not_found_is_the_same_404` — hidden (read raises not-found) equals unknown, byte for byte.
- `::test_no_cookie_is_a_redirect_to_sign_in` — 303 to sign-in.
- `::test_the_actions_bar_holds_only_the_open_link` — no buttons, no command.
- `::test_the_real_world_has_an_empty_iwp_log` — unpatched world: `0 IWPs`, no rows, unknown panel 404.

## Learnings (proposed)
- "Five readers" is met by the `WALK` row (run by `test_web_confidentiality_walk.py` in the gate) plus the parametrized person-reader test above; the fake IWP world carries no record classes, so the walk checks mostly the 404 shape.
- `seed_iwp` signoffs are empty, so no test here checks that a sign-off hash stays out of the page; only T07b's acceptance covers it.
- `WALK._panels` derives panel probes from every `/web/p/{project}/<slug>` row, so a log page needs no separate panel row.

## Open questions / Blocked
- `packages/tl-web/README.md` line 36 lists the log pages (`cwps` is there). It is in the ticket's Context but not in Allowed paths, so I did not add `iwps`. Supervisor: add the line in a follow-up, or allow it here?
- The mirror `list_iwp_scope` takes no `limit`, so the route default (500) applies, while `ApiClient` defaults to 200. The page shows at most 50 scope rows, so nothing visible differs; flagging in case the mirror should match the client.
