# P2-WEB1-T02 — document log page

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web, api
Depends on: S3, S4 (merged), the `panel_image` seam (trunk of this branch, commit 7c0544d), `present.file_text` (17e12bf)
Branch: `p2/web1-t02-document-log`

## Goal
`GET /web/p/{project}/documents` shows the document register in the log standard: the seven regions, the terminal's columns, cells, panel and summary, and page 1 of the current revision's PDF at the top of the panel. One new module `tl_web/pages/documents.py`; `routers.PAGE_MODULES` already lists it. No actions on this page in i1 (see Pins).

## Brief references (pasted)
> Columns, panels and summaries come from the same functions as the terminal (`document_text.COLUMNS`, `DROP`, `row_cells`, `detail_lines`, `summary_line`). Hidden = missing (ADR-0016): a hidden or unknown number is the one 404 page. `tl_web` imports terminal names only through `tl_web.present`, never `sqlalchemy`, `cur_*`, `tl_core` query modules or Textual.
> Page 1 (document log panel): `<img src="/web/files/{id}/page1.png?scope=...">`, with the text line of `file_text.file_line` (`PDF document  1.2 MB  3 pages`) when no picture is available.

## Pins (this file wins over the spec)
1. **Rows.** `self.client.list_documents(project, limit=500)` (no state, type or void filter in i1; `?q=` is the page's own text filter). Row type `DocumentView`; `row_key = row.id`; `row_record = (row.number, row.title)`; `columns = present.document_text.COLUMNS`, `drop_order = present.document_text.DROP`; `LABEL_TYPES = ("documents.Document",)`; `LOG_NAME = "Documents"`.
2. **Cells** are `present.document_text.row_cells(row, self.labels, technical=self.technical)`.
3. **Summary** is `present.document_text.summary_line(n, n, state=None, doc_type=None, include_void=False, text="", labels=self.labels)` with `n = len(rows)`; keep it in `self._summary`, as T01 does.
4. **Panel text.** Read the document in full once per request: `full = self.client.get_document(self.project, row.number)`. Lines are `present.document_text.detail_lines(full, self.labels, technical=self.technical)`, then, only when the file list below is not empty, a blank line, the line `Files`, and one `present.file_text.file_line(f.filename, f.content_type, f.size)` per file.
5. **Files of the panel.** `rev = present.document_text.file_revision(full)`; if `rev` is not `None`, `files = self.client.list_record_files(rev.id)` (a list of `FileInfo`: `.file_id .scope .filename .content_type .size`; `[]` when there are none). Cache `(full, files)` per number in a dict on the instance so the panel text and `panel_image` share one read.
6. **Picture.** `panel_image(row)` returns `/web/files/{file_id}/page1.png?scope={quote(scope, safe='')}` for the first file whose `content_type == "application/pdf"` or whose name ends `.pdf` (case-insensitive), using that file's own `.scope`; `""` when there is none. (The base template shows it; the S3 route does the visibility check and the render.)
7. **No actions.** The document commands have no `ACTION_UI` row (the terminal builds them inside its screen), so override `actions_for` to return `[]`. Do not call `allowed_actions`.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_web/log.py   (see its docstring for the recipe; docs/reports/P2-WEB1/S4.md "Recipe for T15")
class WebLog[Row]:  # hooks: LOG_NAME, LABEL_TYPES, columns, drop_order, load_rows, row_key, row_record, row_cells, panel_text, summary_text, actions_for
    def panel_image(self, row: Row) -> str: return ""     # NEW seam: a same-origin picture URL for the top of the panel
def register(slug: str, cls: type[WebLog[Any]]) -> None: ...
# tl_web/present.py re-exports: document_text, file_text, plain_lines, as_client
# document_text: COLUMNS, DROP, row_cells(view, labels, *, technical), detail_lines(view, labels, *, technical) -> list[str],
#                summary_line(shown, total, *, state, doc_type, include_void, text, labels), file_revision(view) -> RevisionView | None
# file_text.file_line(name, content_type, size, pages=None) -> str
# WebReadClient.list_documents(project, *, limit=1000) -> list[DocumentView]; .get_document(project, number) -> DocumentView
# WebReadClient.list_record_files(record_id) -> list[FileInfo]
```
`DocumentView` (`.id .number .title .state .doc_type .discipline .current_revision_code ... .revisions`), `RevisionView` (`.id .code .state .is_current ...`) are in `tl_mod_documents.views`: import them under `TYPE_CHECKING` only, and quote the base: `WebLog["DocumentView"]` (a bare name fails at import, T01 learning).

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `packages/tl-web/src/tl_web/pages/correspondence.py` (the model page: same shape, copy its skeleton)
- `packages/tl-web/src/tl_web/log.py` (docstring, `WebLog`, `panel_image`)
- `dev/accept/P2-WEB1/T15.py` (the model acceptance script) and `dev/accept/P2-WEB1/T01.py` (how a read is patched with `mock.patch.object`)
- `packages/tl-modules/documents/src/tl_mod_documents/views.py` (`DocumentView`, `RevisionView`, to build the script's views)
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/documents.py` (create)
- `dev/accept/P2-WEB1/T02.py` (create)
- `docs/reports/P2-WEB1/T02.md` (create)

## Steps
1. Create `pages/documents.py`: `router = web_router()`, `DocumentWebLog(WebLog["DocumentView"])` per the Pins, `register("documents", DocumentWebLog)`, and `GET /p/{project}/documents` (`q`, `sel`, `mode` query strings) returning `DocumentWebLog.page(...)`.
2. Write `dev/accept/P2-WEB1/T02.py` as T15.py does (load `S4.py` as a module, switch its demo page off, `S4.World`, `world.web("alice")`). The ledger holds no documents, so the script builds three `DocumentView`s itself and patches the three reads for the whole run with `mock.patch.object(WebReadClient, ...)`: `list_documents` returns the three (ISO-1001 with a current revision `A` that has one PDF file, ISO-1002 with a current revision whose file is `notes.txt` / `text/plain`, ISO-1003 with no revisions); `get_document(project, number)` returns the one with that number or raises `KeyError`; `list_record_files(record_id)` returns `FileInfo`-shaped `types.SimpleNamespace(file_id, scope="project:P123", filename, content_type, size)` for the revision ids that have files and `[]` otherwise. Checks (one `PASS <letter>: ...` line each, exit 1 on the first failure): (a) `routers.page_routers()` includes the router of `tl_web.pages.documents` and `LOGS["documents"].SLUG == "documents"`; (b) alice's page has the seven region ids in order, the first three headers are Number, Title, State, and each row's cells equal `document_text.row_cells` for the same view (map columns by name as T15 does); (c) the panel route for ISO-1001 returns `detail_lines(...)` then a blank line, `Files` and the `file_line` of the PDF, and its HTML has exactly one `<img` whose `src` is `/web/files/<file id>/page1.png?scope=project%3AP123`; the panel of ISO-1002 has the `file_line` (kind `File` or per `file_kind`) and no `<img`; the panel of ISO-1003 has neither the `Files` line nor an `<img`; (d) the page itself (first row selected) also carries the `<img>` of ISO-1001 inside `#log-panel`; (e) `#log-status` equals `summary_line(3, 3, ...)`; (f) `?q=1002` leaves only ISO-1002 in the table, and `/panel/ISO-9999` answers 404 with the same bytes as a second unknown number; (g) a request without a cookie is 303 to `/web/sign-in`; (h) `#log-actions` has no `data-command` button for any row (the bar holds only the Open link).

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-WEB1/T02.py
```
Expected: `just check` clean; every check prints `PASS`, exit 0. Do not run `S4.py` (its demo page owns a slug the real pages use; T02.py switches it off). Paste the last 10 lines of each in the report.

## Tests to add
None here. The tests piece (S5) writes `packages/tl-web/tests/test_web_document_log.py` (page-1 image and text fallback) and the walk entries.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), at most 60 lines, plus the pasted outputs and a line saying no pytest was run (deferred). Commit subject `P2-WEB1-T02: <summary>`; no model names in any committed file. Do not discuss the commit trailer. Commit message: end it with the attribution trailer the harness requires, then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and report *Blocked* if a terminal function the page needs is reachable only through `widgets/*` (Textual), if `WebReadClient` raises `UnsupportedRead` for one of the three reads, or if the script cannot construct `S4.World` (say what failed; do not edit `S4.py`).
- Stop if the picture needs any change to `log.py`, the templates or the CSS (the seam is complete; say what is missing).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
