# P1-UX2-S4 — Documents on LogScreen, open in viewer, page-1 thumbnail, Files tab

> **D9 (orchestrator, 2026-10-22, overrides the rest of this spec where they differ).** textual-image is
> LGPL-3.0-or-later and refused by the licence check (your first attempt, caf2a9a). Use **rich-pixels 3.0.1 (MIT,
> by the Textual author; depends on Pillow and Rich)** instead: the page-1 thumbnail is a Rich renderable
> (`Pixels.from_image(...)`, half-block cells) in the FilePanel, shown when the terminal has colour (use T01's
> `image_protocol` only to decide colour vs plain; no kitty/iTerm/sixel escapes). Text fallback (type, size, pages,
> title) when there is no colour or rendering fails. Size the thumbnail to the panel (about 30 columns wide), render it
> off the UI thread from the cached page-1 PNG. A snapshot of the thumbnail is allowed (it is deterministic).
> rich-pixels' wheel has no License field (only an MIT LICENSE file): if `dev/tools/check_licences.py` flags it,
> add an allow-list entry naming the MIT licence file, with a one-line comment. Allowed paths widen by
> dev/tools/check_licences.py (that entry only), dev/demos/p1_i2_demo.py, dev/demos/p1_i2b_demo.py and
> dev/tour/phase1.py (only the `#docs-table`/`#docs-status` → `#log-table`/`#log-status` renames the move to
> LogScreen forces). Testing policy (owner, 2026-10-21): run only the gate paths named for this piece; the whole
> suite and the demos run once at the end of the increment.


Status: draft (dispatch in wave 2, after S1, S2, T01, T02 are merged)
Tier: sonnet
Kind: piece
Review: full
Labels: tui, tests, dependencies, security
Depends on: S1 (allowed_actions, list_record_files, fetch_file, document_command), S2 (LogScreen, ActionFormScreen), T01 (`preview/terminal.py`), T02 (`file_text.py`)
Branch: `p1/ux2-s4-document-preview`

## Goal
The document log stands on `LogScreen` (breadcrumb, panel, actions bar from the server, keys row). `v` (or Enter on the
file line) opens the current revision's file in the system viewer; where the terminal shows images the panel shows page 1
of a PDF as a picture, elsewhere page count, size and title. Any record with files gets a Files tab (RFIs included) with
the same open and preview. Rendering is bounded, off the UI thread, in a child process, cached by content hash.

## Brief references (pasted, abridged)
> SCOPE §4: Open = a key opens the current revision's file in the system viewer; in remote mode it is downloaded to a
> temporary file first, through the existing file routes (confidentiality and hashing unchanged). Thumbnail where the
> terminal can show images (kitty, iTerm2, WezTerm, Windows Terminal/sixel); elsewhere page count, size and title.
> Rendering uses pypdfium2 (Apache-2.0 / BSD-3; PDFium BSD-3) and a permissive terminal-image library (textual-image,
> MIT); both pass `dev/tools/check_licences.py` or the piece stops (copyleft). Rendering is bounded (page 1 only, size
> and time caps, no network), runs off the UI thread, cached by content hash. Tests use the text fallback.
> Owner decision 2026-10-21 (APPROVALS b57c20b): open in system viewer plus page-1 thumbnail. README D4: a child process.
> README Sec2 lists what the reviewer will prove; build to it.

## Interfaces
```python
# tl_tui/preview/ (T01 created __init__.py and terminal.py: image_protocol(env) -> "kitty"|"iterm2"|"sixel"|"none")
# preview/temp.py   class PrivateTemp: context manager / registry; dir mode 0700 under tempfile.gettempdir(), files 0600,
#                   cleanup() on screen close and atexit (best effort), never follows symlinks, name = fetch_file's sanitised name
# preview/viewer.py def open_in_viewer(path: Path, launcher: Launcher | None = None) -> None
#                   default: argv list (xdg-open | open | os.startfile), never shell=True, start_new_session, path made absolute,
#                   a name starting "-" is prefixed "./"; env TL_VIEWER_CMD (shlex) replaces the default (demo and tests record the path)
# preview/render.py @dataclass PreviewResult: state: Literal["ok","not_pdf","too_big","timeout","error"]; pages: int|None; png: Path|None
#                   def render_first_page(path: Path, sha256: str, *, timeout_s: float = 8.0) -> PreviewResult
#                   parent: refuses > MAX_BYTES (50 MB) without starting a child; cache hit by sha256 returns at once; else spawns
#                   `python -I -m tl_tui.preview._worker` (argv list, stripped env, no stdin), kills it at the timeout.
# preview/_worker.py child: checks the "%PDF-" header, setrlimit (address space ~1 GiB, CPU seconds) where supported, opens with
#                   pypdfium2, page 0 only, scale so that max(width,height) <= 1200 px and area <= 1.5 MP, writes PNG to a temp name
#                   then os.replace into the cache, prints one JSON line {"pages": n}. Imports no network module; no file but input and cache.
# preview/cache.py  directory under the user cache dir (XDG_CACHE_HOME or ~/.cache/throughline) mode 0700, entries <sha256>.png only,
#                   size cap 64 MB / 200 entries, oldest evicted; a name that is not 64 hex digits is never read or written
# widgets/file_panel.py class FilePanel(Widget): shows file_line(...) rows (T02), the thumbnail via textual_image when
#                   image_protocol(os.environ) != "none" and the preview is ok (import textual_image lazily, inside that branch),
#                   else the text fallback "PDF document  1.2 MB  3 pages"; render runs in run_worker(thread=True); a new selection cancels
#                   the previous render; `v` / Enter on a file line -> fetch_file(...) into PrivateTemp then open_in_viewer
# RecordView gains a Files tab (key 6; tabs, bindings and compose only: the Details renderer function belongs to S5, leave it alone) shown only when client.list_record_files(record_id) is non-empty; RecordScreen KEY_HINTS and keymap.py updated
# DocumentRegisterScreen(LogScreen): actions via allowed_actions + document_command (IssueRevision, SupersedeRevision, SupersedeDocument,
#                   VoidDocument, CreateTransmittal -> the existing composer); existing `r` re-pin stays when the document has a stale link
```
Dependencies: add `pypdfium2` and `textual-image` to `packages/tl-tui/pyproject.toml`; `uv lock`; run
`uv run python dev/tools/check_licences.py` and paste the two lines for these distributions (and Pillow) into the report.
Any copyleft or unknown finding: STOP, write *Blocked*, change nothing else.

