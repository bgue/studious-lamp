# P2-WEB1-T05 — PDF viewer page and pdfview.js

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S3 (merged), S4 (merged; the `file_info` read is already in the branch, added by the supervisor in round 3)
Branch: `p2/web1-t05-pdf-viewer`

## Goal
`GET /web/p/{project}/files/{file_id}/view` shows a PDF in full in the browser with the vendored pdf.js: pages drawn into canvases as they scroll into view, a toolbar with `page n of N`, zoom in and out, and a download link. A file that is not a PDF, or is over 50 MB, gets the filename and a download link only. A hidden or unknown file is the one 404 page.

## Brief references (pasted)
> **Full preview:** `/web/p/{project}/files/{file_id}/view` loads `vendor/pdfjs/pdf.min.mjs` and `pdfview.js`, which calls `getDocument({url: "/web/files/{id}/content?scope=...", isEvalSupported: false, enableXfa: false, disableRange: true, disableStream: true})` with `GlobalWorkerOptions.workerSrc` set to the vendored worker, and draws pages into canvases as they scroll into view; toolbar: page n of N, zoom, download. Over 50 MB, or not a PDF: a download link only. pdf.js >= 4.2.67 is required (CVE-2024-4367); `isEvalSupported: false` is kept regardless.
> CSP on every `/web` answer: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; worker-src 'self'; object-src 'none'; ...`. No inline script, no inline style, no `on*=` attribute, no `style=` attribute in markup (setting `element.style.x = ...` from the script is fine). The two scripts hold no business logic and are not run in the gate.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_web/webroute.py
def web_router() -> APIRouter: ...                  # prefix /web, HTML failures (a 404 from a read is the one 404 page)
def not_found_page(request: Request) -> HTMLResponse: ...
# tl_web/app.py
def render(request: Request, name: str, status: int = 200, **values: Any) -> HTMLResponse: ...   # Jinja; csrf token supplied
PROJECT_ID: re.Pattern[str]
# tl_web/reads.py
class WebReadClient:
    def __init__(self, ctx: ApiContext, principal: Principal, *, path: str = "/web") -> None: ...
    def file_info(self, scope: str, file_id: str) -> Any: ...   # FileInfo: file_id size(int bytes) content_type filename status; checks file.read; hidden/unknown raises the 404
# how a page builds the client (tl_web/log.py WebLog.__init__)
#   principal = request.scope[PRINCIPAL_KEY]   # from tl_api.auth import PRINCIPAL_KEY
#   client = WebReadClient(request.app.state.ctx, principal, path=request.url.path)
# tl_web/templates/base.html: blocks `title` and `content`; already loads htmx and tl.js
# vendored: /web/static/vendor/pdfjs/pdf.min.mjs and /web/static/vendor/pdfjs/pdf.worker.min.mjs
# existing byte route (cookie mirror): GET /web/files/{file_id}/content?scope=project:{project}
```
Template data flow: the page renders `<div id="pdf-view" data-src="/web/files/{id}/content?scope=..." data-worker="/web/static/vendor/pdfjs/pdf.worker.min.mjs" data-name="...">`; `pdfview.js` reads the data attributes only. Build the scope as `f"project:{project}"` and URL-quote it (`urllib.parse.quote(scope, safe="")` gives `project%3AP123`).

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `packages/tl-web/src/tl_web/files.py`
- `packages/tl-web/src/tl_web/templates/base.html` and `not_found.html`
- `packages/tl-web/src/tl_web/log.py` (lines 108-122 `__init__`; `not_found_page` use at `page`)
- `dev/accept/P2-WEB1/S3.py` (`World`, `make_pdf`, `upload`, `web_session`, `client`; to reuse)
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/viewer.py` (create)
- `packages/tl-web/src/tl_web/templates/viewer.html` (create)
- `packages/tl-web/src/tl_web/static/pdfview.js` (create)
- `packages/tl-web/src/tl_web/static/viewer.css` (create; linked from `viewer.html`, `tl.css` is not edited)
- `dev/accept/P2-WEB1/T05.py` (create)
- `docs/reports/P2-WEB1/T05.md` (create)

## Steps
1. `pages/viewer.py`: `router = web_router()`; `GET /p/{project}/files/{file_id}/view`. Refuse a `project` that does not match `PROJECT_ID` with `not_found_page`. Read `info = client.file_info(scope, file_id)`. `MAX_VIEW_BYTES = 50 * 1024 * 1024`. The viewer is offered when `info.content_type == "application/pdf"` or the filename ends in `.pdf` (case-insensitive), and `info.size <= MAX_VIEW_BYTES`; otherwise the template shows the filename and a download link only. The download link is the content URL.
2. `viewer.html`: extends `base.html`; heading with the filename; toolbar (`id="pdf-toolbar"`: `<span id="pdf-page">`, zoom out and in buttons with `type="button"`, the download link); `<div id="pdf-view" ...>` data attributes as above and `<div id="pdf-pages">`; links `/web/static/viewer.css`; loads `<script type="module" src="/web/static/pdfview.js"></script>` only in the viewer branch. No inline script or style.
3. `pdfview.js` (about 100 lines, no framework): `import * as pdfjs from "/web/static/vendor/pdfjs/pdf.min.mjs"`; set `pdfjs.GlobalWorkerOptions.workerSrc` from `data-worker`; `getDocument` with exactly the options in the brief; create one canvas per page (size from page 1 at the current zoom), render each when an `IntersectionObserver` sees it; keep `page n of N` in `#pdf-page` from the page most in view; zoom steps 0.25 between 0.5 and 3, redraw on change; on a load failure write `This PDF could not be shown. Use the download link.` into `#pdf-pages`.
4. `viewer.css`: a few rules for the toolbar and the page column (no `@import`, no `url()` outside `self`).
5. `dev/accept/P2-WEB1/T05.py`: load S3 as a module (`importlib.util.spec_from_file_location`, register in `sys.modules`, `exec_module`; `main()` is guarded, so importing runs nothing) and build `S3.World()`. Upload a 2-page PDF (`S3.make_pdf(2, 300)`), a text file and a PDF over 50 MB to `w.open_item`, and a PDF to `w.restricted_item`. Checks (`PASS <letter>: ...`, exit 1 on the first failure): (a) bob's viewer page for the PDF is 200, contains `id="pdf-view"` with a `data-src` of exactly `/web/files/<id>/content?scope=project%3A...` (the project of `S3.SCOPE`), the worker data attribute, a download link and the script tag for `pdfview.js`; (b) the page has no inline `<script>` body, no `style=` attribute, no `on*=` attribute and carries the CSP header of the S4 script (`default-src 'self'; script-src 'self'; ...`); (c) the text file and the 51 MB PDF answer 200 with a download link and no `pdf-view` element and no `pdfview.js`; (d) the hidden file's view page for bob answers the same bytes and status as a file id that never existed (404); the controller can open it; (e) a request without a cookie is a 303 to `/web/sign-in`; (f) the data-src bytes fetched with the same cookie have the SHA-256 the file info states; (g) `node --check` is not available: read `pdfview.js` as text and assert it contains `isEvalSupported: false`, `enableXfa: false`, `disableRange: true`, `disableStream: true`, `workerSrc`, and none of `eval(`, `new Function`, `innerHTML`, `document.write`.

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-WEB1/T05.py
```
Expected: `just check` clean; every check prints `PASS`, exit 0. Paste the last 10 lines of each in the report. The scripts are not executed in a browser here; say so in the report.

## Tests to add
None here. The tests piece (S5) writes `packages/tl-web/tests/test_web_pdf_viewer.py` (scoped URL, size cut-over, CSP, no inline script).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), at most 60 lines, plus the pasted outputs and a line saying no pytest was run (deferred) and that `pdfview.js` was not run in a browser. Commit subject `P2-WEB1-T05: <summary>`; no model names in any committed file. Commit message: end it with the attribution trailer the harness requires, then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. Do not discuss the trailer.

## Escalation triggers
- Stop and report *Blocked* if the page needs a read `WebReadClient` does not have (other than `file_info`), or any file outside Allowed paths.
- Stop if `just check` reports a licence or vendored-hash problem (that belongs to S1; do not touch `static/vendor/`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
