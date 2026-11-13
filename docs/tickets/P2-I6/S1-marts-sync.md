# P2-I6-S1 — Marts sync pass: materials silver, gold model runner, three model stubs (B2)

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: lake, core
Depends on: none (trunk @4624fcf; `cur_materials_*` and `IWP.ReadinessEvaluated` exist)
Branch: `p2/i6-s1-marts-sync`
Worktree: `/home/user/wt/i6-s1`
Sec: lake guard (SR-X1)

## Goal
After this piece `tl lake sync` (1) copies two more ledger projections into silver, `cur_materials_movement` and `cur_materials_stock`, with
the same visibility rule as every silver table; (2) runs a gold pass, `tl_lake.gold.build_gold_marts(con)`, that builds each SQL model file
under `packages/tl-lake/src/tl_lake/models/` as a table, inside the sync transaction of both the event pass and the schedule pass. The three
models are stubs with their final columns and no rows (`WHERE false`), each with a provided test and a mutation-checked reference; the Haiku
ticket T02 writes the SQL. A lake built by incremental syncs equals a full rebuild, property-tested like `test_rebuild_equals_incremental.py`.

## Brief references (pasted)
> §28.2 Gold (marts): IWP readiness history; schedule trend; progress by cost code and period. "SQL models over silver (versioned in repo, tested)."
> `docs/build-spec/specs/m4-materials.md` §1: movements are events `StockLot.Moved` (`kind` receive|issue|transfer|return|adjust|scrap|reserve|unreserve);
> projections `cur_materials_movement` (one row per movement event, key `seq`) and `cur_materials_stock` (`scope, lot_id, location_id, on_hand, reserved, available`; rows at zero deleted; no `last_seq`).
> `packages/tl-lake/AGENTS.md`: a sync is one DuckLake transaction; a mart reads silver (and bronze) only, replaces its table whole; a silver table naming record ids needs them in `_VISIBLE_ENDS`; rebuild equals incremental; bulk loads via NDJSON; no dialect SQL in `sync.py`.
> ADR-0016: hidden looks like missing; the lake stores nothing about a hidden record, not even its id. Bronze `events` of a hidden stream are rows of type `Internal.Redacted` with an empty payload; reference ids the lowest viewer may not read are removed from payloads (`PAYLOAD_REFS`).

## Interface (fixed here; T02 depends on it)
`schema.py`:
```python
@dataclass(frozen=True)
class SilverTable:
    name: str; source: str; key: str; driver: str | None = None
    change: Literal["last_seq", "seq", "whole"] = "last_seq"
    # last_seq: today's rule. seq: append-only, copy source rows with seq > watermark (never replaced).
    # whole: no change column; delete all rows and reload when the sync is not empty.
SilverTable("cur_materials_movement", "cur_materials_movement", "seq", change="seq")
SilverTable("cur_materials_stock", "cur_materials_stock", "lot_id", change="whole")
```
`sync.py` `_VISIBLE_ENDS` gains `cur_materials_movement: (lot_id, iwp_id, requisition_id)` and `cur_materials_stock: (lot_id,)`. A NULL end is
kept (the filter applies to non-null ids only). `_newest_seq` and `_changed_keys` must not assume a `last_seq` column for these two.

New `tl_lake/gold.py`:
```python
@dataclass(frozen=True)
class GoldModel:
    name: str                  # table name, starts "mart_"; the SQL file is models/<name>.sql
    needs: tuple[str, ...]     # lake tables that must exist, else the mart is dropped and the model skipped

GOLD_MODELS: tuple[GoldModel, ...]   # build order
def model_sql(name: str) -> str      # text of models/<name>.sql (importlib.resources), one SELECT, no trailing ';'
def build_gold_marts(con: Duck) -> None
    # per model in order: DROP TABLE IF EXISTS; if all needs exist: CREATE TABLE <ref> AS <model_sql>
    # (the table exists, possibly empty, whenever its needs exist). Names go through table_ref. No views, no indexes.
```
`GOLD_MODELS` order and needs: `mart_iwp_readiness_history` needs `events`; `mart_materials` needs `cur_materials_movement`, `cur_materials_stock`;
`mart_schedule_vs_readiness` needs `mart_schedule_history`, `mart_iwp_readiness_history`.
Call sites: `sync._sync` after `build_document_marts(con)` and before the `_tl_sync` insert; `xer._sync` right after `build_marts(con)`. Both inside the open transaction.

