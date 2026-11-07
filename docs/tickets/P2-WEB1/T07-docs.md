# P2-WEB1-T07 — Docs: tl-web README, web-client runbook, AGENTS row

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: all page tickets merged (they are)
Branch: `p2/web1-t07-docs`   (from p2/web1)

## Goal
The web client is documented where the next person looks: a package README, a runbook, one AGENTS.md row.

## Context (read these, nothing else)
- `docs/build-spec/specs/web-client-i1.md` (sections 1-3 for the shape; abridged use)
- `packages/tl-web/src/tl_web/pages/__init__.py`, `packages/tl-web/src/tl_web/routers.py` (PAGE_MODULES)
- `docs/tickets/P2-WEB1/TWINS.md` and `M4-TWINS.md` ("Learned" parts)
- `docs/runbooks/tui-dev.md` (style model for a runbook), `docs/runbooks/README.md` (index)
- `packages/tl-tui/README.md` (style model for a package README)
may explore: (none)

## Allowed paths
- `packages/tl-web/README.md` (create)
- `docs/runbooks/web-client.md` (create)
- `docs/runbooks/README.md` (one index line)
- `AGENTS.md` (one row in "Where things go")
- `docs/reports/P2-WEB1/T07.md` (create)

## Content
README (<= 90 lines): what tl-web is (server-rendered pages over the same read contracts as the JSON API and
the terminal; no business logic, only `present.py` imports tl_tui); layout (log.py WebLog standard, pages/,
templates, static incl. vendor/VENDORED.toml, reads.py mirrors, actions.py and POST /do); how to add a page
(the recipe: stub in PAGE_MODULES, WebLog subclass, WALK marker, mirror row); rules: hidden = missing (ADR-0016),
CSRF on every POST, `TL_WEB` on/off, no `/web` route in openapi.json.
The 11 twin pages, one line each, path `/web/p/{project}/<slug>`: cwps, cwas, wbs, packages, path (M3);
stock, movements, receipts, mto, items, locations (M4). Plus the earlier pages: rfis, correspondence,
documents, record (tabs Details Properties History Links Trace Thread Files), file viewer.
Decisions to state plainly (one line each): D41 (pages without a record page have no Open link; follow-up
for Phase 2); the items panel shows other projects' quantities for the same item by design (roles-mvp §7,
P3-I8 follow-up, see `docs/reports/P2-WEB1/SEC-C4.md`); the locations page indents subject by depth in the
cell text, HTML collapses it (flat look; follow-up).
Runbook (<= 70 lines): start (`just serve`, `/web/sign-in`), `TL_WEB` values, sessions and cookie, the demo
(`just demo P2-WEB1`), screenshots (`.accept/shots`), where logs/errors show, troubleshooting (404 = hidden or
absent; 403 csrf_refused; 503 on file renders when 2 are busy).
AGENTS row: web client | `packages/tl-web/`; runbook `docs/runbooks/web-client.md`; demo `dev/demos/P2-WEB1.sh`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
```
Expected exit 0. Every path you name in the docs exists (`ls` them). No model names in any file.

## Report requirements
Standard haiku report, <= 60 lines.

## Escalation triggers
- A page or fact you would have to guess: leave it out and list it in the report.
