# P2-WEB1-T12b — movements page

Status: staged (activation list in `M4-TWINS.md`)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T09b, p2/i3 merged into p2/web1, the materials reads seam (r9), T17 (seed)
Branch: `p2/web1-t12b-movements`

## Goal
`GET /web/p/{project}/movements` shows the stock movements log (date, kind, lot, item, quantity, for, from, to, by) with the terminal movement screen's columns, cells, panel and summary. One module, `tl_web/pages/movements.py`.

## Pins (this file wins; then `M4-TWINS.md`, then `TWINS.md`)
1. `LOG_NAME = "Movements"`, `columns = MOVEMENT_COLUMNS`, `drop_order = MOVEMENT_DROP`. Row `MovementView`.
2. Query strings: `?lot=` (text), `?kind=` (one of the kinds in the rows read, as `KIND_WORDS` keys; else absent, narrows after the read as the screen does) and `?period=` (a member of `materials_text.PERIODS`, else `all`). `since, until = present.materials_text.period_range(period, date.today().isoformat())` (the page may read the clock, the module may not); `list_materials_movements(project, lot=, since=, until=, limit=500)`.
3. `row_key = str(row.seq)`; `row_record = (f"#{row.seq}", the Kind cell)`. Number `#12` is in the panel URL: quote it (the base class does).
4. Panel (no call), as the screen's `panel_text`: cells `movement_cells(row, MOVEMENT_COLUMNS, self.labels)` (the screen's `PANEL_COLUMNS` is the same nine) as one property line each, plus `Reason` (`row.reason`) and `Person` (`row.person`), in a `present.layout.Page(identity=present.layout.identity_line(f"#{row.seq}", kind_cell), sections=(present.layout.Section("", props),))` with `present.layout.prop(name, value)`; render with `present.plain_lines`.
5. Summary `present.materials_text.movement_summary(len(rows), len(all_read), kind=, period=, lot=)`.

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`, `M4-TWINS.md`
- `packages/tl-web/src/tl_web/pages/wbs.py`, `packages/tl-web/tests/test_web_wbs_log.py` (models)
- `packages/tl-tui/src/tl_tui/materials_text.py` (movement half), `packages/tl-tui/src/tl_tui/widgets/movement_screen.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: `packages/tl-tui/tests/fakes_materials_seed.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/movements.py` (replace the stub)
- `packages/tl-web/tests/test_web_movements_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T12b rows`)
- `docs/reports/P2-WEB1/T12b.md` (create)

## Tests to add
`test_web_movements_log.py`: cases (a)-(h) and (j) of TWINS.md for slug `movements` over the seed. Case (f) does not apply (no panel read); say so. Then: `?kind=` keeps one kind and an unknown kind is ignored; `?lot=`; `?period=zzz` is `all`; the Qty cell is signed (`+` receive, `-` issue); the panel of `#<seq>` has Reason and Person. Screenshot `T12b-movements.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of the PNG. Commit subject `P2-WEB1-T12b: ...`. Setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`.

## Escalation triggers
- *Blocked* if a mirror raises `UnsupportedRead`, the text module needs a Textual import, or a view lacks a field the pin names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
