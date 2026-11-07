# P2-WEB1-T03 — record screen: Links and Trace tabs

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S6 (merged; the tab registry in `pages/record.py`)
Branch: `p2/web1-t03-links-trace`

## Goal
`/web/p/{project}/records/{id}?tab=links` and `?tab=trace` work. Two new tab modules, each one `build` function and one `tab(Tab(...))` line, and two templates. `TAB_MODULES` in `record.py` already names `tl_web.pages.record_links` and `tl_web.pages.record_trace`; do not edit `record.py`, `reads.py` or `present.py`. The frame has already refused a hidden or other-project record before `build` runs; `build` only reads through `ctx.client`.

## Brief references (pasted)
> Tabs are a registry. A tab module calls `tab(Tab(name, label, template, build))` at import and edits nothing else. `build(ctx: RecordCtx) -> dict` returns the values its template uses; it may not return a frame name (`project record header nav actions open_url notice text tab_name tab_template csrf`). Links to other pages carry `ctx.mode_query` (`?mode=technical` or `""`). `RecordCtx(request, project, record, labels, technical, client, mode_query)`.
> Hidden = missing (ADR-0016). `tl_web` imports terminal names only through `tl_web.present`, never `sqlalchemy`, `tl_core` query modules or Textual.

## Pins (this file wins over the spec)
1. **Links** (`pages/record_links.py`, template `record/links.html`, `Tab("links", "Links", "links.html", build)`). `views = ctx.client.links_of(ctx.record["id"])`; `rows = present.links_text.build_rows(views)`. `build` returns `{"headers": list(present.links_text.COLUMNS), "rows": [{"group": r.link_id is None, "cells": list(r.cells)} for r in rows], "empty": "No links yet." if not rows else ""}`. Template: a `<table class="tl-history">` with `<th scope="col">` per header, one `<tr>` per row, `class="tl-group"` on a group row; when `empty` is set, a `<p>` with it and no table. Plain `{{ }}` only, never `|safe`. No per-row links, no expected-links lines (`expected_links` is not a web read), no actions.
2. **Trace** (`pages/record_trace.py`, template `record/trace.html`, `Tab("trace", "Trace", "trace.html", build)`). Query values: `depth` (int, default 2, clamped to `present.trace_text.MIN_DEPTH..MAX_DEPTH`; anything not an integer means 2) and `dir` (one of `present.trace_text.DIRECTIONS`, default `both`; anything else means `both`), read from `ctx.request.query_params`. `root = ctx.client.trace(ctx.record["id"], depth=depth, direction=direction)`. `build` returns `{"head": present.trace_text.head_text(depth, direction), "lines": "\n".join(present.trace_text.tree_lines(root)), "controls": [...]}`; `controls` is one dict `{"label", "url", "current"}` per direction (label `DIRECTION_WORDS[d]`, current when chosen) and a `Less`/`More` pair for depth (omit the one that would leave the clamp). Every control url is `?tab=trace&depth=<n>&dir=<d>` plus `&mode=technical` when `ctx.mode_query` is not empty. Template: `<p>{{ head }}</p>`, a `<nav id="trace-controls">` of the controls (`aria-current="true"` on the current one), then `<pre class="tl-panel-text">{{ lines }}</pre>`.
3. A read that raises `NotImplementedError`, or an exception `body_for(exc)` maps (`from tl_api.errors import body_for`), shows `Trace unavailable: <mapped[1].message>` (or the same for Links) as the `lines` / `empty` text, as `_properties` in `record.py` does. Anything else propagates.
4. Tabs are visible to every viewer (`visible` left at its default).

