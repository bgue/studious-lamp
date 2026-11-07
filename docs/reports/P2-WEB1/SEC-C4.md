# P2-WEB1 C4 security review: the twins (M3 and M4 web pages)

Range `b817341..da07d37`, `packages/tl-web/src`. Read-only review, fresh context, 2026-11-03. Result: **no findings** (`9 none`).

## Q7 item 1: the items panel shows other projects' stock
This is intended company-wide data, not a leak. `roles-mvp.md` §7 and `wave0.md` §2: module roles do not filter reads
in the MVP, and reads stay governed by ADR-0016 alone. The project-membership read filter is deferred to P3-I8 (owner Q3).
`m4-materials.md` §7 specifies the panel's Projects table. The JSON API (`/companies/materials/item-projects`,
`/projects/P456/materials/stock`) and the terminal already answer the same reader the same rows.
**Follow-up for P3-I8:** `item_projects` and `items.projects` are company-scope views and need the membership filter
in the view. The page needs no change.

## Q7 item 2: five-reader walk
The readers are admin, materials superuser on P123, user on P123, P123 without a materials grant, and P456 only.
For all ten materials mirrors and the eight awp mirrors, every reader gets exactly the JSON rows. Each mirror runs the
route's `document.read` guard before the route function. Neither module declares a confidential source. A missing or
hidden number gets the single `not_found.html` 404. Technical mode is for admins only (`log.py` `for_request`).

## Q7 item 3: the routes
- **ADR-0016:** the 11 new routes are all GET. Each checks the project, then reads through the guarded `_call` before any lookup.
- **Panels:** they never look up a number taken from the URL. They pick from the rows already listed.
- **Panel URLs:** `quote(number, safe="/")` builds them, and Jinja autoescape is on.
- **CSRF:** no write route was added, and every new log's `actions_for` returns `[]`.

## Seen, no security effect
Movements `?lot=` and take-off lines `?wp=` skip the JSON route's length caps (200 and 64). The web calls the route
function directly, so FastAPI's query checks don't run. Both values are bound equality parameters, so an over-long
value matches nothing.
