# P2-WEB1-S6 — Record screen on the web: Textual-free record text modules, trace and conformance mirrors, the frame with Details, Properties and History

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: web, tui, security
Depends on: S4 (merged), T15, T01, T05 (merged); T02 is independent
Branch: `p2/web1-s6-record-screen`
Approver: none beyond the `full` reviewer and the C4 security review (Sec row: a hidden record is missing before any tab read).

## Goal
`GET /web/p/{project}/records/{record_id}` shows a record as the terminal's record screen does: heading `number · subject`, state line with badges, the actions bar, and the tabs. This piece builds the hard part: the record-screen logic that today lives inside Textual widgets moves into four Textual-free modules (the widgets then call them, so terminal and web share one implementation), the web gets the two reads the tabs need, and the page frame ships with the Details, Properties and History tabs plus a tab registry. Links, Trace, Thread and Files are then one Haiku ticket each (a tab module + a template over these modules), written after this merges. Decision D16/Q3 (approved): record screen = piece S6; cut it so Haiku can finish what passes `01-tiers.md` §6.

## Setup (every acceptance run, new worktrees need it)
```
cd /home/user/wt/<your worktree> && uv sync --all-packages && export NODE_OPTIONS=--max-old-space-size=6144
```
`just check` takes over 120 s: run it in the background and wait for the harness. Commit subjects are `P2-WEB1-S6: <imperative summary>`. End each commit message with the attribution line your harness requires, then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Brief references
`docs/build-spec/specs/web-client-i1.md` **§8 first paragraph** and the T3/T4 rows of §11 (this file replaces them), with these pins (this file wins):
1. **Move, do not copy.** Behaviour stays identical; existing tl-tui tests pass **unchanged** (no test file is edited). Every moved name stays importable from the module it left (`from tl_tui.widgets.record_view import event_summary` still works: import it back, `# noqa: F401` only where the widget does not use it).
   - `tl_tui/record_text.py` (from `widgets/record_view.py`): `details_lines`, `event_label`, `event_summary` (and the private `_or_empty`, `_sorted_keys`, `_plain_keys`, `_EVENT_WORDS` they need); and new pure pieces cut from the widget methods: `header_parts(record, badges, *, technical) -> HeaderParts` (frozen dataclass: `identity` = `"{key} · {title}"`, `status`, `version` (`" · v3"` in technical mode, else `""`), `mark` (`conformance_mark(record.get("conformance"))`), `rest` (` · voided` + ` · {badges}`)); `badges_text(entered_at, counts) -> str` (the string-building half of `_badges`: `since <time>`, `N link(s)`, stale / broken / suggested; the two reads and their `except` stay in the widget); `history_columns(technical) -> tuple[str, ...]` and `history_cells(event, labels, *, technical) -> tuple[str, ...]` (the cells `_draw_history` adds per row). `_draw_header`, `_badges` and `_draw_history` then call them and only style/add rows.
   - `tl_tui/properties_text.py` (from `widgets/psets_tab.py`): `psets_text`, `rule_text`, `value_text`, `unit_text`, `adhoc_lines`, `HEADER`, `CUSTOM_RULE`, `ADD_LINE`, `LEGEND` and the private helpers they use.
   - `tl_tui/links_text.py` (from `widgets/links_tab.py`): `TableRow`, `status_text`, `pin_text`, `group_title`, `missing_line`, `build_rows` (+ `_link_row`, `_header_row`, `SUGGESTED`).
   - `tl_tui/trace_text.py` (from `widgets/trace_tab.py`): `node_text`, `tree_lines`, `head_text`, `DIRECTIONS`, `DIRECTION_WORDS`, `MIN_DEPTH`, `MAX_DEPTH`, the `Direction` type.
   None of the four imports `textual`, `rich` or any `tl_tui.widgets` module (`tl_web.present` must still leave `textual` out of `sys.modules`). `tl_web/present.py` re-exports the four modules (4 import lines + `__all__`).