Model stubs `models/<name>.sql` (columns, in order, are the contract; stubs are `SELECT CAST(NULL AS <type>) AS <col>, ... WHERE false`):
- `mart_iwp_readiness_history`: one row per `IWP.ReadinessEvaluated` event in bronze: `scope VARCHAR, iwp_id VARCHAR, seq BIGINT, evaluated_at VARCHAR, today DATE, ready BOOLEAN, checks_total BIGINT, checks_blocked BIGINT, checks_pending BIGINT, blocked_names VARCHAR` (names of checks with state `blocked`, sorted, comma-joined, empty string if none), `changed BOOLEAN` (true for an IWP's first row, else ready or blocked_names differ from its previous row by seq). Never `detail`, `resolve_via`, `facts_hash` or raw payload (D3).
- `mart_materials`: `scope VARCHAR, period VARCHAR` (`YYYY-MM` of `recorded_at`), `kind VARCHAR, movements BIGINT, lots BIGINT` (distinct), `qty DOUBLE, cost_codes BIGINT` (distinct non-null), `on_hand_now DOUBLE, lots_in_stock_now BIGINT` (the scope's totals from `cur_materials_stock`, same on every row of the scope; 0 when the scope has no stock). One row per scope, period, kind.
- `mart_schedule_vs_readiness`: one row per published snapshot of `mart_schedule_history`: `scope, schedule_code, snapshot_number, data_date, latest_early_finish, finish_slip_days` (copied), `iwps_evaluated BIGINT, iwps_ready BIGINT, iwps_not_ready BIGINT, ready_pct DOUBLE` (1 dp, NULL when none evaluated), `as_of_seq BIGINT` (greatest `seq` among the evaluations counted, NULL when none). Counted: the latest evaluation (greatest `seq`) per IWP with `today <= CAST(data_date AS DATE)` and the same scope.

Provided tests (you write them, they are the T02 spec): `docs/tickets/P2-I6/provided/T02_test_iwp_readiness_history.py`, `T02_test_materials.py`,
`T02_test_schedule_vs_readiness.py`. Each builds the silver/bronze rows it needs in a temp lake by direct `INSERT` (as `test_schedule_history_mart.py`),
calls `build_gold_marts`, and pins `SELECT *` for 4-6 cases including the empty case, the `changed` flag, a period boundary, a scope split and
the `today <= data_date` edge. Each is pyright-clean as copied (no unnarrowed Optional) and imports only `tl_lake`. Write your reference SQL first, run the tests green, then replace
the SQL files by the stubs and keep the reference in the report (60 lines max, or `docs/tickets/P2-I6/refs/<name>.sql`, create). Do not leave a failing test
in the tree for the stub state: mark the three provided tests as living under `provided/` only (they run from `packages/tl-lake/tests/` when T02 copies them).

## Context (<= 10 files)
`packages/tl-lake/{AGENTS.md,README.md}`; `src/tl_lake/{schema,sync,xer,xer_marts,doc_marts,duck}.py` (abridged: sync `_sync`, `_sync_silver`, `_changed_keys`, `_newest_seq`, `_VISIBLE_ENDS`);
`tests/{builder.py,lakecheck.py,test_rebuild_equals_incremental.py,test_schedule_history_mart.py,test_document_silver.py}`.
`schema/modules/awp/iwp_events.yaml` (the `IWPReadinessEvaluatedPayload` fields); `packages/tl-core/src/tl_core/readiness/types.py` (`CheckState`: ok, blocked, pending, n_a, unknown).

## Allowed paths
- `packages/tl-lake/src/tl_lake/{schema,sync,xer,gold}.py`, `packages/tl-lake/src/tl_lake/models/*.sql` (create)
- `packages/tl-lake/tests/**` (new tests; edit `builder.py`, `lakecheck.py` only to add helpers)
- `packages/tl-lake/{README.md,AGENTS.md}`, `docs/runbooks/lake-sync.md` (mart rows and one paragraph on the gold pass)
- `docs/tickets/P2-I6/provided/**`, `docs/tickets/P2-I6/refs/**` (create), `dev/accept/P2-I6/S1.py`, `docs/reports/P2-I6/S1.md` (create)
- pinned lists that change only because the new tables exist (rule 12), listed in the report
Not allowed: `schema/**`, `tl_core/**`, `tl-cli` (`tl lake mart ls` lists `mart_*` already), any module package.

## Steps
1. `SilverTable.change`, the two silver tables, `_VISIBLE_ENDS`, the `seq` and `whole` paths in `sync.py` (no dialect SQL; NDJSON load).
2. `gold.py`, the three stubs, the two call sites. 3. Reference SQL, provided tests, the property test, the walking test (below). 4. Docs.

## Tests to add (in the package)
- `test_gold_runner.py`: a model with a missing need is dropped and skipped; a stale mart is dropped when its need disappears (lake rebuilt over a ledger with no materials rows keeps the tables, empty); model files exist for every `GOLD_MODELS` name and each is one SELECT (`lake_query` guard accepts the mart tables).
- `test_materials_silver.py`: movements append by seq (second sync copies only new seqs; an old row is never rewritten); stock is replaced whole (a lot that goes to zero leaves no row); both agree with the ledger row for row (`lakecheck`).
- `test_marts_rebuild_equals_incremental.py`: Hypothesis history (create IWPs and lots, readiness evaluations, movements, sync points, a schedule snapshot pass in the middle, a rebuild at the end through `sync_lake` then `sync_xer`); after it every gold and silver table of the incremental lake equals the rebuilt lake and the three marts equal the reference SQL run directly over the rebuilt lake's silver/bronze. Use the lighter path to make events (raw event append through the real projectors, or the awp and materials test worlds); say which in the report.
- `test_marts_confidential.py` (**Sec**, walking test, L-P1-I8-6): an IWP and a lot made hidden (class raise or restricted subject, as `test_document_silver.py` does it) are in no row of silver or any mart, in no count (`checks_total`, `movements`, `lots`, `iwps_evaluated`), and no mart column holds a hidden id; a `resolve_via` naming a hidden record leaves no trace; declassify, sync again: rows appear; reclassify: they leave; rebuild equals. A mart row of a hidden IWP absent equals "never existed".

## Acceptance (run once each; named paths only)
```
just check
uv run python dev/accept/P2-I6/S1.py
just gate packages/tl-lake/tests
just gate-pg packages/tl-lake/tests
```
`S1.py`: SQLite, one `PASS <check>` per check, final `S1 ok`: silver tables present after a sync of a ledger with 3 movements; `build_gold_marts` creates the three tables in order; `tl_lake.lake_query` answers `SELECT * FROM mart_materials` with `as_of_seq`.

## Mutation (L-P1-I4-6; sentinel plus at most 5 targeted, in your own worktree, reported in 3 lines)
Sentinel: baseline passes, one trivial mutant killed. Targets: (1) drop `lot_id` from the `cur_materials_movement` `_VISIBLE_ENDS` entry; (2) seq-mode watermark `>` to `>=` (duplicate rows); (3) whole-mode stock reload skipped (stale row stays); (4) `build_gold_marts` does not drop a mart whose need is missing; (5) `changed` flag compares against the wrong neighbour (reference SQL, kills `T02_test_iwp_readiness_history`).

## Report
Standard (`docs/templates/haiku-report.md`), deviations first, <= 60 lines: the interface as built (signatures, column lists if changed: say so and stop if an interface above changed), the property test path, the 3-line mutation result, pinned lists changed. Return <= 15 lines. Commit subjects `P2-I6-S1: ...`; trailers `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- A column of the contract above cannot be built from the silver and bronze named (write under Blocked, do not change the column list).
- Any non-lake package imports `SilverTable` or `tl_lake.sync` internals (interface change).
- A hidden record appears in a mart and the fix needs `tl_core.confidentiality` changes (security matter, `9`).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)

## Decision (orchestrator, 2026-11-13, after the first build @95a66da0)

Two follow-ups from the builder's open questions. Both are in scope of this piece (Sec: lake guard). T02 has not started, so the interface change is allowed now.

1. **Q2, hide after copy.** A record hidden after its rows reached the lake must leave every gold mart on the next incremental sync, without `tl lake rebuild`. Add the visibility source (`cur_core_record`, or the table the guard already reads) to the `needs` of every gold model whose rows name a record that can later be hidden, and re-apply the guard on each sync. Test: reclassify, run an incremental sync, and the marts equal a rebuild and lack the record in rows and counts. Update the T02 provided tests and `refs/` if the interface line changes; say so in the report.
2. **Q1, payload refs.** `PAYLOAD_REFS` (`packages/tl-core/src/tl_core/intent.py:262`) lacks entries for `IWP.ReadinessEvaluated` (`resolve_via` record ids) and `StockLot.Moved` (`iwp_id`, `requisition_id`), so bronze rows and other payload readers can carry hidden ids. Add those entries. Then list every event type added in Phase 2 module code (awp, materials, requisitions, quality) whose payload has a record-id field missing from `PAYLOAD_REFS`; add the clear id fields, and list any doubtful ones in the report without adding them. Additive: no event changes, a hidden id becomes null for the reader. One test per added entry (hidden id is null for a reader without access, present for one with). APPROVALS line by the orchestrator at merge (core change).

Allowed paths widen to `packages/tl-core/src/tl_core/intent.py` and `packages/tl-core/tests/` for item 2.
