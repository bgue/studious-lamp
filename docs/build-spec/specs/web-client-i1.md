# Spec: web client, increment 1 (RFI, correspondence and document logs, record screen, full PDF preview)

Status: draft v0.1, 2026-10-30, planner tier. Source: owner decision 3 (`module-designs/OWNER-DECISIONS-2026-10-30.md`):
the web client starts in Phase 2; increment 1 covers the everyday screens and reuses the log standard and the server
actions; new modules from then on ship terminal and web together. It moves the first part of `11-phase5-plan.md`
increment 6 forward. Standards applied: `packages/tl-tui/README.md` "Log screens", "Plain and technical display",
"File preview"; the `tui-layout` skill (branch `p1/ux3`); ADR-0009 (sessions), ADR-0016 (hidden = missing),
ADR-0010 addendum (allowed actions), `specs/roles-mvp.md`. Lines marked **(proposed)** go beyond the decisions.

## 1. What exists after this increment
A person signs in at `/web/sign-in` on the server that already serves the API (`tl serve`), opens the RFI log, the
correspondence log or the document log of a project, selects a row, sees the same panel and the same offered actions
as in the terminal, runs an offered action, opens the record screen, and reads any PDF in full in the browser. Every
read is a read the JSON API already makes; every write is a command the API already runs.

## 2. Stack (decision and why)
**Server-rendered HTML in a new workspace package `packages/tl-web` (`tl_web`), mounted into the existing FastAPI app
under `/web`: Jinja2 templates (BSD-3-Clause), htmx 2.0.4 for partial updates (BSD-2-Clause), pdf.js from
`pdfjs-dist` 4.10.38 for PDFs (Apache-2.0), plain CSS and one small script. No Node build.**
1. **Same reads, no second presentation layer.** Pages are rendered in the server process from the JSON routes' own
   functions and from the terminal's own text and label functions (`tl_tui.display`, `rfi_text`,
   `correspondence_text`, `document_text`, `details`), so plain words, technical mode, labels and section order are the
   terminal's by construction. A JS SPA would re-implement every label and section in TypeScript.
2. **Security by default.** The session token stays in an `HttpOnly` cookie no script can read; CSP forbids inline
   script; Jinja2 autoescapes. A SPA holding a bearer token in JS widens the XSS blast radius.
3. **No toolchain risk.** Python dependencies are already locked (`jinja2` 3.1.6, `python-multipart` 0.0.32, both
   permissive, both pass `dev/tools/check_licences.py`); htmx and pdf.js are vendored prebuilt files with a manifest
   the licence check reads (ticket T6). ADR-0002 has Node, but a build step in the gate is not needed for this scope;
   the Phase 3 `web/` TypeScript workspace (model viewer) stays separate.
4. **Alternatives rejected:** React/Vue/Svelte SPA (Node build, duplicated presentation, token in JS); `textual-serve`
   (a terminal in a page, not a web client); a separate web server (second auth surface, second deployment).

## 3. Package, mount, switch
- `packages/tl-web/src/tl_web/`: `app.py` (`mount(app: FastAPI) -> None`), `session.py`, `csrf.py`, `reads.py`,
  `present.py`, `log.py`, `pages/{rfis,correspondence,documents,record,viewer}.py`, `actions.py`, `files.py`,
  `templates/`, `static/{tl.css,tl.js,pdfview.js}`, `static/vendor/{htmx,pdfjs}/` with `VENDORED.toml`
  (`name, version, licence, url, sha256` per file). Depends on `tl-api`, `tl-tui` (pure modules only), `jinja2`,
  `python-multipart`.
- `tl_api.app.create_app` calls `tl_web.app.mount(app)` when `TL_WEB` is `on`; default `on` where `TL_ENV` is dev,
  test or ci, `off` elsewhere until the wave's security review passes **(proposed)**.
- Routes (all HTML unless said; `{project}` is the bare project id, the scope is `project:{project}`):
  `GET|POST /web/sign-in`, `POST /web/sign-out`; `GET /web/` (redirect to `/web/p/{TL_PROJECT}/rfis`);
  `GET /web/p/{project}/{rfis|correspondence|documents}?q=&sel=&mode=`; `GET /web/p/{project}/{log}/panel/{number:path}`
  (htmx partial: panel, actions bar, status line out-of-band); `GET /web/p/{project}/records/{record_id}?tab=&mode=`;
  `POST /web/p/{project}/records/{record_id}/do/{command}`; `GET /web/p/{project}/files/{file_id}/view` (PDF viewer);
  `GET /web/files/{file_id}/content?scope=` and `/web/files/{file_id}/page1.png?scope=` (bytes); `GET /web/static/*`.

