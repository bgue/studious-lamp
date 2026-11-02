# P2-I1-T03c — API report route of the awp module

Status: ready (T10c, T03b merged; no other openapi.json ticket in the batch)
Tier: haiku
Review: full
Labels: api
Depends on: T04b, T03a (merged)
Branch: `p2/i1-t03c-reports`
Worktree: `/home/user/wt/i1/t03c` (from `p2/i1` head)

## Goal
`GET /projects/{project}/awp/reports/{name}` serves the three awp reports (T04b) to the web: as a table in JSON, or as CSV with `?format=csv`. Same viewer filter as every awp read.

## Brief references (pasted; spec §5, decisions D24, D32)
- Names: `cwp_status`, `wbs_vs_cost_code`, `cwa_sequence` (`reports.REPORT_NAMES`). An unknown name answers 404 `record_not_found` (`no report 'x'`), never 422: the confidentiality walk feeds `x` and `cwp_status`.
- JSON body `ReportView(name: str, columns: list[str], rows: list[list[str]])`: `columns` = the row model's field names, each cell `reports.format_value(value)` (the CSV and the JSON show the same text).
- CSV: `reports.to_csv(rows)` as `text/csv; charset=utf-8`, header line first; no rows gives an empty body.
- `wbs_vs_cost_code` needs the cost system's hours: build `dict[str, CostFigure]` from `tl_mod_cost.views.cost_codes(conn, scope, limit=20000)` exactly as `tl_cli/awp_report.py::_cost_figures` does (copy the 8 lines; tl-api already depends on tl-mod-cost).

## Interfaces (verbatim)
```python
# tl_mod_awp.reports: REPORT_NAMES; cwp_status(conn, scope)->list[StatusRow]; wbs_vs_cost_code(conn, scope, cost: Mapping[str, CostFigure])->list[CostRow]; cwa_sequence(conn, scope)->list[SequenceRow]
#  to_csv(rows)->str; format_value(v)->str; CostFigure(title: str, hours_budget: Decimal|None)
# tl_api/routes/awp.py: router, Ctx, Reader = Annotated[str, Depends(guard("document.read"))], `with ctx.backend(True) as uow:` then uow.conn(); scope f"project:{project}"
# new: class ReportView(BaseModel); @router.get("/projects/{project}/awp/reports/{name}", operation_id="awp_report", response_model=None, responses={200: {"content": {"text/csv": {}, "application/json": {}}}})
#  def awp_report(ctx, actor, project, name: str, format: Annotated[Literal["json","csv"], Query()] = "json") -> ReportView | Response
```

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/awp.py` (all), `packages/tl-cli/src/tl_cli/awp_report.py` lines 1-100
- `packages/tl-api/tests/test_confidentiality_walk.py` lines 142-162 (`candidates`)
- `dev/accept/P2-I1/T03a.py` (how the script builds the app and a signed-in `TestClient`; copy its setup)
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-api/src/tl_api/routes/awp.py`
- `packages/tl-api/tests/test_confidentiality_walk.py` (only the `"name"` entry of `candidates`: `["x", "cwp_status"]`)
- `docs/reference/openapi.json` (regenerate: `uv run python -m tl_api.openapi`; `just check` fails on drift; review with `git diff --minimal`)
- `dev/accept/P2-I1/T03c.py` (create), `docs/reports/P2-I1/T03c.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T03c.py
```
`T03c.py`: copy the seed, queue and run the rollup on the copy (`requeue_orphans(target)`, `build_worker(target).runner.run_until_idle()`, as `dev/accept/P2-I1/T04b.py` does), build the app on the copy, sign in a reader,
then: `PASS json <name> <n> rows` for each name (n equals `len(reports.<fn>(...))`); `PASS csv <name>` (body equals `reports.to_csv(rows)`, content type `text/csv`);
`PASS cells` (JSON cells equal the CSV cells row by row for `wbs_vs_cost_code`); `PASS unknown` (`x` answers 404 `record_not_found`); an anonymous call answers 401 (`PASS 401`). Ends `T03c ok`. No pytest, no `just gate`.

## Tests to add
none (T11 adds the route to `test_confidentiality_walk.py` runs and `test_awp_api.py`).

## Report requirements
`docs/reports/P2-I1/T03c.md` <= 60 lines; deviations first; the five PASS lines. Subject `P2-I1-T03c: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if the cost hours need a different read than `cost_codes` under the viewer; do not read cost tables directly.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
