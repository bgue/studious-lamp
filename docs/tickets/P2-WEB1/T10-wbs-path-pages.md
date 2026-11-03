# P2-WEB1-T10 — WBS tree and path of construction pages

Status: staged (waiting for the p2/i1 merge into p2/web1; see Activation)
Tier: haiku
Kind: ticket
Review: full
Labels: web
Depends on: S4, T02 (merged); P2-I1 C2 merged into p2/web1; P2-I1 T05b and T05c (terminal screens)
Branch: `p2/web1-t10-wbs-path`

## Goal
Two web logs, the WBS tree (nodes depth-first, indented by `depth`, each with its rollup) and the path of construction (steps of one version, a version list), twins of the terminal screens: <fill: slugs and text module>.

## Reads (known now: routes in `p2/i1` `packages/tl-api/src/tl_api/routes/awp.py`, views in `tl_mod_awp.views`)
- `wbs_tree(project, depth=None) -> list[WbsRow]` (`code title parent_code depth position retired total_hours by_cost_code`); `get_wbs_node(project, code) -> WbsRow` for the panel (`code` is a path parameter: URL-quote it).
- `get_path(project, version=None) -> PathView` (`key title version current_version steps[position cwa reason_code actor recorded_at]`); `list_path_versions(project) -> list[PathVersion]` (`version recorded_at actor step_count is_current`); `?version=` is validated as a positive int, anything else means the current one.

## Allowed paths
- `packages/tl-web/src/tl_web/pages/wbs.py` (create), `pages/path.py` (create)
- `dev/accept/P2-WEB1/T10.py`, `docs/reports/P2-WEB1/T10.md` (create)

## Activation (STAGED: do not dispatch before every line below is true; the supervisor then fills the `<fill>` marks and sets Status: ready)
1. `p2/i1` is merged into `p2/web1` (orchestrator, at M3 C2), so `tl_api.routes.awp` and `tl_mod_awp.views` are in the tree.
2. The matching terminal screens (`P2-I1` T05a/T05b/T05c) are merged and their text (columns, `row_cells`, `detail_lines`, `summary_line`, the panel) is in a Textual-free `tl_tui/*_text.py` module that `tl_web/present.py` can re-export. If a screen keeps that text inside a widget, the supervisor raises it (4) to the M3 supervisor instead of writing the ticket; a twin never moves terminal code.
3. Supervisor seam, one commit, <= 45 lines: `from tl_api.routes import awp as awp_routes` and the mirror methods + `MIRRORS` rows for the reads named below in `tl_web/reads.py` (pattern of `links_of`: `self._call(awp_routes.<fn>, project=project, ...)`), the text-module re-export in `present.py`, and the new mirror count in the S5 spec. The route functions take `project` as a path parameter (not a scope).
4. Run the `01-tiers.md` 6 checklist on the filled ticket; one "no" means split it.

## Common pins (all twins; model: `pages/documents.py`, `dev/accept/P2-WEB1/T02.py`)
Row types are imported under `TYPE_CHECKING` only and the base is quoted: `WebLog["CwpRow"]`. Cells, summary, panel text and the sort are the terminal's own functions via `tl_web.present`. Hidden or unknown = the one 404 page. No `|safe`. Actions: only if an `ACTION_UI` row exists for the log's commands (then `actions_for` as `rfis.py`), else `actions_for` returns `[]` (D20). Tests are deferred (S5); the acceptance script patches the reads with `mock.patch.object(WebReadClient, ...)` as T02 does, and checks: registration, seven regions in order, headers and cells equal the terminal functions, panel text, `?q=` filter, 404 byte-equality for unknown and hidden, no-cookie 303, plain mode versus root `?mode=technical`.
Acceptance: `uv sync --all-packages`, `NODE_OPTIONS=--max-old-space-size=6144 just check`, `uv run python dev/accept/P2-WEB1/<id>.py`; no pytest. Report <= 60 lines. Commit subject `P2-WEB1-<id>: ...`, no model names; end the message with the attribution trailer the harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer.