## 4. Authentication against the existing sessions
- `POST /web/sign-in` (form `username`, `password`) calls the same `sessions.sign_in` as `POST /auth/sign-in`
  (lockout, audit, timing and error text unchanged; body limit 16 KiB like `/auth/`). On success it sets
  `tl_session=<the same opaque 12-hour session token>; HttpOnly; SameSite=Strict; Path=/web; Secure` (`Secure` dropped
  only for loopback hosts where `TL_ENV` is dev, test or ci) and redirects 303 to `/web/`. Agent accounts have no
  password and therefore no web session. The password is never logged, echoed or put in a redirect.
- `AuthenticationMiddleware` (`tl_api/auth.py`): for paths under `/web/` only, a missing bearer header is filled from
  the `tl_session` cookie; `/web/sign-in` and `/web/static/` are open paths; an unauthenticated `GET` under `/web/`
  is a 303 to `/web/sign-in`, anything else 401. **The cookie is never read for any other path**, so the JSON API stays
  bearer-only and immune to CSRF (test). The principal and the ADR-0016 viewer are set exactly as for a bearer token.
- `POST /web/sign-out` calls `sessions.sign_out`, clears the cookie, redirects to `/web/sign-in`. A role change, a
  disabled account or an expired session apply on the next request (the resolver reads the ledger each time).

## 5. CSRF, headers, confidentiality
- **CSRF:** every non-GET route under `/web/` (sign-in excepted) requires `X-CSRF-Token` (htmx, from
  `<meta name="csrf-token">`) or a `csrf` form field equal to `base64url(HMAC-SHA256(web_secret, "csrf|" +
  sha256(session_token)))`, compared in constant time; plus `Origin` (else `Referer`) equal to `TL_WEB_ORIGIN` when
  set, else the request's own scheme and host; a missing or foreign origin is 403 `csrf_refused`. `web_secret` is
  `TL_WEB_SECRET` (≥ 32 bytes, required outside dev/test/ci, refused at start-up when short); dev generates one per
  process. Sign-in is protected by `SameSite=Strict` and the origin check. A test walks every unsafe `/web` route.
- **Headers** on every `/web` answer: `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src
  'self'; img-src 'self' data:; worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none';
  form-action 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Cache-Control: no-store`
  (bytes and page-1 images: `private`). No inline script or style; htmx configured from a `<meta>` tag.
- **Hidden = missing.** Pages only call functions the JSON routes call, under the viewer the middleware set. A hidden
  record, file or number answers the same 404 page as one that never existed, with the same text; a list leaves it out
  and its counts say nothing of it. `test_web_confidentiality_walk.py` enumerates every `GET /web/...` route from
  `app.routes` (an unclassified route fails), seeds an item per class plus a bogus class, and reads as a plain user, a
  document controller, an admin, a person named on a privileged item and an agent token (the agent is refused
  everywhere); a secret word of a hidden item in any answer fails the test.

## 6. Reads: the same server reads
- `tl_web/reads.py` holds `WebReadClient(ctx, principal)`, which implements the **read** methods of
  `tl_tui.client.ClientInterface` that the pages, `tl_tui.labels_load.load_labels` and the `tl_tui.details` renderers of
  the i1 record types call. Each method calls the **JSON route function** directly (`tl_api.routes.correspondence.
  list_rfis(ctx, actor, project, ...)`, `get_rfi`, `list_correspondence`, `get_correspondence`,
  `tl_api.routes.documents.list_documents`, `get_document`, `routes.records.get_record`, `get_record_history`,
  `routes.links`, `routes.files.list_record_files`, `routes.reference.get_form_metadata`, `get_workflow_status`,
  `routes.actions.get_record_actions`, the thread read), with the caller's actor and principal (a route that takes a `Response` gets a throwaway one). `MIRRORS: dict[str,
  str]` maps each method to the route's `operation_id`. No module of `tl_web` imports `sqlalchemy`, a `cur_*` name or
  a `tl_core` query module (test). A method a page needs and the client lacks is a test failure, never a new query.
- `tl_web/present.py` is the only importer of `tl_tui`: `display`, `text`, `rfi_text`, `correspondence_text`,
  `document_text`, `details`, `labels_load`, `action_ui` (S2). Importing `tl_web` must not import `textual`
  (test checks `sys.modules`).

## 7. The log standard on the web
- `tl_web.log.WebLog` mirrors the `LogScreen` hooks (`LOG_NAME`, `KEY_HINTS`, `columns`, `load_rows`, `row_key`,
  `row_cells`, `panel_text`, `actions_for`, `summary_text`) and renders one template with the terminal's region ids in
  the same order: `#log-crumb` (`P123 › RFI log › P123-RFI-0328: title`), `#log-filter`, `#log-table`, `#log-panel`,
  `#log-actions`, `#log-keys`, `#log-status` (`! text` for a refusal). At ≥ 1280 CSS px (about 160 columns) the panel
  sits right of the list, below it otherwise; the layout is chosen by width alone.
