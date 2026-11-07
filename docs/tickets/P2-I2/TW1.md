# P2-I2-TW1 — Web twin: IWP log and record page (STAGED)

Status: staged (dispatch when T07b T04c2 merged; refine names from its report)
Tier: haiku
Kind: ticket
Review: full
Labels: web, read
Depends on: T07b T04c2
Branch: `p2/i2-tw1-web`
Worktree: harness-created under `/home/user/wt/i2/tw1`

## Goal
One server-rendered page, `packages/tl-web/src/tl_web/pages/iwps.py`, that renders the text module `packages/tl-tui/src/tl_tui/iwp_text.py` (Textual-free) for the same reads the terminal screen uses (list_iwps, get_iwp, list_iwp_scope). No business logic in the page (AGENTS.md); same text, same hiding.

## Brief
- Route `/web/p/{project}/iwps and /iwps/{number}` under `/web`, registered by adding the module name to the list in `packages/tl-web/src/tl_web/routers.py` (copy `pages/cwps.py`; route paths follow the sibling pages, check `pages/cwps.py` for the project prefix); read-only, so no POST and no origin-check work (L-P2-WEB1-2 applies only to writes).
- Reads through the client the web package already uses (`reads.py`); the viewer is the session's, never widened. A hidden or unknown record answers the same 404 page (140). No record text beyond what the text module prints.
- Navigation: one link where the CWP log link lives (`templates/`), found by grep `cwp`.
- Test: copy the shape of `packages/tl-web/tests/test_web_cwp_log.py`: page renders rows, empty state, hidden-vs-missing byte-identical, five readers on the page (AGENTS.md walking-test rule): `packages/tl-web/tests/test_web_TW1.py` is the ticket's own deliverable here (Haiku writes it from the shape).

## Context (read these, nothing else)
- `docs/reports/P2-I2/{T07b,T04c2}.md`, `packages/tl-tui/src/tl_tui/iwp_text.py`, `packages/tl-web/src/tl_web/pages/cwps.py`, `packages/tl-web/src/tl_web/routers.py`, `packages/tl-web/tests/test_web_cwp_log.py`, `packages/tl-web/README.md`

## Allowed paths
- `packages/tl-web/src/tl_web/pages/iwps.py` (create), its module name in the `routers.py` list, the nav template line, `packages/tl-web/tests/test_web_TW1.py` (create), consequential pins (union form, listed), `docs/reports/P2-I2/TW1.md`

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-web/tests/test_web_TW1.py packages/tl-web/tests/test_web_imports.py packages/tl-web/tests/test_web_confidentiality_walk.py
```

## Report requirements
Standard, <= 60 lines, deviations first, pins listed. Commits `P2-I2-TW1: ...`, trailer as other tickets.

## Escalation triggers
- Stop if the text module needs a change, or the page needs a read the client lacks (name it).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