## Context (≤ 10 files)
- `packages/tl-tui/src/tl_tui/widgets/document_register.py`, `document_text.py`, `details/documents.py`
- `packages/tl-tui/src/tl_tui/widgets/log_screen.py`, `action_form.py` (S2); `file_text.py`, `preview/terminal.py` (T01, T02)
- `packages/tl-tui/src/tl_tui/widgets/record_view.py`, `record_screen.py`; `client.py` (S1's three methods)
- `packages/tl-tui/tests/test_document_register.py`, `fakes_documents.py`, `test_record_screen.py`
- `dev/tools/check_licences.py`, `docs/adr/0006-*.md` (licence policy; read only the decision)
may explore: `packages/tl-core/src/tl_core/files/queries.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/preview/**` (create: temp, viewer, render, _worker, cache), `packages/tl-tui/src/tl_tui/widgets/file_panel.py` (create)
- `packages/tl-tui/src/tl_tui/widgets/{document_register,record_view,record_screen}.py`, `document_text.py`, `details/documents.py`, `keymap.py`
- `packages/tl-tui/pyproject.toml`, `uv.lock`
- `packages/tl-tui/tests/**` for the above, `test_document_*`, `fakes_documents.py`, `fakes.py` only to give the fake a settable file list and bytes; snapshots of the document register and record view
- `packages/tl-tui/README.md` (a section "File preview", ≤ 25 lines, the document-register row, the Files tab), `docs/runbooks/tui-dev.md` (how to force/disable images: `TL_IMAGES=off|kitty|iterm2|sixel`; how to point `TL_VIEWER_CMD`)
- `docs/reports/P1-UX2/S4.md` (create)
S4 does NOT edit `labels_load.py` or `display.py` (S3's); a missing document label is reported.
Consequential pins (rule 12) as in S3: listed in the report, with a counterpart pinning the unchanged part.

## Steps
1. Dependencies and licence check first. 2. `temp`, `cache`, `viewer`, `render`/`_worker` with their hostile-file tests. 3. `FilePanel`. 4. Document log on `LogScreen` with actions and `v`. 5. Files tab. 6. README, runbook, report.

## Acceptance (run these, once)
```
just check
just gate packages/tl-tui | tee .gate/summary.txt
just gate-pg packages/tl-tui/tests/test_embedded_real_services.py
```
Expected: PASS on both adapters; `check_licences.py` clean. Tests never import `textual_image` outside the branch that needs it and never need a terminal image.

## Tests to add
- `packages/tl-tui/tests/test_preview_render.py` (new): a real small PDF renders (pages == 1, PNG header); not-a-PDF -> `not_pdf` without a child; a 60 MB file -> `too_big` without a child; a PDF whose MediaBox is 14400x14400 -> PNG within 1200 px; a worker that sleeps -> `timeout` and the child is gone; a truncated PDF -> `error`, no traceback text; second call is a cache hit (no child).
- `packages/tl-tui/tests/test_preview_cache.py`, `test_preview_viewer.py`, `test_preview_temp.py` (new): cache names, eviction, a hostile name never read; viewer argv list, no shell, leading-dash and space names; temp dir 0700 / file 0600, symlink in place refused, `cleanup()` removes everything, atexit hook registered once.
- `packages/tl-tui/tests/test_file_panel.py` (new): text fallback shows type, size, page count; with protocol `none` `textual_image` is not imported; `v` fetches then opens (launcher spy records the path; hash of the temp file equals the file's sha256); a new selection cancels the render; hidden record's file shows the same "not available" line as a missing one.
- `packages/tl-tui/tests/test_record_files_tab.py` (new): tab only when files exist; RFI fake with two files lists both with `file_line`.
- `test_document_register.py` updated (ids/keys pins) and extended: breadcrumb, actions bar from the fake `allowed_actions` (controller sees Issue, reader does not), `v` on a document with a PDF.

## Mutation (builder, own worktree, 3 lines in the report)
Sentinel plus at most 5: (1) drop the `%PDF-` header check; (2) drop the size cap; (3) never kill the child at timeout; (4) temp dir mode 0700 -> 0755; (5) viewer launched with `shell=True`. Each killed by a test above.

## Report requirements
`docs/reports/P1-UX2/S4.md` ≤ 60 lines: deviations first, licence lines, the caps used, consequential pins, commands, learnings.

## Escalation triggers
- Copyleft or unlicensed distribution (stop condition). pypdfium2 or textual-image fails to install through the proxy.
- The child-process design cannot be made to work on the box (state evidence; do not fall back to in-process rendering).
- A need to edit `schema/**`, a command, or the file routes.
