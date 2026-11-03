# P2-WEB1-T13b — MTO lines page

Status: staged (activation list in `M4-TWINS.md`)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T09b, p2/i3 merged into p2/web1, the materials reads seam (r9), T17 (seed)
Branch: `p2/web1-t13b-mto`

## Goal
`GET /web/p/{project}/mto` shows the material take-off lines (number, item, for, required, reserved, issued, short, need by) with the terminal MTO screen's columns, cells, panel and summary; the panel shows source, coverage, reservations and open receipts. One module, `tl_web/pages/mto.py`.

## Pins (this file wins; then `M4-TWINS.md`, then `TWINS.md`)
1. `LOG_NAME = "Take-off lines"`, `columns = MTO_COLUMNS`, `drop_order = MTO_DROP`. Row `MtoLineView`. `row_key = row.key`, `row_record = (row.key, row.item_title)`; the key holds `/` and `@` (`<doc>@<rev>/MTO...`): the panel route takes the path as it is.
2. Query strings `?short=1` (short lines only) and `?wp=<work package number>` (text, else absent), passed as `short_only`, `work_package` to `list_materials_mto_lines(project, work_package=, short_only=, limit=500)`.
3. Panel: `detail = get_materials_mto_line(project, row.key)`; `present.plain_lines(present.mto_text.mto_page(detail, self.labels, technical=self.technical))`. A 404 is the one 404 page.
4. Summary `present.mto_text.summary_line(len(rows), total, short_only=, work_package=, text="")`.

## Context (read these, nothing else)
- `docs/tickets/P2-WEB1/TWINS.md`, `M4-TWINS.md`
- `packages/tl-web/src/tl_web/pages/documents.py`, `packages/tl-web/tests/test_web_document_log.py` (models)
- `packages/tl-tui/src/tl_tui/mto_text.py`, `packages/tl-tui/src/tl_tui/widgets/mto_screen.py`
- `docs/tickets/P2-WEB1/provided/shot_recipe.py`
may explore: `packages/tl-tui/tests/fakes_materials_seed.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/mto.py` (replace the stub)
- `packages/tl-web/tests/test_web_mto_log.py` (create)
- `packages/tl-web/tests/walk.py` (only: your row under `# --- T13b rows`)
- `docs/reports/P2-WEB1/T13b.md` (create)

## Tests to add
`test_web_mto_log.py`: cases (a)-(h) and (j) of TWINS.md for slug `mto` over the seed. Case (i): applies if `mto_page` shows technical rows, else REFUSAL only. Then: `?short=1` keeps the short line; `?wp=` keeps one work package; a covered line's state reads `Covered`, a short one `Short N UOM`; the panel of a key with `/` and `@` is found; reservations and open receipts tables. Screenshot `T13b-mto.png`.

## Acceptance
As TWINS.md. Report: also the `ls -l` of the PNG. Commit subject `P2-WEB1-T13b: ...`. Setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`.

## Escalation triggers
- *Blocked* if a mirror raises `UnsupportedRead`, the text module needs a Textual import, or a view lacks a field the pin names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
