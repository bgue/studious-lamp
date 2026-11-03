# P2-WEB1-T04 — record screen: Thread and Files tabs

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S6 (merged), S3 (page-1 route), T05 (viewer page, merged), the `thread_text` re-export in `present.py` (this branch)
Branch: `p2/web1-t04-thread-files`

## Goal
`/web/p/{project}/records/{id}?tab=thread` (read-only) and `?tab=files` work. Two tab modules and two templates; `TAB_MODULES` already names `tl_web.pages.record_thread` and `tl_web.pages.record_files`. Do not edit `record.py`, `reads.py` or `present.py`. The frame refuses a hidden or other-project record before `build` runs.

## Brief references (pasted)
> Tabs are a registry. `tab(Tab(name, label, template, build))` at import; `build(ctx: RecordCtx) -> dict` may not return a frame name (`project record header nav actions open_url notice text tab_name tab_template csrf`). `RecordCtx(request, project, record, labels, technical, client, mode_query)`; links carry `ctx.mode_query`.
> Page 1: `<img src="/web/files/{id}/page1.png?scope=...">` for a PDF; full view `/web/p/{project}/files/{file_id}/view`; download `/web/files/{id}/content?scope=...` (`scope` URL-quoted with `safe=''`). At most 2 renders run at once (503 `preview_busy`), so the Files tab draws page 1 of the FIRST PDF only.
> Hidden = missing (ADR-0016): a file the viewer may not read is not in `list_record_files`.

## Pins (this file wins over the spec)
1. **Thread** (`pages/record_thread.py`, `record/thread.html`, `Tab("thread", "Thread", "thread.html", build)`). `before` from `ctx.request.query_params` is an int `>= 0` or `None` (anything else means `None`). `page = ctx.client.thread_page(ctx.record["id"], limit=50, before_seq=before)`. Returns `{"head": present.thread_text.header_text(page, ctx.labels, technical=ctx.technical), "lines": "\n".join(present.thread_text.message_lines(page, ctx.labels, technical=ctx.technical)), "empty": ..., "older": ...}`. `empty` is `"No messages yet."` when `page.enabled` and no lines, `"Threads are not switched on for this type."` when not `page.enabled`, else `""`. `older` is `?tab=thread&before=<page.next_before>` (plus `&mode=technical` when `ctx.mode_query` is not empty) when `page.next_before is not None`, else `""`. Template: `<p>{{ head }}</p>`, then the `empty` text or `<pre class="tl-panel-text">{{ lines }}</pre>`, then a link `Older messages` when `older`. Read-only: no composer, no form, no action.
2. **Files** (`pages/record_files.py`, `record/files.html`, `Tab("files", "Files", "files.html", build)`). `files = ctx.client.list_record_files(ctx.record["id"])` (`FileInfo`: `.file_id .scope .filename .content_type .size`). Table headers `list(present.details.FILE_COLUMNS_NO_PAGES)`; per file the cells `(f.filename, present.file_text.file_kind(f.content_type, f.filename), present.file_text.human_size(f.size))`. Each row also carries `view` = `/web/p/{ctx.project}/files/{f.file_id}/view` and `download` = `/web/files/{f.file_id}/content?scope={quote(f.scope, safe='')}`. `picture` is `/web/files/{id}/page1.png?scope={quote(scope, safe='')}` of the first file for which `is_pdf(f.content_type, f.filename)` (`from tl_web.pages.viewer import is_pdf`), else `""`. `empty` is `"No files."` when none. Template: the table (name cell plain text, then `<a>View</a>` and `<a>Download</a>` links, `<a>` text fixed), then, when `picture`, one `<img class="tl-page1" src="{{ picture }}" alt="Page 1">` (no width/height script, no inline style). Plain `{{ }}` only, never `|safe`.
3. A read that raises `NotImplementedError`, or an exception `body_for(exc)` maps (`from tl_api.errors import body_for`), shows `Thread unavailable: <mapped[1].message>` (Files: `Files unavailable: ...`) in `empty`, as `_properties` in `record.py` does. Anything else propagates.
4. Both tabs are visible to every viewer.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_web/pages/record.py:  Tab(name, label, template, build, visible=...);  tab(t: Tab) -> None;  ORDER = ("details", "properties", "links", "history", "trace", "thread", "files")
# tl_web/present.py re-exports: thread_text, file_text, details, plain_lines
# thread_text: header_text(page, labels=None, *, technical=True) -> str;  message_lines(page, labels=None, *, technical=True) -> list[str]
# file_text: file_kind(content_type, filename) -> str;  human_size(n) -> str;  details.FILE_COLUMNS_NO_PAGES = ("Name", "Type", "Size")
# tl_web/pages/viewer.py: is_pdf(content_type: str, filename: str) -> bool
# WebReadClient.thread_page(record_id, *, limit=50, before_seq=None) -> ThreadPage;  .list_record_files(record_id) -> list[FileInfo]
```
`ThreadPage` (`.enabled .dispatch_enabled .participants .messages .kinds .next_before .record`) is in `tl_core.threads.queries`: do not import it at run time; the script builds `types.SimpleNamespace` stand-ins with the attributes `header_text` and `message_lines` read (open `thread_text.py`); messages need `.author .posted_at .body .retracted .edited .dispatch`.

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `packages/tl-web/src/tl_web/pages/record.py` (docstring recipe, `_properties`)
- `packages/tl-tui/src/tl_tui/thread_text.py`
- `packages/tl-web/src/tl_web/pages/viewer.py` (`is_pdf`, the view and download URL shapes)
- `dev/accept/P2-WEB1/S6.py` (the model script: `url(world, key, query)`, `Page`-style parsers, `main`)
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/record_thread.py` (create)
- `packages/tl-web/src/tl_web/pages/record_files.py` (create)
- `packages/tl-web/src/tl_web/templates/record/thread.html` (create)
- `packages/tl-web/src/tl_web/templates/record/files.html` (create)
- `dev/accept/P2-WEB1/T04.py` (create)
- `docs/reports/P2-WEB1/T04.md` (create)

