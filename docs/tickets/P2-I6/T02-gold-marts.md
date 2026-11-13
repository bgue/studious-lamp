# P2-I6-T02 — Lake gold marts as SQL models

Status: draft (ready when S1 is merged: copy its provided tests, then dispatch)
Tier: haiku
Kind: ticket
Review: full
Labels: lake, sql
Depends on: S1 (merged on `p2/i6`)
Branch: `p2/i6-t02-gold-marts`
Worktree: harness-created under `/home/user/wt/i6/t02` (from `p2/i6` head)
Sec: lake guard

## Haiku-ability checklist (`01-tiers.md` §6, run after S1's interface was fixed in `S1-marts-sync.md`)
1 context files: 6 (yes). 2 interfaces in the tree after S1 merge: runner, stubs, provided tests (yes). 3 provided tests: three files (yes).
4 diff: 3 SQL files of about 40 lines, 3 test copies, report: under 400 lines, 7 files but 3 are byte copies (yes; the copies count as one unit).
5 no supervisor-tier row (SQL models over silver are not engines; the sync is S1) (yes). 6 no `schema/**`, no dependency, no public interface (yes).
7 verifiable from diff and gate summary (yes). Review is `full` because it is SQL over confidential-adjacent tables (lake guard).

## Goal
The three stub files in `packages/tl-lake/src/tl_lake/models/` become real DuckDB SELECT models so the provided tests pass: `mart_iwp_readiness_history`,
`mart_materials`, `mart_schedule_vs_readiness`. Nothing else changes; the runner (`tl_lake.gold`) already builds them in every sync.

## Brief references (pasted)
> §28.2 Gold: IWP readiness history; schedule trend. SQL models over silver, versioned in the repo, tested.
> Column contract (verbatim from S1; the stubs carry the exact types and order, keep them):
> - `mart_iwp_readiness_history`: `scope, iwp_id, seq, evaluated_at, today, ready, checks_total, checks_blocked, checks_pending, blocked_names, changed` from bronze `events` where `event_type = 'IWP.ReadinessEvaluated'`; payload text JSON with `iwp_id, evaluated_at, today, ready, checks[{name, state, ...}]`. Never select `detail`, `resolve_via` or `facts_hash`. `changed`: true for an IWP's first row, else `ready` or `blocked_names` differs from its previous row (by `seq`).
> - `mart_materials`: per scope, `YYYY-MM` period of `recorded_at`, kind: `movements, lots, qty, cost_codes`, plus the scope's `on_hand_now`, `lots_in_stock_now` from `cur_materials_stock`.
> - `mart_schedule_vs_readiness`: per row of `mart_schedule_history`, counts over the latest evaluation per IWP with `today <= CAST(data_date AS DATE)` in the same scope; `ready_pct` 1 dp; `as_of_seq` greatest counted seq.
> Rules: one SELECT, no trailing `;`, no `CREATE`, no view or index; DuckDB functions (`json_extract_string`, `json_extract`, `TRY_CAST`, `strftime`, `ROW_NUMBER() OVER`, `COUNT(*) FILTER (WHERE ...)`, `LAG`) work; qualify nothing (the runner wraps the text in `CREATE TABLE ... AS`); table names are the bare lake names `events`, `cur_materials_movement`, ... (the runner's connection has the lake as default catalog: look at `models/mart_*.sql` stubs and `gold.py` for how names resolve, and use `table_ref` style names if the stubs do).
> Hidden records: bronze already holds `Internal.Redacted` rows for hidden streams, and silver holds only visible rows; a model that reads only these cannot leak. Do not read anything else.

## Interfaces
`packages/tl-lake/src/tl_lake/gold.py` (`GOLD_MODELS`, `model_sql`, `build_gold_marts`) and the stubs: S1's report lists them verbatim at merge (supervisor pastes the stub text here when S1 is merged, abridged).

## Context (read these, nothing else)
- `packages/tl-lake/src/tl_lake/gold.py`
- `packages/tl-lake/src/tl_lake/models/mart_iwp_readiness_history.sql`, `mart_materials.sql`, `mart_schedule_vs_readiness.sql` (the stubs)
- `docs/tickets/P2-I6/provided/T02_test_iwp_readiness_history.py` (and the two siblings)
- `packages/tl-lake/src/tl_lake/xer_marts.py` (pattern for a mart in SQL)
- `docs/reports/P2-I6/S1.md`

## Allowed paths
- `packages/tl-lake/src/tl_lake/models/mart_iwp_readiness_history.sql`, `mart_materials.sql`, `mart_schedule_vs_readiness.sql`
- `packages/tl-lake/tests/test_gold_iwp_readiness_history.py`, `test_gold_materials.py`, `test_gold_schedule_vs_readiness.py` (create: byte-identical copies of the provided tests)
- `docs/reports/P2-I6/T02.md` (create)

## Acceptance
```
just check
just gate packages/tl-lake/tests
```
Expected: the three copied tests pass, the rest of the folder unchanged; `cmp` of each test and its provided copy identical; `git diff --stat` shows only the allowed paths.

## Tests to add
The three provided tests, copied. Do not edit them.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I6-T02: ...`; trailers `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- A provided test fails on a line the ticket does not explain; a column needs a source the silver or bronze does not hold; a statement the DuckLake catalog refuses (write the error under Blocked; do not edit the test or `gold.py`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