- Columns, panels and summaries come from the same functions as the terminal (`rfi_text.rfi_cells`, `rfi_summary`,
  `rfi_lines` and their correspondence and document counterparts). Columns follow the skill: Number, Subject, State
  first; a column whose value does not vary in the rows shown is dropped; no sideways scroll.
- Keys (`static/tl.js`, no logic beyond keys and focus): Up/Down move the selection (`aria-selected`), Enter opens the
  record, `/` focuses the filter, Esc clears the filter then closes, `F5` reloads, and the action keys the server
  offered. Pointer: click selects, double-click opens. Selecting a row fetches `/panel/{number}` (htmx); an answer for a
  row no longer selected is dropped. No live updates in i1: `F5` re-reads.
- **Actions** come only from `GET /records/{id}/actions` (`allowed_actions`, scoped by module roles). Their keys,
  questions and command building come from the terminal's `ACTION_UI` table, moved to the Textual-free module
  `tl_tui/action_ui.py` (S2; `log_actions` re-exports it). An action with questions opens a form in the panel. The POST
  route accepts only a command that is in `ACTION_UI` **and** offered on that record now, builds it with `ActionUi.build`,
  stamps actor and scope, and runs it through `tl_api.commands.run_command` (S2: the body of `_make_endpoint` after the
  model is built, shared by both, including `require_command_access`). A refusal is shown in `#log-status` as it is.
- **Plain and technical mode:** plain by default; `?mode=technical` is honoured for an admin only (others get plain
  and the status line `Technical details are for admins`), carried on links, never stored. `test_web_plain_walk.py`
  runs `tl_tui.display.find_technical` over every page as a plain user and fails on ids, hashes or keys.

## 8. Record screen and full PDF preview
- `/web/p/{project}/records/{record_id}` has the terminal's tabs: Details (the `tl_tui.details` renderer of the type,
  technical rows only in technical mode), Properties (grouped by set, from form metadata), Links, History, Files and,
  read-only, Thread. Heading `number · subject`, state line, then sections per the skill. The actions bar is the same
  as in the log.
- **Page 1** (document log panel and Files tab): `<img src="/web/files/{id}/page1.png?scope=...">`, with the text line
  of `file_text.file_line` (`PDF document  1.2 MB  3 pages`) when no picture is available. S3 moves the bounded renderer
  (`tl_tui/preview/{render,_worker,cache}.py`: 50 MB cap, `%PDF-` check, isolated `python -I` child, 8 s kill, 1 GiB,
  page 1 only, PNG cached by content hash, 200 files / 64 MB) to `tl_api/preview/` (the terminal re-exports it) and adds
  `GET /files/{file_id}/page1.png?scope=` (action `file.read`; the web route is its cookie mirror). The visibility check
  (`FileService.open_file`, 404 for hidden) runs **before** the cache is consulted; at most 2 renders per process
  (503 `preview_busy`, `Retry-After: 2`); not a PDF or not renderable → 404 `no_preview`.
- **Full preview:** `/web/p/{project}/files/{file_id}/view` loads `vendor/pdfjs/pdf.min.mjs` and `pdfview.js`, which
  calls `getDocument({url: "/web/files/{id}/content?scope=...", isEvalSupported: false, enableXfa: false,
  disableRange: true, disableStream: true})` with `GlobalWorkerOptions.workerSrc` set to the vendored worker, and draws
  pages into canvases as they scroll into view; toolbar: page n of N, zoom, download. Over 50 MB, or not a PDF: a
  download link only. pdf.js ≥ 4.2.67 is required (CVE-2024-4367); `isEvalSupported: false` is kept regardless.

