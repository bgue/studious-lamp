# P2-WEB1-S3 — Server-side page 1: the bounded PDF renderer moves to `tl_api`, `GET /files/{file_id}/page1.png`, and the web file mirrors

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: security, api, files, web
Depends on: S1 (merged on `p2/web1`)
Branch: `p2/web1-s3-page1`
Approver: none beyond the `full` reviewer and the C4 security review (Sec row: visibility before cache).

## Goal
After this piece the browser can show the first page of a PDF without a terminal: `tl_api` owns the bounded renderer (it was
`tl_tui/preview/`), the JSON API has `GET /files/{file_id}/page1.png?scope=`, and `/web/files/{id}/content` and
`/web/files/{id}/page1.png` answer the same bytes for a cookie session. The terminal keeps working through re-exports.

## Setup (every acceptance run, new worktrees need it)
```
cd /home/user/wt/<your worktree> && uv sync --all-packages && export NODE_OPTIONS=--max-old-space-size=6144
```
`just check` takes over 120 s: run it in the background and wait for the harness. Commit subjects are `P2-WEB1-S3: <imperative summary>`
(a different prefix is a defect the reviewer will bounce). End each commit message with the attribution line your harness requires,
then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Brief references
`docs/build-spec/specs/web-client-i1.md` **§8 first two paragraphs ("Page 1")** and the S3 row of §11, with these pins (this file wins):
1. **Move.** `packages/tl-tui/src/tl_tui/preview/{render,_worker,cache}.py` move to `packages/tl-api/src/tl_api/preview/` (new package, `__init__.py`).
   The child command becomes `python -I -m tl_api.preview._worker`; the worker's `cache` import becomes `tl_api.preview.cache`. `temp.py`, `terminal.py`,
   `viewer.py` stay in `tl_tui`. `tl_tui/preview/{render,_worker,cache}.py` stay as thin aliases: the module **is** the moved module
   (`sys.modules[__name__] = <the tl_api module>` after import), so `from tl_tui.preview import render, cache`, `render.MAX_BYTES`, and the existing
   tests' `monkeypatch.setattr(render, "WORKER_COMMAND", ...)` keep acting on the one real module. Existing tl-tui tests must pass **unchanged**.
   Move `pypdfium2` (and `pillow` if the worker imports it and tl-api does not declare it) to `packages/tl-api/pyproject.toml`; `tl-tui` keeps its entry. No version change.
   Run `uv lock` once; `uv.lock` is committed. Declaring an already-locked package must not add a package to the lock beyond the workspace edge (check the diff).
2. **Route.** `GET /files/{file_id}/page1.png?scope=` in `routes/files.py`, `operation_id="get_file_page1"`, action `file.read` (the guard of `download_file`),
   `Cache-Control: private`, `image/png`. Order, pinned: (1) `FileService.open_file(...)` under the viewer (hidden or unknown = the same 404 as `download_file`; a
   quarantined file only to its uploader, as there); (2) only then the size and `%PDF-` check and the cache lookup by content hash; (3) render.
   Not a PDF / too big / not renderable / worker error or timeout = 404 `no_preview` with one text for all of them. At most 2 renders at once per process
   (a module-level `threading.BoundedSemaphore(2)` taken without waiting): the third gets 503 `preview_busy` with header `Retry-After: 2`. A cache hit does not take a slot.
   The bytes are never handed to the renderer from a hidden file in any branch. The route is in `openapi.json`: regenerate with `uv run python -m tl_api.openapi`
   (never by hand); the diff is the one new path.
