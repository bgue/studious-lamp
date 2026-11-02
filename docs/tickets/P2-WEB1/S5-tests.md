# P2-WEB1-S5 — The web client tests: ports of every acceptance script, the CSRF walk, hidden = missing on every route, mirror count, plain vs technical, PDF viewer limits, the demo clauses

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: tests, security, web
Depends on: S1, S2, S3, S4, S6, T01, T02, T03, T04, T05, T06, T15 (all merged on `p2/web1`, head d8c8e45)
Branch: `p2/web1-s5-tests`
Approver: none beyond the `full` reviewer; the C4 security review reads these tests as its proofs.

## Goal
Every merged web item has its tests in the gate and the throwaway scripts under `dev/accept/P2-WEB1/` are gone. Tests only: no file under a
`src/` directory changes. A test that fails because the code is wrong is a finding (write it under *Blocked* with file:line); it is never
weakened, skipped or marked xfail (AGENTS never-list). Twin tickets T09-T14 add their own tests later; the walks below are built so that
adding a page is one table entry (see Walks).

## Setup (every run, new worktrees need it)
```
cd /home/user/wt/<your worktree> && uv sync --all-packages && export NODE_OPTIONS=--max-old-space-size=6144
```
`just check` takes over 120 s: run it in the background. Commit subjects are `P2-WEB1-S5: <imperative summary>`; end each message with the
attribution line your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. Do not discuss the
trailer. No model names in any committed file.

## Brief references
`docs/build-spec/specs/web-client-i1.md` §9 (Testing), the "Tests added" column of §11, §12 (demo clauses), D13, D17, D22, D23, D24 in
`STATE.md` (read-only). Pins (this file wins):
1. **Where.** Per-module tests in `packages/tl-web/tests/`; the three cross-package ones where §11 names them. `pyproject.toml` has
   `--import-mode=importlib`: test modules cannot import siblings. The shared harness (ledger, the readers, sign-in client, PDF upload) and the
   `htmlkit` helper (stdlib `html.parser`: by id, rows, cells, links; void elements `img meta link br input` never pushed on the open stack, T04
   learning) live in `conftest.py` as fixtures; `htmlkit.py` stays a file, loaded by a fixture through `importlib.util.spec_from_file_location`
   (precedent: `packages/tl-api/tests/test_integration_confidentiality.py:46`). Build the harness from the `World` classes of
   `dev/accept/P2-WEB1/{S1,S3,S4}.py` and the reader kinds of `packages/tl-api/tests/test_confidentiality_walk.py` (`MAY_READ`: five readers).
   The orchestrator's gate is `just gate` over the paths in Acceptance (there is no `tests/web/`).
2. **Port, do not transcribe.** Read each script `S1 S2 S3 S4 S6 T01 T02 T03 T04 T05 T06 T15` and turn every check (a, b, c ...) into a pytest
   function with the same intent. Three scripts are stale and must be ported to today's behaviour, not today's text: `S4.py` (its demo page
   collides with the real slug `rfis`, D17: use the real RFI, correspondence and document pages, and keep an in-test `WebLog` page only for the
   framework checks that need a fake), `S6.py` (nav order is now Details, Properties, History, Links, Trace, Thread, Files; `?tab=links` is real, D23),
   and any check that patches a read (use `mock.patch.object(WebReadClient, ...)`; fakes take `self`).
3. **Test files** (all in `packages/tl-web/tests/` unless a path says otherwise):
   - S1: `test_web_auth`, `test_web_csrf`, `test_web_headers`; `packages/tl-api/tests/test_api_cookie_refused.py`. Cookie flags (`HttpOnly`,
     `SameSite=Strict`, `Path=/web`, `Secure` off plain loopback http), a new token per sign-in, sign-out kills the session, an agent principal behind the
     cookie is 401, no cookie = 303 to `/web/sign-in`, the JSON API ignores the cookie on a sample of routes (GET and POST, 401 each), CSP and the
     other headers on every answer (also 404 and 500 pages), `openapi.json` has no `/web` path, `TL_WEB=on` with `tl_web` missing is a start error (D6).
   - S2: `test_web_actions`; `packages/tl-api/tests/test_run_command.py`; `packages/tl-tui/tests/test_action_ui_pure.py` (create if absent,
     extend if present). Offered only, not-offered refused with `NOT_OFFERED`, CSRF on `/do`, a module-role refusal shown in `#log-status`.
   - S3: `test_web_files`; `packages/tl-api/tests/test_api_page1.py`. Hidden 404 before the cache (warm the cache as the allowed reader first, no
     child started for the hidden one, body equals the body for an id that never existed), busy 503 with `Retry-After: 2` (a cache hit still 200),
     not-a-PDF and over-50 MB 404 `no_preview`, second call starts no child, the web mirrors: 303 without cookie, 401 with an agent token.
   - S4: `test_web_reads_mirror`, `test_web_log_standard`, `test_web_rfi_log`, `test_web_confidentiality_walk`, `test_web_plain_walk`.
   - T01 `test_web_correspondence_log` (D22: pin the status line counting all loaded rows), T02 `test_web_document_log` (page-1 `<img>`, text
     fallback, no actions D20), T15 inside `test_web_rfi_log` (one row compared with `rfi_cells` for the same fixture).
   - S6/T03/T04: `test_web_record_details` (Details, Properties, History, the escaping of planted markup), `test_web_record_tabs` (Links, Trace,
     Thread, Files: all T03 and T04 checks; D24 pins: Trace depth clamp 1 to 6 and `dir`, Thread one page per `before` with the Older link, Files page 1
     of the first PDF only with View and Download links).
   - T05: `test_web_pdf_viewer` (see PDF viewer limits below). T06: `tests/tools/test_check_licences_vendored.py` (copyleft licence and hash mismatch in
     `VENDORED.toml` fail; the committed manifest passes; a fixture tree under `tmp_path`).
   - `test_web_imports`: `import tl_web` pulls no `textual` (subprocess `python -I -c`, check `sys.modules`), `tl_web` has no `sqlalchemy`, `cur_*` or
     `tl_core` query import (AST scan of `src/tl_web`), `PAGE_MODULES` equals the list in `routers.py` today and every name imports (R3).
   - `test_web_demo_clauses`: spec §12 clauses 1 to 5 end to end in process, one function per clause (see Demo clauses).
