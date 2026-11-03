# P2-WEB1-T16 — path of construction page

Status: staged (waits for the path text module, P2-I1 T05c)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: T09b (merged), the awp reads seam, P2-I1 T05c: a Textual-free `tl_tui/path_text.py` (not in the tree at r7)
Branch: `p2/web1-t16-path`

## Goal
`GET /web/p/{project}/path` shows the steps of one path version and the list of versions, twin of the terminal path screen: <fill: columns, cells, panel, summary from `path_text`>. One module, `tl_web/pages/path.py` (stub exists).

## Reads (in the tree: `get_path(project, version=None)`, 404 when none; to add at activation: `list_path_versions(project) -> list[PathVersion]` = `version recorded_at actor step_count is_current`)
`?version=` is a positive integer, anything else means the current one (recipe 4). `PathView`: `key title version current_version steps[position cwa reason_code actor recorded_at]`.

## Activation (do not dispatch before every line is true)
1. `path_text.py` is merged into `p2/web1` and Textual-free; if the terminal keeps its text inside a widget, raise it (4) to the M3 supervisor.
2. Supervisor seam (<= 12 lines): `list_path_versions` mirror + MIRRORS row (32), `path_text` re-export in `present.py`, the mirror case.
3. Fill the `<fill>` marks, set Status: ready, run the 01-tiers 6 checklist. Pins, tests, screenshot and acceptance follow `TWINS.md`; allowed paths `pages/path.py`, `tests/test_web_path_log.py`, the `# --- T16 rows` marker in `walk.py`, `docs/reports/P2-WEB1/T16.md`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