## Steps
1. Create the two modules and two templates per the Pins.
2. Write `dev/accept/P2-WEB1/T04.py` after `S6.py` (load `S4.py` with `S4.PAGE_SOURCE` emptied, `S4.World(Path(tmp))`, `alice, _ = world.web("alice")`, record `world.ids["answered"]`; `secret` and `restricted` are hidden from alice). Patch for the run with `mock.patch.object(WebReadClient, name, fake)`, started before the first request and stopped in `finally`: `thread_page` (records its `before_seq`; returns stand-ins: three messages, one with a multi-line body containing `<b>x</b>`, one retracted, `next_before=7`; a second stand-in with `enabled=False`) and `list_record_files` (returns `SimpleNamespace(file_id, scope="project:P123", filename, content_type, size)`: `a.pdf` application/pdf, `b.pdf` application/pdf, `n.txt` text/plain). Checks, one `PASS <letter>: ...` line each, exit 1 on the first failure: (a) the nav of the answered record lists Thread and then Files as its last two tabs (after History, and after Trace once that is registered); (b) Thread `<pre>` equals the joined `message_lines`, the head equals `header_text`, markup in a body is escaped; (c) the Older link is `?tab=thread&before=7`, and `?tab=thread&before=7` calls `thread_page` with `before_seq=7`; `before=x` and `before=-3` call it with `None`; (d) the `enabled=False` page shows `Threads are not switched on for this type.` and no `<pre>`; (e) Files: headers `Name Type Size`, rows equal `file_kind`/`human_size` cells, exactly one `<img` and its `src` is `/web/files/<a.pdf id>/page1.png?scope=project%3AP123`; each row has the View url `/web/p/P123/files/<id>/view` and the Download url `/web/files/<id>/content?scope=project%3AP123`; (f) no files shows `No files.` and no `<img`; (g) root with `?mode=technical` has `&mode=technical` on the Older link; alice has none; (h) `secret` and `restricted` with `?tab=thread` and `?tab=files` are the 404 page of an unknown id, byte for byte, and neither fake was called for them; a fake raising `NotImplementedError` gives `Thread unavailable:` with status 200.
   `S6.py` may now fail on the nav order; do not edit it (S5 replaces it with tests).

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-WEB1/T04.py
```
Expected: `just check` clean; every check prints `PASS`, exit 0. Do not run `S4.py`. Paste the last 10 lines of each in the report.

## Tests to add
None here. The tests piece (S5) writes the Thread and Files tab tests and the walk entries (five kinds of reader).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), at most 60 lines, plus the pasted outputs and a line saying no pytest was run (deferred). Commit subject `P2-WEB1-T04: <summary>`; no model names in any committed file. Do not discuss the commit trailer. Commit message: end it with the attribution trailer the harness requires, then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and report *Blocked* if a name you need is reachable only through `widgets/*` (Textual), if `record.py`, `reads.py`, `present.py` or a frame template needs a change, or if the script cannot construct `S4.World` (say what failed; do not edit `S4.py` or `S6.py`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