## 9. Testing
- Server-side only in the gate: FastAPI `TestClient` (as in `packages/tl-api/tests/test_auth.py`) and a stdlib
  `html.parser` helper `packages/tl-web/tests/htmlkit.py` (find by id, rows, cells, links); no new test dependency.
- Each page: region ids present and ordered, rows as the terminal's text functions give them (one test compares a
  web row with `rfi_cells` for the same fixture), panel lines, offered actions only, refusal in `#log-status`.
- Security: cookie flags, cookie refused on the JSON API, CSRF walk, origin check, CSP on every answer, agent refused,
  the confidentiality walk (5 readers), the plain walk, page-1 visibility-before-cache, viewer page has no inline script.
- The two scripts are not executed in the gate (no browser in the build environment); they hold no business logic.
  A browser smoke run (Playwright) belongs to `11-phase5-plan.md` increment 5 **(proposed)**.

## 10. Out of scope (increment 1)
Creating records (raise an RFI, register a document, upload, draft a letter) and their forms; the feed, posting to a
thread, dispatch; admin and accounts (module roles stay in the terminal); other logs (commercial, clocks, transmittals,
tags, schema workbench); live updates; mobile layout beyond the narrow breakpoint, PWA and offline; SSO; text layer,
search and annotation in the PDF viewer; the model viewer; separate web origin.

## 11. Pieces and tickets
IDs `P2-WEB1-*`. Needs `P2-RM-S2` (roles in `allowed_actions` and `run_command`). Placement **(proposed)**: an
increment of its own after wave 0; it shares no module directory with I1–I6, so the orchestrator pairs it with one
module stream; registries it touches: `tl_api/auth.py`, `tl_api/app.py`, `tl_api/commands.py`, root `pyproject.toml`
(workspace member), `uv.lock`, `docs/reference/openapi.json`.
| ID | Kind | Review | Depends | Allowed paths | Tests added |
|---|---|---|---|---|---|
| S1 foundation | piece (security) | full | RM-S2 | `packages/tl-web/**` (package, `app.py`, `session.py`, `csrf.py`, base and sign-in templates, `static/`, `VENDORED.toml`), `packages/tl-api/src/tl_api/{auth,app,settings}.py`, root `pyproject.toml`, `uv.lock` | `packages/tl-web/tests/{test_web_auth,test_web_csrf,test_web_headers}.py`, `packages/tl-api/tests/test_api_cookie_refused.py` |
| S2 shared runner, actions | piece (security) | full | S1 | `packages/tl-api/src/tl_api/commands.py` (`run_command`), `packages/tl-tui/src/tl_tui/{action_ui,log_actions}.py`, `tl_tui/widgets/action_form.py` (re-export), `packages/tl-web/src/tl_web/actions.py` | `packages/tl-web/tests/test_web_actions.py` (offered only, not-offered refused, CSRF, module role refusal shown), `packages/tl-api/tests/test_run_command.py`, `packages/tl-tui/tests/test_action_ui_pure.py` |
| S3 server page 1 | piece | full | S1 | `packages/tl-api/src/tl_api/preview/**` (moved), `tl_api/routes/files.py`, `packages/tl-api/pyproject.toml` (declares `pypdfium2`, already locked), `packages/tl-tui/src/tl_tui/preview/{render,cache,_worker}.py` (re-exports), `packages/tl-web/src/tl_web/files.py`, `docs/reference/openapi.json` | `packages/tl-api/tests/test_api_page1.py` (hidden 404 before cache, busy 503, non-PDF 404, cached second call), `packages/tl-web/tests/test_web_files.py` |
| S4 log standard, reads, RFI log | piece | full | S2 | `packages/tl-web/src/tl_web/{reads,present,log}.py`, `pages/rfis.py`, `templates/{log,panel}.html`, `static/{tl.css,tl.js}` | `packages/tl-web/tests/{test_web_reads_mirror,test_web_log_standard,test_web_rfi_log,test_web_confidentiality_walk,test_web_plain_walk}.py`, `htmlkit.py` |
| T1 correspondence log | ticket | full | S4 | `packages/tl-web/src/tl_web/pages/correspondence.py`, `templates/pages/correspondence.html` | `packages/tl-web/tests/test_web_correspondence_log.py` (+ walk entry) |
| T2 document log | ticket | full | S3, S4 | `packages/tl-web/src/tl_web/pages/documents.py`, `templates/pages/documents.html` | `packages/tl-web/tests/test_web_document_log.py` (page-1 image and text fallback) |
| T3 record screen: Details, Properties | ticket | full | S4 | `packages/tl-web/src/tl_web/pages/record.py`, `templates/record/{frame,details,properties}.html` | `packages/tl-web/tests/test_web_record_details.py` |
| T4 record screen: Links, History, Files, Thread | ticket | full | T3, S3 | `templates/record/{links,history,files,thread}.html`, `pages/record.py` (tab dispatch only) | `packages/tl-web/tests/test_web_record_tabs.py` |
| T5 PDF viewer | ticket | full | S3 | `packages/tl-web/src/tl_web/pages/viewer.py`, `templates/viewer.html`, `static/pdfview.js` | `packages/tl-web/tests/test_web_pdf_viewer.py` (scoped URL, size cut-over, CSP, no inline script) |
| T6 vendored licence check | ticket | lite | S1 | `dev/tools/check_licences.py` | `tests/tools/test_check_licences_vendored.py` (copyleft or hash mismatch in `VENDORED.toml` fails) |
| T7 docs | ticket | lite | T1–T5 | `packages/tl-web/README.md`, `docs/runbooks/web-client.md`, `AGENTS.md` (one "Where things go" row) | none (docs) |
| T8 demo | ticket | lite | T1–T5 | `dev/demos/P2-WEB1.sh` (curl with a cookie jar) | the demo is its test |

