# P2-I2-T09a — IWP and constraint reports, `tl awp report`

Status: ready (T04a, T04a2, S4 merged)
Tier: haiku
Kind: ticket
Review: lite
Labels: core, cli, read
Depends on: T04a, T04a2, S4 (merged)
Branch: `p2/i2-t09a-iwp-reports`
Worktree: harness-created under `/home/user/wt/i2/t09a` (from `p2/i2` head)

## Goal
Six reports exist as functions over the existing views and print from the existing `tl awp report NAME [--csv]`, as P2-I1 T04b did for the three CWP reports (`docs/tickets/P2-I1/T04b-reports.md`, `reports.py`, `awp_report.py`). No table is read directly, so the viewer filter applies. No new registration: `awp_report.py` already is mounted.

## Reports (rows are `BaseModel`s; `to_csv` and `format_value` of `reports.py` are reused, import them)
- `iwp_status`: `(state, discipline, count, estimated_hours)` from `iwp_views.iwp_list(limit=500)`; states in workflow order Draft, In development, Constraint check, Ready, Issued, In progress, Field complete, Closed, On hold, Split, Cancelled, then others by name; discipline `-` when none; total row last (state `total`, discipline `-`).
- `iwp_readiness`: `(number, ready, passing, total, blocked)`; per visible IWP in number order, from `readiness.views.readiness(conn, scope, number)`: `ready` `yes|no|not evaluated`, `passing` = checks with state in `readiness.engine.PASSING` (import it), `total` = checks, `blocked` = names of `blocked` checks comma-joined or `-`. An IWP never evaluated: `not evaluated`, `-`, `-`, `-`. NEVER read or print `resolve_via`, counts or ids (hidden refs, D32); only check names and states.
- `constraint_log`: `(key, state, category, severity, owner, phase, due, age_days, aging)` from `tl_core.constraints.list_constraints(conn, scope, limit=500)` (viewer none = lowest clearance), by key; owner `-` when none, due the date part or `-`.
- `constraints_by_category`, `constraints_by_owner`, `constraints_by_age`: `(label, count, blocking, aging)` from `review_groups(views, by)` with `by` category, owner, age (`BY_WORDS`); the `keys` are not printed.

## Interfaces (verbatim)
```python
# tl_mod_awp/iwp_reports.py (create):
IWP_REPORT_NAMES: Final = ("iwp_status", "iwp_readiness", "constraint_log", "constraints_by_category", "constraints_by_owner", "constraints_by_age")
def iwp_status(conn, scope) -> list[IwpStatusRow]; def iwp_readiness(conn, scope) -> list[IwpReadinessRow]
def constraint_log(conn, scope) -> list[ConstraintLogRow]; def constraint_groups_report(conn, scope, by: str) -> list[GroupRow]
# tl_mod_awp.reports: to_csv, format_value; tl_cli.awp_report.report(...) dispatches on NAME (extend the name check and the if-chain)
# tl_core.constraints: list_constraints, review_groups, BY_WORDS (queries.py, review.py); iwp_views.iwp_list; readiness.views.readiness
```

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/reports.py` (all), `packages/tl-cli/src/tl_cli/awp_report.py` (all), `packages/tl-modules/awp/src/tl_mod_awp/iwp_views.py` lines 41-66 and 156-180
- `packages/tl-core/src/tl_core/constraints/queries.py` lines 53-82, 208-236; `review.py` (all); `dev/accept/P2-I2/s4_world.py` (seed and evaluate helpers; reuse)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/iwp_reports.py` (create)
- `packages/tl-cli/src/tl_cli/awp_report.py` (the name check, the if-chain and the help text only)
- `dev/accept/P2-I2/T09a.py` (create; helper `t09a_checks.py` if over 70 lines), `docs/reports/P2-I2/T09a.md` (create)
Not here: `reports.py`, `awp.py`, `main.py`, pyproject, any change to a view or to `tl_core`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T09a.py
just gate packages/tl-cli/tests/test_cli_awp.py
```
`T09a.py` (seed a SQLite ledger with the S4 world helpers: 3 IWPs of two states, one evaluated with two blocked checks, one never evaluated; 4 constraints, one hidden by its subject's class; `PASS <name>` per line; ends `T09a ok`): `iwp_status` counts sum to the IWP count and the hours to the sum of `iwp_list` hours, total row last, order as above; `iwp_readiness` forms for evaluated and not evaluated, blocked names listed, `n_a` counted as passing; no 64-hex string, no record id and no `resolve_via` text in any report output; `constraint_log` and the three group reports exclude the hidden subject's constraint and agree with each other on the total; `to_csv` of each starts with its header and has rows+1 lines; through `CliRunner` on a local `typer.Typer()` with `awp_report.register(app)`, `report constraints_by_owner --csv --project P123 --db <copy>` exits 0 and an unknown name exits 1 listing all nine names; no `Traceback`.

## Tests to add
None (S5).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Subject `P2-I2-T09a: ...`; trailer is the attribution lines your harness requires, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- Stop and write *Blocked* if a report needs a table read or a field no view carries (say which), or a CWP-report snapshot outside Allowed paths breaks.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