3. **Web mirrors**, `packages/tl-web/src/tl_web/files.py`, module attribute `router = APIRouter(prefix="/web", include_in_schema=False)`
   (listed in `tl_web/routers.py`; do **not** edit `app.py` or `routers.py`):
   `GET /web/files/{file_id}/content?scope=` and `GET /web/files/{file_id}/page1.png?scope=`. Each depends on `guard("file.read")` and calls the JSON route function
   (`download_file`, the new page-1 function) with the same `ctx`, `file_id`, `scope`, `actor`, so there is one visibility path. The cookie is read by the
   middleware only (S1). Headers: bytes `Cache-Control: private` and `Content-Disposition: attachment` as `download_headers` gives; the PNG `private`. A JSON-route error is
   passed through unchanged (status and JSON body; the hidden/unknown 404 text is the route's own). No template, no HTML.
4. No new `tl_web` template or static file. No `tl_tui` logic change. `tl_web` imports no `sqlalchemy`, no `cur_*`, no `tl_core` query module.

## Context (<= 10 files)
- `packages/tl-tui/src/tl_tui/preview/{render,_worker,cache}.py`; `packages/tl-tui/tests/test_preview_render.py` (names, monkeypatch targets)
- `packages/tl-api/src/tl_api/routes/files.py` (`download_file`, `download_headers`, `ScopeParam`, `_service`)
- `packages/tl-tui/src/tl_tui/widgets/file_panel.py` (how the terminal feeds `render_first_page`)
- `packages/tl-web/src/tl_web/{app,routers}.py`, `packages/tl-api/tests/conftest.py` (names)
may explore: the importers of `tl_tui.preview` (grep), `dev/accept/P2-WEB1/S1.py` (cookie harness: sign in on `http://127.0.0.1`)

## Allowed paths
- `packages/tl-api/src/tl_api/preview/**` (create), `packages/tl-api/src/tl_api/routes/files.py` (modify), `packages/tl-api/pyproject.toml`
- `packages/tl-tui/src/tl_tui/preview/{render,_worker,cache}.py` (replace by aliases)
- `packages/tl-web/src/tl_web/files.py` (create)
- `docs/reference/openapi.json` (regenerated), `uv.lock`
- `dev/accept/P2-WEB1/S3.py` (create), `docs/reports/P2-WEB1/S3.md` (create)
Not allowed: `tl_web/{app,routers,csrf,session}.py`, `tl_api/{auth,app,commands}.py`, other `routes/**`, other `tl_tui` files, any test file, root `pyproject.toml`.

## Acceptance (run once; no pytest of new tests, no `just gate`)
```
just check
uv run pytest -q packages/tl-tui/tests/test_preview_render.py packages/tl-tui/tests/test_preview_cache.py packages/tl-tui/tests/test_preview_temp.py packages/tl-tui/tests/test_file_panel.py
uv run python dev/accept/P2-WEB1/S3.py
```
The pytest line is a regression sniff of the move (existing tests only), expected all passed. `dev/accept/P2-WEB1/S3.py` (SQLite temp ledger, `TL_ENV=test`, `TestClient`
with `base_url="http://127.0.0.1"`, exit 0, one `PASS <check>` per check; make the PDF with `pypdfium2`'s `PdfDocument.new()` or copy the helper in `test_preview_render.py`):
(a) `tl_tui.preview.render is tl_api.preview.render` (same for `cache`, `_worker`); `render.WORKER_COMMAND` ends with `tl_api.preview._worker`; each alias file is <= 12 lines;
(b) a reader allowed to see a PDF gets 200 `image/png` from `/files/{id}/page1.png?scope=` with `Cache-Control: private`; a second call starts no child (patch `WORKER_COMMAND` to a failing script after the first call);
(c) **visibility before cache**: after (b) warmed the cache, a plain user who may not see the file (confidential class) gets 404 whose body equals the body for a file id that never existed; no child started for either;
(d) a text file uploaded under `.pdf` name (no `%PDF-` header) and a non-PDF: 404 `no_preview`; an over-50 MB declared size: 404 `no_preview` without a child;
(e) busy: hold two slots (acquire the semaphore twice from the script), the third request is 503 `preview_busy` with `Retry-After: 2`; a cache hit while both are held is still 200;
(f) web mirror: sign in at `/web/sign-in`, then `/web/files/{id}/page1.png?scope=` is 200 `image/png` with the CSP header; `/web/files/{id}/content?scope=` returns the uploaded bytes with `attachment`; the same two paths for the hidden file are 404 with the JSON bodies of (c); without a cookie they are 303 to `/web/sign-in`; with an agent token 401;
(g) a request to `/files/{id}/page1.png?scope=` carrying only the cookie (no bearer) is 401 (the cookie is not read outside `/web/`);
(h) `uv run python -m tl_api.openapi --check` is silent; the openapi diff against the branch point adds exactly one path.

## Mutation guards (you run them, own worktree, 1 sentinel + <= 5 targeted, 3 lines)
Sentinel: baseline green. Targets: cache lookup moved before `open_file` (c red); the `%PDF-` or size check dropped (d red); semaphore dropped (e red); `Cache-Control: private` dropped (b red);
mirror calling a copy of the open logic that skips the viewer (f red).

## Tests for the end run (S5 writes them; this piece writes none)
`packages/tl-api/tests/test_api_page1.py`, `packages/tl-web/tests/test_web_files.py` (hidden 404 before cache, busy 503, non-PDF 404, cached second call).

## Report requirements
Standard piece report (<= 60 lines): deviations first; the alias approach and why the monkeypatches still work; acceptance output (<= 5 lines per command); the openapi path added; mutation result in 3 lines; seams for S5 (file:line); no discussion of the commit trailer; no model names in any committed file.

## Escalation triggers
- *Blocked* if: an existing tl-tui preview test needs editing; `uv.lock` gains more than the workspace edge; the page-1 route needs a change to `FileService`; any path outside Allowed is needed.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