Mutation guards: cookie read outside `/web/` (S1); CSRF comparison and origin check (S1); offered-now check (S2);
visibility before cache (S3); `MIRRORS` coverage (S4). S1–S3 are `Sec` rows of the wave's security review.
After this increment every new module log adds one `WebLog` page and its test in the same increment as its
terminal log (owner decision 3) **(proposed)**: about one implementer ticket per log in the Phase 2 plans.

## 12. Demo clauses (`just demo P2-WEB1`)
1. `tl serve` on a seeded ledger; `curl -c jar -d username=alice -d password=... /web/sign-in` → 303 and a cookie with
   `HttpOnly`, `SameSite=Strict`; `curl -b jar /commands/AnswerTechnical` → 401 (cookie ignored by the JSON API).
2. `GET /web/p/P1/rfis` has the seven region ids in order; rows match `tl rfi ls` for P1; a restricted RFI is absent
   for alice and present for the controller; its number answers alice with the generic 404 page.
3. Selecting an RFI shows its panel and only the offered actions; `POST .../do/AnswerTechnical` without `X-CSRF-Token`
   → 403 `csrf_refused`; with it → 200 and the panel shows the new state.
4. The document log shows a page-1 image for a PDF revision; `/files/{id}/view` serves the viewer with the CSP header;
   `/web/files/{id}/content` returns the bytes whose SHA-256 the file info states.
5. `?mode=technical` shows record ids for the admin and the "for admins" status line for alice.

## 13. Risks
- **R1 CSRF or session fixation on a cookie surface** (HIGH): mitigated by `SameSite=Strict`, HMAC token, origin check,
  cookie confined to `/web`, a new token per sign-in; S1 on the security review.
- **R2 reads drift from the API** (MD): `WebReadClient` calls route functions only; mirror test; no SQL in `tl_web`.
- **R3 `tl_web` depends on `tl-tui`** (MD): Textual stays out of the import graph (test); a later move of the pure
  text modules into a shared package is a follow-up **(proposed)**.
- **R4 pdf.js vulnerabilities** (MD): pinned version ≥ 4.2.67, `isEvalSupported: false`, CSP without `unsafe-eval`,
  manifest hash; upgrades follow the dependency process (ADR-0006).
- **R5 untested scripts** (LO): two small scripts with no logic; a browser smoke run later.
- **R6 page-1 renders as a denial of service** (LO): 2 concurrent renders, bounded child, content-hash cache.

## 14. Owner questions
- **Q1** Is increment 1 read-and-act (offered actions run from the web) as specified, with creating records in
  increment 2? Default: yes.
- **Q2** Should the web be off by default on production servers until its first security review passes? Default: yes.
- **Q3** Which browsers must work? Default: the current and previous major versions of Chrome, Edge, Firefox, Safari.
