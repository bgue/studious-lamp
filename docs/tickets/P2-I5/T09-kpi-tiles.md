# P2-I5-T09 — KPI tiles: PPC and percent constraint-free

Status: ready (S4a merged; stub `kpis.py` in the tree)
Tier: haiku
Kind: ticket
Review: lite
Labels: read, cli
Depends on: S4a
Branch: `p2/i5-t09-kpis`
Worktree: harness-created under `/home/user/wt/i5/t09` (from `p2/i5` head)

## Goal
Two figures a planner reads each week, computed from the ledger on both adapters: PPC and the share of live IWPs with no open blocking constraint. They are module functions (the API, the CLI, MCP and the TUI read them) and two names of `tl awp report`.

## Brief references (pasted)
- PPC tile: the last `weeks` (default 4, `kpis.PPC_WEEKS`) Closed weekly plans the viewer may read (`week_views.list_weeks`, state `Closed`; `list_weeks` is latest week first), their commitments the viewer may read (`week_detail`); pooled by count: `numerator` = commitments with outcome `done`, `denominator` = all, value = `progress.engine.ppc(done, committed)[0]` (one decimal, half-up; `None` with nothing). Pooled, so 2 of 3 then 2 of 2 is 80.0, not the mean 83.4. `detail` is plain words, `"4 of 5 IWPs done, last 2 closed weeks"`; with no value `"no closed week yet"`.
- Constraint-free tile: live IWPs are those in `actions.IWP_LIVE_STATES` the viewer may read (`iwp_views.iwp_list(conn, scope, limit=500)` under `confidentiality.use_viewer(viewer)`, as `look_ahead_view` does); an IWP is free when `look_ahead_view._open_blocking(conn, scope, viewer, ids)` is 0 for it (Open or Assigned, blocking, readable by the viewer). `numerator` = free, `denominator` = live, value = `round_half_up(Fraction(free * 100, live))`, `None` for no live IWP; `detail` `"3 of 4 IWPs"` / `"no live IWP"`.
- `kpi_rows(conn, scope, viewer)` returns `[ppc_tile, constraint_free_tile]` in `KPI_NAMES` order.
- CLI: `tl awp report kpi_ppc|kpi_constraint_free` print one row each through the existing report path (`ALL_NAMES`, `reports.format_value`; columns `name value numerator denominator detail`; `--csv` as the other reports); the viewer is `session_viewer(db)`.

## Interfaces (verbatim from repo)
The stub `packages/tl-modules/awp/src/tl_mod_awp/kpis.py` (signatures, `KpiTile`, `KPI_NAMES`, `PPC_WEEKS`). Replace the three `NotImplementedError` bodies and drop the STUB note.
```python
# tl_mod_awp/week_views.py
def list_weeks(conn, scope, viewer, *, limit=60) -> list[WeekRow]     # .state "Closed"
def week_detail(conn, plan_id, viewer) -> WeekDetail                    # .commitments[*].outcome
# tl_mod_awp/progress/engine.py
def ppc(done: int, committed: int) -> tuple[Decimal | None, list[str]]
def round_half_up(value) -> Decimal
```

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/{kpis.py (the stub), week_views.py, look_ahead_view.py (115-130, 131-170), actions.py (60-72)}`
- `packages/tl-cli/src/tl_cli/awp_report.py` (whole), `packages/tl-modules/awp/src/tl_mod_awp/iwp_reports.py (35-70)`
- the provided test `docs/tickets/P2-I5/provided/T09_test_kpis.py`

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/kpis.py` (replace the stub)
- `packages/tl-modules/awp/tests/test_kpis.py` (create: byte-identical copy of the provided test)
- `packages/tl-cli/src/tl_cli/awp_report.py` (the two names and their branch), `packages/tl-cli/tests/test_awp_kpi_report.py` (create: below)
- `docs/reports/P2-I5/T09.md` (create); consequential pins: `docs/reference/awp.md` (one report line), any report-name list a test pins (union)

## Acceptance
```
just check
just gate packages/tl-modules/awp/tests/test_kpis.py packages/tl-cli/tests/test_awp_kpi_report.py packages/tl-cli/tests/test_cli_awp.py packages/tl-cli/tests/test_reports.py
just gate-pg packages/tl-modules/awp/tests/test_kpis.py
```
Expected: 7 passed in `test_kpis.py`; both adapters green; `cmp` identical.

## Tests to add
`test_awp_kpi_report.py` (CLI, pattern of `test_awp_progress.py`): `report kpi_ppc` and `kpi_constraint_free` on the seed ledger print one row each with the named columns; `--csv` header line; an unknown name is `error:` exit 1; no `Traceback`.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T09: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
