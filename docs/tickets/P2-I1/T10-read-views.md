# P2-I1-T10 — Read views of the awp module (`views.py`)

Status: ready
Tier: haiku
Review: full
Labels: core
Depends on: S4 (merged), S5 (merged)
Branch: `p2/i1-t10-views`
Worktree: `/home/user/wt/i1-t10` (from `p2/i1` head)

## Goal
The eight stubs in `tl_mod_awp/views.py` read the typed tables and return pydantic models. Every read goes through the
viewer filter (ADR-0016): a record the viewer may not read is absent, never counted, never named. Nothing writes and
nothing checks an access word. T03a (routes), T04 (CLI) and T05 (screens) call these.

## Brief references (pasted; spec `docs/build-spec/specs/m3-wbs-cwp.md` §5)
`cwp_list(conn, scope, *, state=, discipline=, cwa=)`; `cwp_detail(conn, scope, number)` (fields, allocations, packages,
activities); `cwa_list`; `wbs_tree(conn, scope, *, depth=None)` (depth-first, with rollup totals); `wbs_detail(code)`;
`path(conn, scope, version=None)`; `path_versions`; `package_list(conn, scope, kind=)`.
**Decision D15:** the link count, file count and timeline of a CWP are NOT here; the entry points have a unit of work and
add them (`link_queries.links_of`, `queries.record_history`) in T03a. A function returns `None` (detail views) or `[]`
for a missing, hidden, voided or other-project record; the words never differ.

## Interfaces (verbatim)
```python
# views.py today: cwp_list(conn, scope, *, state=None, discipline=None, cwa=None) -> list[object]; cwp_detail(conn, scope, number)
# -> object|None; cwa_list(conn, scope); wbs_tree(conn, scope, *, depth=None); wbs_detail(conn, scope, code); path(conn, scope,
# version=None); path_versions(conn, scope); package_list(conn, scope, *, kind=None). Replace `object` by your models.
# tl_core.confidentiality.not_hidden(id_expr) -> (clause, params): "r.id NOT IN (...)"; merge params into the statement.
# tl_mod_schedule.resolver.links_to_activities(conn, record_id, *, scope, limit=...) -> list[ActivityLink]
#   ActivityLink(link_id, status, pin, reason, ref_key, resolution)
# names.py: tables CWP_TABLE WBS_NODE_TABLE WBS_ALLOCATION_TABLE PATH_TABLE PATH_STEP_TABLE CWA_TABLE CWP_ALLOCATION_TABLE
#   PACKAGE_TABLE{EWP,PWP}; types CWP WBS_NODE CWA PATH EWP PWP; common.resolve_code(conn, scope, type, code) -> id|None
```
Columns (record tables have `id` as key; envelope `cur_core_record r`: `id, key, title, scope, type, status, voided`):
- `cur_awp_cwp`: scope, discipline, cwa_id, planned_start, planned_finish, budget_hours, quantities_json, contractor_text;
  CWP number = `r.key`; state = `r.status`, NULL reads as `Planned` (`common.package_state`). Void CWPs are left out.
- `cur_awp_cwp_allocation`: cwp_id, wbs_node_id, percent. `cur_awp_wbs_node`: code, parent_id, depth, position, retired.
- `cur_awp_wbs_allocation`: node_id, cost_code_id, percent. `cur_awp_cwa`: code, location_text, retired.
- `cur_awp_path`: current_version; `cur_awp_path_step`: path_id, version, position, cwa_id, reason_code, actor, recorded_at.
- `cur_awp_ewp_ref` / `cur_awp_pwp_ref`: package_no, status_text, forecast_date, actual_date, constraint_source, source_system.
- `cur_awp_rollup`: subject_id, line (`total`, `cost_code`, `unallocated`), cost_code_id, measure `budget_hours`, value, as_of_seq.
Packages of a CWP: active `cur_links` rows (`from_id` = CWP, `relation = 'requires'`, `status <> 'retracted'`) whose other end is
an EWPRef or PWPRef the viewer may read. Decimals are `Decimal(str(value))`; dates `YYYY-MM-DD` strings.

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/views.py`, `names.py`, `common.py` (`resolve_code`, `package_state` only)
- `packages/tl-modules/cost/src/tl_mod_cost/views.py` (shape: pydantic models, only reads)
- `packages/tl-core/src/tl_core/confidentiality.py` (`not_hidden`, `hidden_among`)
may explore: `.accept/p2-i1.db` (read-only, to see columns and rows)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/views.py`
- `dev/accept/P2-I1/T10.py` (create), `docs/reports/P2-I1/T10.md` (create)

## Steps
1. `mkdir -p .accept && uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db` (seed ledger; do not commit `.accept`).
2. One model per view (`CwpRow`, `CwpDetail`, `CwaRow`, `WbsRow` with `total_hours: Decimal | None` and
   `by_cost_code`, `PathView` with its steps in position order, `PathVersion`, `PackageRow`). Lists order: CWP by number, CWA
   by code, tree depth-first by `position` under each parent, packages by `package_no`, versions newest first.
3. `wbs_tree` reads rollup rows in one query (not one per node); `depth=n` keeps nodes with `depth < n`. A node without rollup
   rows has `total_hours=None`. `path(version=None)` reads `current_version`; an unknown version gives `None`.
4. `cwp_detail.activities` = `links_to_activities(conn, id, scope=scope)`; a stale link stays listed with its status.
5. Acceptance `dev/accept/P2-I1/T10.py --db PATH` prints `PASS <view> <n> rows` per view on the seed (6 CWPs, 4 CWAs,
   3-level WBS, path v1), then one `PASS hidden`: set a restricted class on one CWP as a lowest-clearance viewer would see it
   (copy the way `dev/accept/P2-I1/S4.py` hides a record) and the CWP leaves `cwp_list` and `cwp_detail` answers `None`.
   Ends `T10 ok`. No pytest.

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/T10.py --db .accept/p2-i1.db
```
Expected: `just check` clean; every PASS line, `T10 ok`. No `just gate` (no existing test directory is touched).

## Tests to add
none (T11 writes `test_views.py`).

## Report requirements
`docs/reports/P2-I1/T10.md` <= 60 lines, <= 5 decisive output lines per command. Subject `P2-I1-T10: ...`; no model names.

## Escalation triggers
- Stop and write *Blocked* if a view needs a column the tables above do not have, a file outside Allowed paths, or a
  `tl_core` change; or if the hidden CWP still shows in any view.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
