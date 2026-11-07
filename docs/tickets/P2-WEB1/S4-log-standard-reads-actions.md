# P2-WEB1-S4 — Web reads, the log standard (`WebLog`), the offered-now action route

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: security, confidentiality, actions, web
Depends on: S1, S2 (merged on `p2/web1`). Independent of S3 (disjoint files).
Branch: `p2/web1-s4-log-standard`
Approver: none beyond the `full` reviewer and the C4 security review (Sec rows: offered-now check, hidden = missing, plain mode).

## Goal
After this piece the web has everything a log page needs and no page: `WebReadClient` (the server's own read functions behind the terminal's read method names),
`present.py` (the one door to the terminal's pure text modules), `WebLog` (the terminal's `LogScreen` hooks, one template, the seven region ids, htmx panel),
the action route that runs only a command that is in `ACTION_UI` **and** offered on that record right now, and the one HTML error path for pages. The RFI page itself is
the next ticket (T15): you leave it a recipe. Nothing here creates records.

## Setup (every acceptance run, new worktrees need it)
```
cd /home/user/wt/<your worktree> && uv sync --all-packages && export NODE_OPTIONS=--max-old-space-size=6144
```
`just check` takes over 120 s: run it in the background and wait for the harness. Commit subjects are `P2-WEB1-S4: <imperative summary>`
(a different prefix is a defect the reviewer will bounce). End each commit message with the attribution line your harness requires,
then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Brief references
`docs/build-spec/specs/web-client-i1.md` **§5 (Hidden = missing, plain/technical), §6, §7** in full, the S4 row of §11, decision D3 (`actions.py` and the `/do` route are yours), with these pins (this file wins):
1. **`tl_web/reads.py`.** `WebReadClient(ctx, principal)` with the same names and signatures as the `ClientInterface` read methods that `labels_load.load_labels`, `rfi_text`,
   `correspondence_text`, `document_text` and the `tl_tui.details` renderers of the RFI, correspondence and document types call, plus `allowed_actions`, `history`, `links_of`, `link_counts`,
   `list_record_files`, `form_metadata`, `workflow_status`, `thread_page`, `get_record`, `get_record_by_id`. Each calls the JSON **route function** (never a `tl_core` query) with the caller's actor,
   principal and **the viewer the authentication middleware set on this request** (read it where the route's own dependency reads it); a route that takes a `Response` gets a throwaway one; a route's
   `HTTPException` or domain error passes through. Any other attribute raises `UnsupportedRead(name)` (a `AttributeError` subclass): a read a page needs and the client lacks is a failing check, never a new query.
   `MIRRORS: dict[str, str]` maps every implemented method to the route's `operation_id`.
2. **`tl_web/present.py`** is the only `tl_web` module that imports `tl_tui`: it re-exports `display`, `text`, `rfi_text`, `correspondence_text`, `document_text`, `details`, `labels_load`, `action_ui` names the pages use.
   Never import a Textual module (`widgets/*`, `log_screen`, `log_actions`): `LogAction` and the layout `Panel` type live there or in `layout.py`; define web-side equivalents (`WebAction`: key, label, command) and say in the docstring which terminal name each mirrors.
   Importing any `tl_web` module must leave `textual` out of `sys.modules`. If a pure function you need is only reachable through a Textual import, stop (Blocked), do not move terminal code.
3. **`tl_web/webroute.py`** — `WebRoute(APIRoute)` and `web_router() -> APIRouter` (prefix `/web`, `include_in_schema=False`, `route_class=WebRoute`). It turns a mapped failure (`tl_api.errors.body_for`) into HTML:
   404 is the existing `not_found.html` with its one text for hidden and unknown alike (status, text and body bytes identical); any other mapped failure is the status line fragment (`! <message>`, as in item 5). Every page module (this
   piece's, T15, T01…) builds its router with `web_router()`. An unmapped exception is not caught.
4. **`tl_web/log.py`** — `WebLog` (mirrors `LogScreen`: `LOG_NAME`, `KEY_HINTS`, `columns`, `load_rows`, `row_key`, `row_cells`, `panel_text`, `actions_for`, `summary_text`, plus `SLUG` for the URL), `register(slug, cls)`,
   and a module `router` (listed in `tl_web/routers.py`; do not edit that file or `app.py`) with the generic `GET /web/p/{project}/{log}/panel/{number:path}` htmx partial (panel, actions bar, status line out of band; a slug not registered, a hidden or unknown
   number: the one 404 page). A page module calls `register` and adds its own `GET /web/p/{project}/{slug}` that renders `log.html` through a helper in this module (`WebLog.page(request, ...)`). Templates `log.html`, `panel.html` and a status partial
   under `templates/`; you may edit `base.html` (htmx script tag, `<meta name="csrf-token">` when a token exists, `<meta name="htmx-config">` with `allowEval:false, allowScriptTags:false, includeIndicatorStyles:false, selfRequestsOnly:true`, the `tl.js` tag).
   Region ids and order, columns rule (Number, Subject, State first; a column constant in the rows shown is dropped; no sideways scroll), the 1280 px panel layout by CSS media query, and keys: spec §7. `tl.js` holds keys and focus only, sets
   `X-CSRF-Token` from the meta tag on `htmx:configRequest`, drops an answer for a row no longer selected, and uses no `eval`, `fetch`, `innerHTML` or inline handler. No inline `<script>`, `style=` or `on*=` anywhere.
5. **Plain and technical mode** (spec §7 last bullet): `?mode=technical` is honoured for an admin only; for anyone else plain, with `#log-status` text `Technical details are for admins`. Carried on links, never stored.
6. **`tl_web/actions.py`** — module `router` (listed in `routers.py`): `POST /web/p/{project}/records/{record_id}/do/{command}` and its question form `GET .../do/{command}/form` (a partial in the panel). The command must be in `ACTION_UI` **and** in the
   `allowed_actions` the server gives this principal for this record **now** (read at request time, never from a form field or an earlier page); else the refusal text in `#log-status`, no command run, no event written. Build with `ActionUi.build`, stamp actor and scope,
   run through `tl_api.commands.run_command` (S2; the only access check: `require_command_access` etc. live there). A refusal from it (module role, state guard, version conflict, validation) is shown in `#log-status` as `! <its message>`, unchanged; htmx swaps only
   2xx, so the refusal fragment goes out with a status htmx will swap, or the page configures `htmx:beforeSwap` in `tl.js`: your choice, recorded in the report. CSRF is already enforced for the unsafe method by S1 (`csrf.verify`): add it as a router dependency and do not re-implement it.
7. **Body limit.** `packages/tl-api/src/tl_api/auth.py` `BODY_LIMITS` gains the row `("/web/", 64 * 1024)` **after** the existing `/web/sign-in` row (first match wins); nothing else in that file changes.
8. **Recipe for T15.** Write in the report (<= 15 lines) the exact recipe for a log page: the module skeleton (`router = web_router()`, `register`, the `WebLog` subclass hooks, the GET route) so a Haiku ticket can copy it with the RFI hooks of `tl_tui/widgets/domain_screen.py` (`RFI_COLUMNS`, `RFI_DROP`, `rfi_cells`, `rfi_page`, `rfi_summary`).

## Context (<= 10 files)
- `packages/tl-tui/src/tl_tui/client.py` (method names only), `widgets/log_screen.py` (`LogScreen` hooks, lines 96-260), `widgets/domain_screen.py` (RFI mode, lines 60-200), `rfi_text.py`, `labels_load.py`
- `packages/tl-tui/src/tl_tui/action_ui.py`, `packages/tl-api/src/tl_api/commands.py` (`run_command`, `command_spec`)
- `packages/tl-api/src/tl_api/routes/{correspondence,records,actions}.py` (the functions you mirror); `tl_api/auth.py` (viewer on the request, `BODY_LIMITS`)
- `packages/tl-web/src/tl_web/{app,csrf,routers}.py`; `docs/build-spec/module-designs/` is not needed
may explore: `.claude/skills/tui-layout/SKILL.md` (columns and panel rules), `dev/accept/P2-WEB1/S1.py` (cookie harness)

## Allowed paths
- `packages/tl-web/src/tl_web/{reads,present,log,webroute,actions}.py` (create), `packages/tl-web/src/tl_web/pages/__init__.py` (create, empty)
- `packages/tl-web/src/tl_web/templates/**` (create `log.html`, `panel.html`, partials; modify `base.html`), `packages/tl-web/src/tl_web/static/{tl.css,tl.js}`
- `packages/tl-api/src/tl_api/auth.py` (the one `BODY_LIMITS` row)
- `dev/accept/P2-WEB1/S4.py` (create), `docs/reports/P2-WEB1/S4.md` (create)
Not allowed: `tl_web/{app,routers,files,csrf,session}.py`, `tl_web/pages/*.py` other than `__init__`, `tl_api/{app,commands}.py`, `routes/**`, any `tl_tui` file, any test file, `htmlkit.py`, `pyproject.toml`, `uv.lock`, `openapi.json`.

## Acceptance (run once; no pytest, no `just gate`)
```
just check
uv run python dev/accept/P2-WEB1/S4.py
```
`dev/accept/P2-WEB1/S4.py` (SQLite temp ledger, `TL_ENV=test`, `TestClient` at `http://127.0.0.1`, exit 0, one `PASS <check>` per check). A page does not exist yet, so the script builds its own: it puts a module with
`router = web_router()` and a small RFI `WebLog` subclass (the recipe, over `WebReadClient.list_rfis` and the real `rfi_cells`) into `sys.modules` and into `tl_web.routers.PAGE_MODULES` **before** `create_app`; seed RFIs per
the correspondence fixtures the tl-api tests use (one visible, one in a class a plain user may not see, one with no `allowed_actions` for the viewer):
(a) AST scan: no `tl_web` module imports `sqlalchemy`, a `cur_*` name or a `tl_core` module other than `tl_core.auth.*` already used by S1; only `present.py` imports `tl_tui`; in a fresh `python -I` interpreter importing `tl_web.app` and every `PAGE_MODULES` entry present leaves `textual` out of `sys.modules`;
(b) `MIRRORS` keys == the implemented public methods; every value is an `operation_id` in the app's routes; an attribute outside the set raises `UnsupportedRead`; `load_labels` and the RFI, correspondence and document `details` renderers run against the seeded records with no `UnsupportedRead`;
(c) reads parity: `WebReadClient.list_rfis` for admin equals the JSON route's rows (numbers, order); for a plain user the hidden RFI is absent from rows **and** from the count; `get_rfi` of the hidden number raises the route's not-found, the same as for a never-used number;
(d) the page: seven region ids present in order `log-crumb, log-filter, log-table, log-panel, log-actions, log-keys, log-status`; columns begin Number, Subject, State and a constant column is dropped; every row's cells equal `rfi_cells` for it; the panel partial for the visible number carries the terminal's panel lines; for the hidden number and an unknown number the panel answers 404 with identical bytes;
(e) actions: the actions bar lists exactly the offered ones; POST `/do/<command>` with a command in `ACTION_UI` but **not offered** is refused with `! ...` in `#log-status` and the event count of the ledger is unchanged; an offered one runs and the record's state changes; no CSRF token = 403 `csrf_refused`; a user without the module word sees the API's own refusal text in `#log-status`; a command not in `ACTION_UI` = 404;
(f) mode: a non-admin with `?mode=technical` gets plain and the status text; an admin gets the technical rows;
(g) `tl_tui.display.find_technical` over the page and the panel as a plain user finds nothing;
(h) a 100 KiB body to `/web/p/x/records/y/do/z` is 413 `payload_too_large`; a 100 KiB body to `/web/sign-in` is still 413 at 16 KiB;
(i) markup and script: no inline `<script>` body, `style=` or `on*=` attribute in any answer of the script; `tl.js` has none of `eval(`, `fetch(`, `innerHTML` and is <= 200 lines; the CSP header is on every answer.

## Mutation guards (you run them, own worktree, 1 sentinel + <= 5 targeted, 3 lines)
Sentinel: baseline green. Targets: the offered-now membership check removed (e red); the request viewer replaced by a default viewer in `WebReadClient` (c red); the admin-only test for `?mode=technical` dropped (f red);
a `MIRRORS` row removed (b red); the `("/web/", 64 * 1024)` row removed (h red).

## Tests for the end run (S5 writes them; this piece writes none)
`packages/tl-web/tests/{htmlkit.py,test_web_reads_mirror,test_web_log_standard,test_web_rfi_log,test_web_confidentiality_walk,test_web_plain_walk,test_web_actions}.py`. Report the seams (file:line) S5 needs.

## Report requirements
Standard piece report (<= 60 lines): deviations first; the refusal-swap choice (item 6); the recipe (item 8); acceptance output (<= 5 lines per command); mutation result in 3 lines; seams for S5; learnings; no discussion of the commit trailer; no model names in any committed file.

## Escalation triggers
- *Blocked* if: a read the pages need has no route function; a pure terminal function is only reachable through a Textual import; `run_command` needs a change; any path outside Allowed is needed; the piece grows past about 900 changed lines (stop and report what is done, with the cut line you would use).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