## Interfaces (verbatim from repo at the branch point)
```python
# tl_web/pages/record.py
@dataclass(frozen=True)
class Tab: name: str; label: str; template: str; build: Callable[[RecordCtx], dict[str, Any]]; visible: Callable[[RecordCtx], bool] = ...
def tab(t: Tab) -> None: ...      # a second tab of the same name raises ValueError
ORDER = ("details", "properties", "links", "history", "trace", "thread", "files")
# tl_web/present.py re-exports: links_text, trace_text, plain_lines, as_client, load_labels
# links_text: COLUMNS = ("", "Key", "Title", "Status", "Pin", "Note"); TableRow(link_id: str | None, cells: tuple[str, ...]); build_rows(views) -> list[TableRow]
# trace_text: MIN_DEPTH = 1; MAX_DEPTH = 6; DIRECTIONS = ("both", "out", "in"); DIRECTION_WORDS: dict[str, str];
#             head_text(depth, direction) -> str; tree_lines(root: TraceNode) -> list[str]
# WebReadClient.links_of(record_id, *, include_retracted=False) -> list[LinkView]; .trace(record_id, *, depth=2, direction="both") -> TraceNode
```
`TraceNode` (`.key .title .label .depth .link_status .voided .more .children`) is in `tl_core.services.link_trace`; `LinkView` in `tl_core.services.link_queries`: import neither at run time (a script builds `types.SimpleNamespace` stand-ins; `TYPE_CHECKING` only in the modules).

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `packages/tl-web/src/tl_web/pages/record.py` (docstring recipe, `_properties`, `_history`)
- `packages/tl-web/src/tl_web/templates/record/history.html` (the table markup to copy)
- `packages/tl-tui/src/tl_tui/links_text.py` and `trace_text.py` (the pure text)
- `dev/accept/P2-WEB1/S6.py` (the model script: `Page`-style parsers, `url(world, key, query)`, `main`)
may explore: (none)

## Allowed paths
- `packages/tl-web/src/tl_web/pages/record_links.py` (create)
- `packages/tl-web/src/tl_web/pages/record_trace.py` (create)
- `packages/tl-web/src/tl_web/templates/record/links.html` (create)
- `packages/tl-web/src/tl_web/templates/record/trace.html` (create)
- `dev/accept/P2-WEB1/T03.py` (create)
- `docs/reports/P2-WEB1/T03.md` (create)

## Steps
1. Create the two modules and two templates per the Pins.
2. Write `dev/accept/P2-WEB1/T03.py` after `S6.py` (load `S4.py` as a module with `S4.PAGE_SOURCE` emptied, `world = S4.World(Path(tmp))`, `alice, _ = world.web("alice")`, record `world.ids["answered"]`; keys `secret` and `restricted` are hidden from alice). The ledger holds no links, so patch both reads for the run: `mock.patch.object(WebReadClient, "links_of", fake)` and `"trace"`, started before the first request and stopped in `finally`. `fake_links_of` returns `SimpleNamespace` link views with the attributes `build_rows` and `status_text` read (open `links_text.py`): two `outbound` links of one relation, one `suggested`. `fake_trace` returns a `SimpleNamespace` tree (root plus two children, one with `more=2`) and records its `depth`/`direction` arguments. Checks, one `PASS <letter>: ...` line each, exit 1 on the first failure: (a) the nav of the answered record lists Links directly after Properties and Trace directly after History (labels in order; Thread and Files may follow once registered); (b) the Links page: headers equal `COLUMNS`, rows equal `build_rows(...)` cells for the same views, group rows marked, markup in a title (`<b>x</b>`) is escaped in the HTML; (c) empty `links_of` shows `No links yet.` and no table; (d) the Trace page `<pre>` equals `"\n".join(tree_lines(fake_tree))` and the head line equals `head_text(2, "both")`; (e) `?tab=trace&depth=9&dir=sideways` calls `trace` with depth 6 and `both`; `depth=x` gives 2; (f) every control url starts `?tab=trace&depth=`, and root with `?mode=technical` has `&mode=technical` on all of them while alice has none; (g) `secret` and `restricted` with `?tab=links` and `?tab=trace` are the 404 page of an unknown id, byte for byte, and neither fake was called for them; (h) a `fake_trace` raising `NotImplementedError` shows `Trace unavailable:` and status 200.
   `S6.py` may now fail on the nav order and on `?tab=links`; do not edit it (S5 replaces it with tests).

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-WEB1/T03.py
```
Expected: `just check` clean; every check prints `PASS`, exit 0. Do not run `S4.py`. Paste the last 10 lines of each in the report.

## Tests to add
None here. The tests piece (S5) writes the Links and Trace tab tests and the walk entries.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), at most 60 lines, plus the pasted outputs and a line saying no pytest was run (deferred). Commit subject `P2-WEB1-T03: <summary>`; no model names in any committed file. Do not discuss the commit trailer. Commit message: end it with the attribution trailer the harness requires, then the line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and report *Blocked* if a name you need is reachable only through `widgets/*` (Textual), if `record.py`, `reads.py`, `present.py` or a template of the frame needs a change, or if the script cannot construct `S4.World` (say what failed; do not edit `S4.py` or `S6.py`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
