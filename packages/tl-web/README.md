# tl-web (`tl_web`)

The web client: server-rendered HTML pages mounted under `/web` in the API process (`tl serve`). A page shows the
same words, rows, panels and offered actions as the terminal, because it calls the same read contracts as the JSON
API and the terminal's own pure text functions. It holds no business logic. Runbook: `docs/runbooks/web-client.md`.
Spec: `docs/build-spec/specs/web-client-i1.md`.

## What it is
- Server-rendered pages (Jinja2, autoescaped), htmx for partial updates, pdf.js for full PDF preview. No Node build.
- Reads go through `tl_web.reads.WebReadClient`, which calls the JSON route functions of `tl_api` with the caller's
  actor and principal. No SQL, no `cur_*` name and no `tl_core` query module is imported here.
- `tl_web.present` is the only module that imports `tl_tui` (its pure text modules). Importing `tl_web` must not
  import `textual`.
- `tl_api.app.create_app` mounts it through `tl_web.app.mount(app)` when `TL_WEB` is on. The `/web` routes are not in
  `docs/reference/openapi.json`.

## Layout (`packages/tl-web/src/tl_web/`)
| Path | What it holds |
|---|---|
| `app.py`, `routers.py` | `mount`, sign-in and sign-out, the `/web/` redirect, the 404 catch-all; `PAGE_MODULES` in match order |
| `log.py` | `WebLog`, the web twin of the terminal's `LogScreen` hooks and regions |
| `reads.py` | `WebReadClient` and `MIRRORS` (each read method to its route's `operation_id`) |
| `present.py` | the only importer of `tl_tui` text modules (`display`, `rfi_text`, `details`, `labels_load`, ...) |
| `actions.py` | the offered-action form and `POST /p/{project}/records/{record_id}/do/{command}` |
| `csrf.py`, `session.py` | the token and origin checks; the `tl_session` cookie |
| `files.py` | file bytes and page-1 pictures (cookie mirrors of the JSON file routes) |
| `pages/` | one module per page; `record_*.py` hold the record screen's tabs |
| `templates/` | `base.html`, `log.html`, `panel.html`, `action_form.html`, `record/*.html`, `viewer.html` |
| `static/` | `tl.css`, `viewer.css`, `tl.js` (keys and focus only), `pdfview.js` (viewer script, no logic) |
| `static/vendor/` | htmx and pdf.js files, with `VENDORED.toml` (name, version, licence, url, sha256 per file) |

## Pages
Path `/web/p/{project}/<slug>`.
- Logs: `rfis`, `correspondence`, `documents`.
- Twins of the register screens, one line each:
  - `cwps`: contract work packages (M3).
  - `cwas`: contract work activities (M3).
  - `wbs`: the WBS tree (M3).
  - `packages`: external packages (M3).
  - `path`: the path view of versions (M3).
  - `stock`: stock on hand by lot and location (M4).
  - `movements`: stock movements (M4).
  - `receipts`: goods receipts (M4).
  - `mto`: material take-off lines (M4).
  - `items`: the item library, with the projects per item (M4).
  - `locations`: the location tree (M4).
- Record screen `records/{record_id}?tab=`: Details, Properties, History, Links, Trace, Thread, Files.
- File viewer `files/{file_id}/view`; bytes at `/web/files/{file_id}/content?scope=`, page 1 at
  `/web/files/{file_id}/page1.png?scope=`.
- `/web/sign-in` (GET and POST); `/web/sign-out` (POST).

## Recipe: add a page
1. The stub `pages/<slug>.py` is named in `PAGE_MODULES`; the page replaces its body.
2. Subclass `WebLog` with `LOG_NAME`, `columns`, `load_rows` (reads through `self.client`), `row_key`, `row_record`,
   `row_cells`, `panel_text`, `actions_for`, `summary_text`; call `register("<slug>", ...)`.
3. Route `@router.get("/p/{project}/<slug>")` returns `<Log>.page(request, project, q=, sel=, mode=)`.
4. Add a `MIRRORS` row in `reads.py` for each read the page needs. A read the client lacks is a stop, not a new query.
5. Add a `WALK` marker in `packages/tl-web/tests/walk.py` and a `test_web_<slug>.py`, modelled on
   `test_web_document_log.py` (recipe: `docs/tickets/P2-WEB1/TWINS.md`).

## Rules
- **Hidden = missing (ADR-0016).** A hidden record, file or number answers the same 404 page as one that never
  existed. A list leaves it out, and its counts say nothing of it.
- **CSRF on every unsafe request.** A POST under `/web` needs `X-CSRF-Token` (htmx reads it from the
  `<meta name="csrf-token">`) or a `csrf` form field, and an `Origin` (else `Referer`) equal to `TL_WEB_ORIGIN` or the
  request's own; else 403 `csrf_refused`. Sign-in has no token: it is protected by `SameSite=Strict` and the origin
  check (spec §5).
- **`TL_WEB` on or off.** Unset means on in dev, test and ci and off elsewhere; any other value is refused. `on` with
  the package missing is a start-up error. The JSON API never reads the cookie.
- **Headers on every `/web` answer:** a strict CSP (no inline script or style), `nosniff`, `Referrer-Policy:
  same-origin`, `Cache-Control: no-store` (bytes and page-1 pictures: `private`).
- **Plain by default.** `?mode=technical` is honoured for an admin only; it is carried on links, never stored.
- **Decisions, stated plainly:**
  - D41: a page whose rows have no record page has no Open link (`row_open_key` returns `None`). Phase 2 follow-up:
    receipts, locations, MTO lines and items carry record ids but have no web record page yet.
  - The items panel shows other projects' quantities for the same item, by design: module roles do not filter reads
    in the MVP (`docs/build-spec/specs/roles-mvp.md` §7). The project-membership filter is P3-I8; see `docs/reports/P2-WEB1/SEC-C4.md`.
  - The locations page indents a subject by depth in the cell text, but HTML collapses the spaces, so the tree looks
    flat. Follow-up.

## Tests and commands
`packages/tl-web/tests/`: `htmlkit.py` (a stdlib `html.parser` helper: find by id, rows, cells, links; no new test
dependency), the walks (`test_web_confidentiality_walk.py`, `test_web_plain_walk.py`), `test_web_imports.py`.
```
uv run pytest packages/tl-web/tests -q
just serve                 # the API and the web client (127.0.0.1:8765)
just demo P2-WEB1          # dev/demos/P2-WEB1.sh over HTTP
```
The scripts in `static/` are not run by the gate (no browser in the build environment).
