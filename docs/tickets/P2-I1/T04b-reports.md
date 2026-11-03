# P2-I1-T04b — awp reports and `tl awp report`

Status: ready
Tier: haiku
Review: full
Labels: core, cli
Depends on: T10 (merged), S5 (merged); T10b is not needed (reports read the same views)
Branch: `p2/i1-t04b-reports`
Worktree: `/home/user/wt/i1-t04b` (from `p2/i1` head)

## Goal
Three reports exist as functions over the views, print from `tl awp report <name>` and render as CSV. They never read a table
directly, so the viewer filter applies. The cost-system hours are passed in by the caller (the module does not depend on cost).

## Brief references (pasted; spec §5)
- `cwp_status`: by state and discipline: count, budget h. Rows `(state, discipline, count, budget_hours)`, states in workflow order
  (Planned, In development, Released for IWP development, then any other state by name), discipline `-` when none, a total row last.
- `wbs_vs_cost_code`: cost code, name, awp budget h, cost-system budget h, difference; plus the Unallocated row. Cost-system hours
  come from the latest cost snapshot `hours_budget` figure when it states one, else `—` (no difference then).
- `cwa_sequence`: the current path with CWP counts and budget h per CWA: `(position, cwa code, cwa title, cwps, budget_hours)`.
Awp budget per cost code = the sum of the `by_cost_code` of the root nodes (`parent_code is None`); Unallocated = sum of the roots'
`total_hours` minus the sum of all their `by_cost_code`. A CWP counts under its CWA by `CwpRow.cwa` (code); void CWPs are not in `cwp_list`.

## Interfaces (verbatim)
```python
# tl_mod_awp/reports.py (create):
class CostFigure(BaseModel): title: str; hours_budget: Decimal | None
REPORT_NAMES: Final = ("cwp_status", "wbs_vs_cost_code", "cwa_sequence")
def cwp_status(conn, scope) -> list[StatusRow]; def wbs_vs_cost_code(conn, scope, cost: Mapping[str, CostFigure]) -> list[CostRow]
def cwa_sequence(conn, scope) -> list[SequenceRow]; def to_csv(rows: Sequence[BaseModel]) -> str   # header = field names, "\n" line ends, Decimal as 1-dp text
# views: cwp_list, cwa_list, wbs_tree, path (see views.py class bodies)
# tl_mod_cost.views.cost_codes(conn, scope, *, parent=None, search=None, limit=1000) -> list[CostCodeView]   # .code .title .figures["hours_budget"] (float|None)
# tl_cli: Project, service_errors, cell, fail in derive_support; `register(app)` pattern in cost_report.py
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/cost_report.py`; `packages/tl-modules/awp/src/tl_mod_awp/views.py` (class bodies and signatures)
- `packages/tl-modules/cost/src/tl_mod_cost/views.py` lines 19-60 (`CostCodeView`)
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/reports.py` (create)
- `packages/tl-cli/src/tl_cli/awp_report.py` (create: `register(app)` adds one command `report` with a NAME argument checked against
  `REPORT_NAMES` and a `--csv` flag; it loads `CostFigure`s through `tl_mod_cost.views.cost_codes(..., limit=20000)`)
- `dev/accept/P2-I1/T04b.py` (create), `docs/reports/P2-I1/T04b.md` (create)
Not allowed: `awp.py`, `main.py` (the supervisor mounts `awp_report.register(app)` after merge), any pyproject (no new dependency).

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db     # if the file is missing
uv run python dev/accept/P2-I1/T04b.py --db .accept/p2-i1.db
```
`T04b.py`: copy the seed to a temp file, queue and run the rollup on the copy (`requeue_orphans(target)`; `build_worker(target).runner.run_until_idle()`,
as `dev/accept/P2-I1/S5.py` does), then: `cwp_status` counts sum to 6 and budget sums to the sum of `cwp_list` budgets (`PASS cwp_status`);
`wbs_vs_cost_code` awp budget per cost code equals the sum of the leaves' `by_cost_code` (compute both ways) and Unallocated >= 0 (`PASS wbs_vs_cost_code`);
`cwa_sequence` has 4 rows in path order (`PASS cwa_sequence`); `to_csv` of each starts with its header and has rows+1 lines (`PASS csv`); through
`CliRunner` on a local `typer.Typer()` with `awp_report.register(app)`, `report cwp_status --csv --project P123 --db <copy>` exits 0 and an unknown
name exits 1 (`PASS cli`). Ends `T04b ok`. No `just gate` (no existing test directory touched).

## Tests to add
none (T11 writes `packages/tl-cli/tests/test_reports.py` and `test_cli_awp.py` cases).

## Report requirements
`docs/reports/P2-I1/T04b.md` <= 60 lines, <= 5 decisive output lines per command; deviations first. Subject `P2-I1-T04b: ...`; no model names;
commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if parents' `by_cost_code` do not sum to the leaves' (say what the seed shows), or a report needs a table read.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
