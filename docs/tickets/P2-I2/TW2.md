# P2-I2-TW2 — Web twin: constraint review page

Status: staged (r11; dispatch after TW1 merges: shared web files; names from the T04b report)
Tier: haiku
Kind: ticket
Review: full
Labels: web, read
Depends on: T04b T04c2 TW1
Branch: `p2/i2-tw2-web`
Worktree: harness-created under `/home/user/wt/i2/tw2`

## Goal
One server-rendered page, `packages/tl-web/src/tl_web/pages/constraints.py`, that renders the text module `packages/tl-tui/src/tl_tui/constraint_text.py` (Textual-free). No business logic in the page (AGENTS.md); same text, same hiding as the terminal screen.

## Brief
- Slug `constraints`: `GET /web/p/{project}/constraints` is the log (`CONSTRAINT_COLUMNS`, `CONSTRAINT_DROP`, `constraint_cells`, summary and group order from `constraint_text`; `?subject=<key>` keeps one subject's constraints, as `ConstraintScreen(client, project, subject_key)` does). Rows come from one `list_constraints(project, subject=..., limit=MAX_LIMIT)` read held in memory and grouped by the text module; no `constraint_groups` read (T04b judgement call, `(first 500 only)` note when total > rows held). The `o t a s b` keys are not on this page yet (docstring). The panel is `constraint_page(...)` (check the signature; `labels` is accepted but unused, `technical=True` adds `Technical`).
- Mirror methods: `list_constraints` (op `list_constraints_api`) and `get_constraint` (op `get_constraint_api`), routes in `packages/tl-api/src/tl_api/routes/constraints.py`. The route is word-checked (`core.constraint.view`): the web client must go through the same guard as `list_cwps` does (see `guard_action` in `reads.py`).
- Learning from T04b: `humanize("rfi")` gives `Rfi`; the page prints what the text module prints, no label fix here.
- Shape: copy `packages/tl-web/src/tl_web/pages/cwps.py` (a `WebLog` subclass: `columns`, `drop_order`, `load_rows`, `row_key`, `row_record`, `row_cells`, `panel_page`, `actions_for` returning `[]`, `summary_text`; `register("<slug>", Class)`; `router = web_router()`; `@router.get("/p/{project}/<slug>")`; the `/web` prefix comes from `web_router`). Read-only: no POST, no origin-check work.
- Text functions reach the page only through `tl_web/present.py` (the one door to `tl_tui`; add the text module to its import list and `__all__`; never import a Textual module). Reads go through `WebReadClient` (`reads.py`): add the mirror method(s) named below with their `MIRRORS` entry (`operation_id` of the API route, see the awp/constraints routes) in the style of `list_cwps`.
- Viewer is the session's, never widened; a hidden or unknown record answers the same 404 page (140). No record text beyond what the text module prints.
- Pins (union form, listed in the report): add the module to `PAGE_MODULES` of `routers.py` and `tests/test_web_imports.py`, the page row to `tests/walk.py`, the new methods to `tests/test_web_reads_mirror.py`.
- Test `packages/tl-web/tests/test_web_TW2.py`: copy the shape of `tests/test_web_cwp_log.py` (fake world from `packages/tl-tui/tests/fakes_iwp.py` and `seed_iwp`): rows render, empty state, hidden vs missing byte-identical, five readers (AGENTS.md walking-test rule). The real unpatched world is read once at the end.

## Shared-file rule (r11)
`reads.py`, `present.py`, `routers.py`, `tests/walk.py`, `test_web_reads_mirror.py` and `test_web_imports.py` are edited by every web twin: additive lines only, at list or dict ends, pins in union form. The orchestrator merges the twins one after another (a conflict in those files is lines to keep from both sides). The web package has no nav template and no dashboard page: there is no nav line to add.

## Context (read these, nothing else)
- `docs/reports/P2-I2/{T04b,T04c2}.md`, `packages/tl-tui/src/tl_tui/constraint_text.py`, `packages/tl-tui/src/tl_tui/widgets/constraint_screen.py` (reads only), `packages/tl-web/src/tl_web/pages/cwps.py`, `packages/tl-web/src/tl_web/{present,reads,routers}.py`, `packages/tl-web/tests/test_web_cwp_log.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/constraints.py` (create), `packages/tl-web/tests/test_web_TW2.py` (create), `packages/tl-web/src/tl_web/{present,reads,routers}.py` (additive lines), `packages/tl-web/tests/{walk,test_web_reads_mirror,test_web_imports}.py` (union pins), `docs/reports/P2-I2/TW2.md`

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-web/tests/test_web_TW2.py packages/tl-web/tests/test_web_imports.py packages/tl-web/tests/test_web_confidentiality_walk.py packages/tl-web/tests/test_web_reads_mirror.py
```

## Report requirements
Standard, <= 60 lines, deviations first, pins listed. Commits `P2-I2-TW2: ...`, trailer as other tickets.

## Escalation triggers
- Stop if the text module needs a change, or the page needs a read the web client cannot mirror (name it).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
