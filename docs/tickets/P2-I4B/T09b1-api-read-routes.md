# P2-I4B-T09b1 — API read routes: scaffold register, record, due list, export (five-reader walk)

Status: ready (dispatch now; pre-hook form, see Goal)
Tier: haiku
Kind: ticket
Review: full
Labels: api, read, confidentiality
Depends on: T01 (merged: `tl_mod_scaffold.views`)
Branch: `p2/i4b-t09b1-api-routes`
Worktree: `/home/user/wt/i4b/t09b1` (from `p2/i4b` head)

## Goal
Four GET routes over `tl_mod_scaffold.views`, in the form the quality module used: a router module and one line in the `app.py` registration tuple. X4's `read_routers` hook is not on trunk (X4 C2 waits on X2 C2), so
this is the pre-hook path; when X4 merges, the `app.py` line becomes a `read_routers` entry in `module.py` (a later round, not here). Model: `routes/punch.py` (copy its shape: `_view_reader` = `guard("document.read")` then `require_word` for `scaffold.view` before any lookup; the request viewer `current_viewer()`, never the views' LOWEST default; one 404 text for missing and hidden) and `docs/reports/P2-PUNCH/T03.md`.

## Routes (operation ids exact)
- `GET /projects/{project}/scaffolds` (`list_scaffolds`; query `state`, `tag` as the views' constants via `Literal`, `overdue` bool, `limit` 1..`views.MAX_LIMIT`, default 200) returns `views.ScaffoldPage` (`rows`, `total`). `today` = `date.today().isoformat()` computed in the route, passed to the view.
- `GET /projects/{project}/scaffolds/{key}` (`get_scaffold`) returns `views.ScaffoldDetail`; missing and hidden are one 404 `record_not_found` with one constant text (the key is not echoed).
- `GET /projects/{project}/scaffold-due` (`list_scaffolds_due`; `limit`) returns `list[views.ScaffoldRow]`: standing scaffolds whose next inspection is due today or earlier (`views.due_list`).
- `GET /projects/{project}/scaffold-export` (`export_scaffolds`; query `format` = `csv` or `jsonl`, default `csv`; `state`, `tag`, `overdue` as the list) returns the text of `views.export_rows` over the visible rows (limit `views.MAX_LIMIT`) as `text/csv` or `application/x-ndjson`, `Content-Disposition: attachment; filename=scaffolds-<project>.<ext>` (owner rule 2026-11-14: a report is a simple export). Any other `format` is 422 (Literal). The export carries no `id` column (views).
Dataclass responses are the views' own; do not add models. No route writes; the `id` field of a row is carried as the views carry it, no hash.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/punch.py` (all), `tl_api/app.py` (the registration tuple around line 350 and the imports near line 75)
- `packages/tl-modules/scaffold/src/tl_mod_scaffold/views.py` (signatures and dataclasses), `docs/reports/P2-I4B/T01.md`
- `packages/tl-api/tests/test_api_punch.py` (lines 1-215: harness, tokens, five readers), `packages/tl-api/tests/test_confidentiality_walk.py` (route list near line 300)
- `packages/tl-modules/scaffold/tests/scaffold_world.py` (`World`, `hidden_record`), `packages/tl-modules/scaffold/tests/test_views.py` lines 90-110 (`hidden_scaffold`: the one projection write that makes a hidden scaffold)

## Allowed paths
- `packages/tl-api/src/tl_api/routes/scaffold.py` (create), `packages/tl-api/src/tl_api/app.py` (one import, one registration line next to `punch,`)
- `packages/tl-api/tests/test_api_scaffold.py` (create), `packages/tl-api/tests/test_confidentiality_walk.py` (add the four routes to the route-list assertion, union form)
- `docs/reference/openapi.json` (regenerate: `uv run python -m tl_api.openapi`; T09a regenerates it too, a conflict there is resolved by regenerating), route-count or auth-table pins (union form, listed)
- `docs/reports/P2-I4B/T09b1.md` (create)

## Acceptance
```
uv sync --all-packages
just check
just gate packages/tl-api/tests/test_api_scaffold.py packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_openapi_baseline.py
```
Add `packages/tl-api/tests/test_api_awp.py` to the gate only if a pin outside the named files breaks.

## Tests to add
`packages/tl-api/tests/test_api_scaffold.py` (pattern `test_api_punch.py`; ledger built by commands with the scaffold `World` loaded by path; the one hidden scaffold uses the projection write of `test_views.py::hidden_scaffold`, said in the module docstring):
- the four paths and operation ids are registered; no token is 401 on each;
- the five readers on list, detail, due list and export: no clearance (lowest) sees the visible rows and not the hidden scaffold; a cleared reader (document controller) sees it; a restricted-subject reader (a person who may read the restricted correspondence item that is the hidden scaffold's served record) sees it; a company admin sees what the class rule gives it (assert the same as the cleared reader only if the rule gives it; otherwise assert the rule's answer and say which in the report); an agent token holds read and sees the lowest reader's rows;
- a hidden scaffold's detail is byte-identical in status and body to a key that does not exist and to a key of another project; `total` never counts it, in the list and in the export (the export has no line for it);
- list filters (`state`, `tag`, `overdue`) reach the view; `limit=0` and `limit=501` are 422; `state=x` is 422; the due list drops a scaffold after `DismantleScaffold`;
- export: `csv` has the header and one line per visible row, the `jsonl` has one object per line, `format=xml` is 422, the headers name the file, a subject starting with `=` is written with the leading `'` in the CSV;
- the word check: the route refuses before any lookup when `require_word` refuses (patch `require_word` to raise and assert no view call), since every platform role derives `scaffold.view` (decision D28 of P2-PUNCH).

## Escalation triggers
- A route needs a viewer other than the request's; a route-count pin cannot be updated in union form; the export needs a column the views do not have; `scaffold.view` is not mapped for `require_word`.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, <= 5 decisive lines per command; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4B-T09b1: ...`; the commit body ends with the trailer lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not run the whole suite.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