2. **Two reads.** `WebReadClient.conformance(record_id)` mirroring `get_conformance` and `WebReadClient.trace(record_id, *, depth=2, direction="both")` mirroring `get_record_trace`, in the style of the existing methods; both rows added to `MIRRORS`. They answer through `_call`, so the route's guard and visibility apply. (S5's mirror test counts them: nothing else may be added to `MIRRORS`.)
3. **Action bar helper.** `WebLog._action_views` becomes the module function `action_views(project, record_id, actions) -> list[dict]` in `log.py`; the method calls it. Same output byte for byte (T15/T01 scripts must still pass).
4. **The page** `tl_web/pages/record.py`, `GET /p/{project}/records/{record_id}` with query `tab` (default `details`) and `mode`:
   - `PROJECT_ID` check, then `client.get_record_by_id(record_id)`; `None`, or `record["scope"] != f"project:{project}"`, or an unknown `tab` name, or a tab that is not visible: the one 404 page (`not_found_page`), before any other read. Hidden = missing (ADR-0016).
   - Technical mode as `WebLog.for_request`: `?mode=technical` honoured for an admin only, else plain and `#log-status` shows `present.REFUSAL`; carried on every link of the page, never stored.
   - Regions, in order: `#rec-header` (three lines: `identity`; `status`+`version`+` · `+`mark`+`rest`; nothing else), `#rec-tabs` (a `<nav>` of plain links `?tab=<name>[&mode=technical]`, `aria-current="page"` on the active one), `#log-actions` (the existing `actions.html` partial fed by `action_views(project, record_id, offered_actions(client.allowed_actions(record_id)))`, `open_url` empty), `#log-panel` (empty `div`, the target the ask-forms swap into), `#rec-body` (the active tab), `#log-status`. No JS beyond what `base.html` loads.
   - Header badges: `since <time>` from `client.workflow_status(id).entered_at` formatted with `present.text.timestamp`, link counts from `client.link_counts([id])`; either read failing leaves the badge out (as the widget does), through `record_text.badges_text`.
   - **Tab registry** in `record.py`: `@dataclass(frozen=True) class RecordCtx` (`request, project, record, labels, technical, client, mode_query`), `@dataclass(frozen=True) class Tab` (`name, label, template, build: Callable[[RecordCtx], dict[str, Any]], visible: Callable[[RecordCtx], bool] = lambda _: True`), `def tab(t: Tab) -> None` (refuses a duplicate name), `ORDER = ("details", "properties", "links", "history", "trace", "thread", "files")` and `TAB_MODULES = ("tl_web.pages.record_links", "tl_web.pages.record_trace", "tl_web.pages.record_thread", "tl_web.pages.record_files")` loaded lazily on the first request (not at import; `find_spec` skips a module that does not exist yet, as `routers.py` does) so later tickets add one module each and edit nothing else. A tab renders by including `record/<template>` with the dict `build` returned. The three tabs of this piece are registered in `record.py`: Details (`details_for(...)` then `record_text.details_lines`, with a `DisplayMode` whose `.technical` is the page's), Properties (`form_metadata(scope, type, id)` and `conformance(id)`, text from `properties_text.psets_text(..., technical=)`; a read error becomes the line `Properties unavailable: ...` as in the widget; no add-property line on the web), History (`client.history(id)` newest first, a table: `history_columns` as headers, `history_cells` as cells, in a `<table>` inside `#rec-body`).
   - Templates `templates/record/{frame,details,properties,history}.html` (`frame.html` extends `base.html`); text goes in `<pre class="tl-panel-text">`, every value escaped (autoescape on, no `|safe`). `static/tl.css`: at most 20 lines for `#rec-tabs`. `pages/record.py` imports terminal names only through `tl_web.present`.

## Context (<= 10 files)
- `docs/templates/haiku-report.md`
- `packages/tl-tui/src/tl_tui/widgets/{record_view,psets_tab,links_tab,trace_tab}.py` (move from; read, then edit)
- `packages/tl-web/src/tl_web/{log,reads,present,actions,webroute}.py` (`pages/correspondence.py` is the model page; `actions.py::_gate` is the scope and 404 rule)
- `dev/accept/P2-WEB1/{T01,S4}.py` (World, Doc, expect, passed, patching a read)
may explore: `tl_tui/details/__init__.py` (`details_for`, `rows_page`), `tl_tui/display.py` (`DisplayMode`)

## Allowed paths
- create: `packages/tl-tui/src/tl_tui/{record_text,properties_text,links_text,trace_text}.py`, `packages/tl-web/src/tl_web/pages/record.py`, `packages/tl-web/src/tl_web/templates/record/{frame,details,properties,history}.html`, `dev/accept/P2-WEB1/S6.py`, `docs/reports/P2-WEB1/S6.md`
- modify: `packages/tl-tui/src/tl_tui/widgets/{record_view,psets_tab,links_tab,trace_tab}.py`, `packages/tl-web/src/tl_web/{reads,present,log}.py`, `packages/tl-web/src/tl_web/static/tl.css`
Not allowed: any test file (existing tests must pass unchanged), `tl_web/{app,routers,actions,csrf,session}.py`, `tl_api/**`, `tl_core/**`, other `tl_tui` files, `docs/reference/openapi.json` (the web routes are not in it), `uv.lock`.

## Acceptance (run once; no pytest of new tests, no `just gate`)
```
just check
uv run pytest -q packages/tl-tui/tests/test_record_view.py packages/tl-tui/tests/test_record_view_banner.py packages/tl-tui/tests/test_record_plain.py packages/tl-tui/tests/test_psets_tab.py packages/tl-tui/tests/test_properties_tab.py packages/tl-tui/tests/test_links_tab.py packages/tl-tui/tests/test_links_thread_plain.py packages/tl-tui/tests/test_trace_tab.py
uv run python dev/accept/P2-WEB1/S6.py
```
The pytest line is a regression sniff of the move (existing tl-tui tests only, the same kind of line S3 ran), expected all passed. `S6.py` (load `S4.py` as a module and switch its demo page off, as T15.py does; `S4.World`, forged RFIs and letters are the records; the expected text is computed in the script by calling the new pure modules on reads from `world.reads(name)`):
(a) imports: `record_text, properties_text, links_text, trace_text` import with `textual`, `rich` absent from `sys.modules`; the old names still import from the four widget modules; `MIRRORS` gained exactly `conformance` and `trace`;
(b) the frame: alice on a visible RFI (`?tab` absent) gets the regions `rec-header, rec-tabs, log-actions, log-panel, rec-body, log-status` in that order; `#rec-header` lines equal `header_parts` for the record; the nav lists the tabs of `ORDER` that are registered (details, properties, history here) with `aria-current` on Details;
(c) Details body equals `record_text.details_lines(details_for(...))` for the same record; Properties body equals `psets_text(...)` (or the `Properties unavailable: ...` line when the forged record has no form metadata: assert whichever the reads give); History rows equal `history_cells` newest first, plain headers `When, What, By, Summary`; admin with `?mode=technical` gets `#, When, Event, Actor, Summary`;
(d) hidden = missing: for the privileged and restricted RFIs alice gets the 404 page with the same bytes as an unknown record id; an RFI of another project scope, an unknown `tab`, and `tab=links` (not registered yet) are the same 404 page; no secret word appears in any answer for alice;
(e) technical mode: alice with `?mode=technical` sees plain text and `present.REFUSAL`; root sees raw rows; the `mode` is on every tab link;
(f) the actions bar of an RFI with offers lists the same `data-command` buttons as its log page (`/p/{project}/rfis` panel) for the same user; without a cookie the page is 303 to `/web/sign-in`;
(g) registry: register a fake `Tab("probe", ...)` in the script before `create_app` (template `record/details.html` reused) and see it in the nav and at `?tab=probe`; registering the same name twice raises; `TAB_MODULES` entries that do not exist are skipped;
(h) plain walk: `present.find_technical` over the visible text of the page in every tab as alice finds nothing (ids in attributes are allowed, not in text).

## Mutation guards (you run them, own worktree, 1 sentinel + <= 5 targeted, 3 lines)
Sentinel: baseline green. Targets: the scope comparison dropped (d red); `get_record_by_id` result used before the `None` check, so a hidden record reaches a tab read (d red); `technical` taken from `?mode` without the admin check (e red); `|safe` or autoescape off on a value (a planted `<` in a title shows raw, h/c red); a moved function changed in one branch of `event_summary` (the sniff pytest red).

## Cut line
If the product diff passes about 900 lines before the page is done, stop at a clean point and report: the order of work is (1) the four modules and the widget edits, with the sniff green, (2) the two mirrors and `present`, (3) the page. Whatever is done and green is committed; the report names the rest. Do not trade the move's exactness for speed.

## Tests for the end run (S5 writes them; this piece writes none)
`packages/tl-web/tests/test_web_record_details.py` (frame, Details, Properties, hidden 404, technical mode), `packages/tl-web/tests/test_web_record_tabs.py` (History, registry, nav), and the mirror count in `test_web_reads_mirror.py`.

## Report requirements
Standard piece report (<= 60 lines): deviations first; list of what moved where (names only); the sniff pytest tail; acceptance output (<= 5 lines per command); mutation result in 3 lines; the tab-module recipe for the follow-up tickets (the `Tab(...)` call a Links tab needs, the context fields, one example) with file:line; seams for S5; no discussion of the commit trailer; no model names in any committed file.

## Escalation triggers
- *Blocked* if: an existing tl-tui test needs editing; a moved function cannot leave its widget without changing its output; the Details renderers need a Textual import; `tl_web.present` would import Textual; any path outside Allowed is needed.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
