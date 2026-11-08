# P2-I2-TW3 — Web twin: readiness page

Status: staged (r11; dispatch after TW2 merges: shared web files; names from the T07a report)
Tier: haiku
Kind: ticket
Review: full
Labels: web, read
Depends on: T07a T04c2 TW2
Branch: `p2/i2-tw3-web`
Worktree: harness-created under `/home/user/wt/i2/tw3`

## Goal
One server-rendered page, `packages/tl-web/src/tl_web/pages/readiness.py`, that renders the text module `packages/tl-tui/src/tl_tui/readiness_text.py` (Textual-free). No business logic in the page (AGENTS.md); same text, same hiding as the terminal screen.

## Brief
- Slug `readiness` with the IWP number as a query: `GET /web/p/{project}/readiness?number=<IWP number>` (the `WebLog` shape has one path per log; a missing or unknown number answers the same 404 page, 140). Rows from `readiness_rows`, columns `READINESS_COLUMNS`, drop `READINESS_DROP`, summary `readiness_summary`, panel `readiness_page`; not evaluated: `not_evaluated_text` (signatures in `readiness_text.py`; the terminal `ReadinessScreen(client, project, number)` shows the read: `get_iwp_readiness`). A check with a reference shows the reference as text; no Enter-to-open on the web.
- Mirror method: `get_iwp_readiness` (op `get_iwp_readiness`, `routes/awp.py` line 314); the API route reads through `visible_readiness` (D32), so hidden references are already dropped.
- Backlog tile: NOT in this ticket. The web package has no project dashboard page and no `get_setting` read (the backlog target is a setting). Follow-up line in STATE (T08 text module `backlog_text`).
- Shape: copy `packages/tl-web/src/tl_web/pages/cwps.py` (a `WebLog` subclass: `columns`, `drop_order`, `load_rows`, `row_key`, `row_record`, `row_cells`, `panel_page`, `actions_for` returning `[]`, `summary_text`; `register("<slug>", Class)`; `router = web_router()`; `@router.get("/p/{project}/<slug>")`; the `/web` prefix comes from `web_router`). Read-only: no POST, no origin-check work.
- Text functions reach the page only through `tl_web/present.py` (the one door to `tl_tui`; add the text module to its import list and `__all__`; never import a Textual module). Reads go through `WebReadClient` (`reads.py`): add the mirror method(s) named below with their `MIRRORS` entry (`operation_id` of the API route, see the awp/constraints routes) in the style of `list_cwps`.
- Viewer is the session's, never widened; a hidden or unknown record answers the same 404 page (140). No record text beyond what the text module prints.
- Pins (union form, listed in the report): add the module to `PAGE_MODULES` of `routers.py` and `tests/test_web_imports.py`, the page row to `tests/walk.py`, the new methods to `tests/test_web_reads_mirror.py`.
- Test `packages/tl-web/tests/test_web_TW3.py`: copy the shape of `tests/test_web_cwp_log.py` (fake world from `packages/tl-tui/tests/fakes_iwp.py` and `seed_iwp`): rows render, empty state, hidden vs missing byte-identical, five readers (AGENTS.md walking-test rule). The real unpatched world is read once at the end.

## Shared-file rule (r11)
`reads.py`, `present.py`, `routers.py`, `tests/walk.py`, `test_web_reads_mirror.py` and `test_web_imports.py` are edited by every web twin: additive lines only, at list or dict ends, pins in union form. The orchestrator merges the twins one after another (a conflict in those files is lines to keep from both sides). The web package has no nav template and no dashboard page: there is no nav line to add.

## Context (read these, nothing else)
- `docs/reports/P2-I2/{T07a,T04c2}.md`, `packages/tl-tui/src/tl_tui/readiness_text.py`, `packages/tl-tui/src/tl_tui/widgets/readiness_screen.py` (reads only), `packages/tl-web/src/tl_web/pages/cwps.py`, `packages/tl-web/src/tl_web/{present,reads,routers}.py`, `packages/tl-web/tests/test_web_cwp_log.py`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/readiness.py` (create), `packages/tl-web/tests/test_web_TW3.py` (create), `packages/tl-web/src/tl_web/{present,reads,routers}.py` (additive lines), `packages/tl-web/tests/{walk,test_web_reads_mirror,test_web_imports}.py` (union pins), `docs/reports/P2-I2/TW3.md`

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-web/tests/test_web_TW3.py packages/tl-web/tests/test_web_imports.py packages/tl-web/tests/test_web_confidentiality_walk.py packages/tl-web/tests/test_web_reads_mirror.py
```

## Report requirements
Standard, <= 60 lines, deviations first, pins listed. Commits `P2-I2-TW3: ...`, trailer as other tickets.

## Escalation triggers
- Stop if the text module needs a change, or the page needs a read the web client cannot mirror (name it).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