4. **CSRF walk** (`test_web_csrf`, name `test_every_unsafe_web_route_is_csrf_checked`). Enumerate `app.routes` for methods POST, PUT, PATCH, DELETE under
   `/web` (today: `/web/sign-out`, `/web/p/{project}/records/{record_id}/do/{command}`, and `/web/sign-in`). Sign-in is the one named exemption
   (`EXEMPT = {("POST", "/web/sign-in")}`, with the reason in a comment). For every other route, signed in as a user who may otherwise pass: no token,
   a wrong token, a token of another session, a right token with a foreign `Origin`, a right token with no `Origin` and a foreign `Referer`: all 403
   `csrf_refused` with one body (equal bytes, so the answer never says which check failed); the right token and own origin passes the CSRF stage
   (status is not the CSRF one; the route's own answer follows). A route added later without `csrf.verify` fails this test with no edit to it. Same
   for a `GET` that changes state: assert no GET route under `/web` appears in the ledger as an event after a walk of all GET routes (event count
   before and after).
5. **Walks** (`test_web_confidentiality_walk`, five readers as `MAY_READ`: admin controller, document controller, plain user, restricted-class user, agent).
   One table `WALK` of rows `(route template, kinds of text it can carry)`, built from `app.routes`: **every GET and POST route with a path parameter
   must be in `WALK` or in `NO_RECORD_TEXT`** (a named set with a reason per entry); the test fails on an unlisted route, which is how a twin page adds
   its entry. Today's rows: the three logs (`rfis`, `correspondence`, `documents`) and their panels, the record page and each of its seven tabs
   (`details properties history links trace thread files`), the viewer page, `/web/files/{id}/content` and `page1.png`, the `/do/{command}` POST and
   its `/form` GET. For each row and each reader:
   a. **Hidden equals missing**: for a record the reader may not read, the answer is byte-equal to the answer for an id that never existed (status,
      every header except `Date` and `Set-Cookie`, body), for the HTML 404 page and for the file routes' JSON 404; no read is made for it on
      the tab routes (count calls on the patched `WebReadClient`, T03/T04 check h); no marker string of the hidden record (subject, number, id, file
      name, class word) appears in any answer, in a log's rows, its count, its status line, its filter echo, or a link.
   b. **Visibility before count and LIMIT**: `list` answers for a reader omit the hidden rows and the count says the same; the status line never counts
      what the reader may not read.
   c. **A visible record's text**: contains what the reader may read and, for the agent, the route is 401 (no cookie principal is an agent).
6. **Mirror count** (`test_web_reads_mirror`). `len(MIRRORS)` is pinned to **24** with a message naming `reads.py` and "twin tickets raise this number in
   their own ticket"; every key is a public method of `WebReadClient`; every value is the name of a function in `tl_api.routes`; no public read method of
   `WebReadClient` is outside `MIRRORS` (a short allow-list for non-reads); each mirror returns what the route function returns for the same viewer
   (compare rows for the admin and the plain user; `file_info` included, D15); `NotImplementedError` and mapped errors pass through as the pages expect.
7. **Plain vs technical** (`test_web_plain_walk`). For a plain user: `tl_tui.display.find_technical` over every page, panel and tab in `WALK` finds
   nothing; `?mode=technical` gives plain output and the status text "Technical details are for admins". For the admin: `?mode=technical` shows record
   ids, and `mode=technical` is carried on the Older link, the trace controls and the tab links only for that admin, never stored (a second request
   without the query is plain). Plain wording equals the terminal's text functions for the same fixture (one row per log).
8. **PDF viewer limits** (`test_web_pdf_viewer`). The page `/web/p/{project}/files/{file_id}/view`: a PDF of at most `MAX_VIEW_BYTES` gets the viewer
   (`data-src` is `/web/files/{id}/content?scope=...`, the same bytes with the same cookie have the SHA-256 the file info states); a PDF of
   `MAX_VIEW_BYTES + 1` declared size, and a non-PDF (by type and by name), get the filename and a download link only (patch the declared size, do not
   upload 50 MB); a hidden or unknown file is the 404 page; CSP on the answer has no `unsafe-eval` and no `unsafe-inline` for scripts; the page has no inline
   `<script>` body and no `on*=` attribute; `pdfview.js` source holds `isEvalSupported: false`, `enableXfa: false`, `disableRange: true`, `disableStream: true`
   and the vendored worker URL; the pdf.js version in `VENDORED.toml` is at least 4.2.67 (parse and compare) and the file hashes match the manifest.
9. **Demo clauses** (`test_web_demo_clauses`, spec §12, with the real viewer route `/web/p/{project}/files/{file_id}/view`): 1 sign-in 303 with
   `HttpOnly` and `SameSite=Strict`, cookie on the JSON API 401; 2 `rfis` has the seven region ids in order, rows equal `tl rfi ls` output of the CLI
   function for P1 (call the CLI's own text function, not a subprocess), the restricted RFI is absent for the plain user and present for the controller,
   its number answers the plain user with the generic 404 page; 3 the panel shows offered actions only, `POST .../do/AnswerTechnical` without the token is
   403 `csrf_refused`, with it 200 and the panel shows the new state; 4 the document log shows the page-1 image for a PDF revision, the viewer has the CSP
   header, the content bytes hash equals the file info; 5 `?mode=technical` shows record ids for the admin and "for admins" for the plain user. Mark this
   file and the walks `@pytest.mark.parity` if the root `conftest.py` adapter fixture is usable from `packages/tl-web/tests`; otherwise SQLite only and say
   so in the report (the orchestrator runs `just gate-pg packages/tl-web` at DONE).
10. **Delete the scripts last**, in a separate final commit: `git rm -r dev/accept/P2-WEB1` once every port is green. Then `grep -rn "dev/accept/P2-WEB1"` over
    `docs/tickets/P2-WEB1/T09*.md T10*.md T11*.md` is the supervisor's to rewrite; list those hits in the report, do not edit those tickets.

## Context
The scripts under `dev/accept/P2-WEB1/` (12 files, read each once), `docs/reports/P2-WEB1/*.md` (seams and learnings), `packages/tl-web/src/tl_web/{app,csrf,
reads,present,log,webroute,routers,actions,files}.py`, `pages/*.py`, `packages/tl-api/tests/{conftest.py,test_confidentiality_walk.py}`, `tests/tools/test_check_licences.py`.
may explore: `packages/tl-web/src/tl_web/templates/**`, `static/**`, root `conftest.py`.

## Allowed paths
- `packages/tl-web/tests/**` (create)
- `packages/tl-api/tests/{test_api_cookie_refused,test_run_command,test_api_page1}.py` (create)
- `packages/tl-tui/tests/test_action_ui_pure.py` (create or extend)
- `tests/tools/test_check_licences_vendored.py` (create)
- `dev/accept/P2-WEB1/**` (delete, last commit only), `docs/reports/P2-WEB1/S5.md` (create)
Not allowed: any file under a `src/` directory, templates, static, `pyproject.toml`, `uv.lock`, an existing test (except the one named extension), `docs/reference/**`.

## Acceptance (run each once)
```
just check
just gate packages/tl-web packages/tl-api/tests/test_api_cookie_refused.py packages/tl-api/tests/test_run_command.py packages/tl-api/tests/test_api_page1.py packages/tl-tui/tests/test_action_ui_pure.py tests/tools/test_check_licences_vendored.py | tee .gate/summary.txt
```
Expected: `gate: PASS`, no skip, no xfail; the report pastes the summary line (and the count per file). Not the whole suite.

## Mutation guards (you run them, own worktree, sentinel + at most 5 targeted, 3 lines in the report, each reverted)
Sentinel: baseline green. Targets, each must turn a named test red: (1) `Path=/web` cookie read widened to every path in `tl_api/auth.py` (cookie-refused); (2) the CSRF comparison
replaced by `True` in `csrf.verify` (the walk); (3) the offered-now check in `actions.py` dropped (test_web_actions); (4) the page-1 cache lookup moved before `open_file` (test_api_page1);
(5) one `MIRRORS` row removed, or a tab route reading before its visibility check (mirror test, walk). Source edits for mutants are never committed.

## Report requirements
Standard piece report (<= 60 lines, <= 5 decisive output lines per command). First line: deviations. Then: the harness shape (fixtures, how `htmlkit` is loaded);
the table of ports (script check -> test function, one line per script); the stale-script handling; the `WALK` rows and `NO_RECORD_TEXT` entries; any code bug the tests
found (file:line, under Blocked); the parity decision; mutation result in 3 lines; the T09-T11 references to the deleted scripts; candidate learnings. Builder return <= 15 lines.

## Escalation triggers
- *Blocked* if a test cannot pass without a source change (list file:line and the failing test; do not weaken it), if the harness needs a dependency, or if a hit on `tl_web` shows a
  hidden record's text in an answer (that is a HI finding: stop and report, with the request that shows it).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
