# P2-I5-S3 — progress rollup (IWP to CWP to WBS to cost code) and the progress CSV export

Status: ready (S1, S2 merged; pairs with S4a in one round, disjoint paths)
Tier: builder
Kind: piece
Review: full
Labels: money, export, cli
Depends on: S2 (`tl_mod_awp.progress.engine`, `cur_awp_iwp_progress`)
Branch: `p2/i5-s3-rollup-export`
Worktree: `/home/user/wt/i5-s3`
Approver: orchestrator reads the diff (money arithmetic, CSV cells); no schema, no new event, no new word (see D17)

## Goal
After this piece earned hours roll up from IWP to CWP to WBS node to cost code with the budget rollup's own arithmetic, and `tl awp export progress --period 2026-W45` prints a CSV by cost code that
cannot carry a formula. The figures are computed on read from the stored IWP progress rows; nothing is stored, no job, no event (D17: a stored figure would need a new event and a human gate; owner trimmed scope).

## Brief references (pasted)
- Earned progress rolls up IWP to CWP to WBS node to cost code and leaves as a CSV per period (README Objective). `cost.CostCode` is read, never written; `cur_cost_*` is never touched.
- Math rules F9 (S2 module docstring, `progress/engine.py`): 1 the IWP figure is the stored, unfiltered one; 2 null item hours weigh the mean of the set, none set means 1 each; 3 exact sums, one half-up rounding at the output, parts of one total split by largest remainder;
  cap 100 is per IWP only (earned hours are not capped to the CWP budget).

## Interfaces to build (names fixed here)
```python
# tl_mod_awp/progress/rollup.py   (new; reads only)
@dataclass(frozen=True) class CwpProgress:  cwp_id: str; key: str; iwps: int; earned_hours: Decimal; hours: Decimal   # 1 dp, half-up at output
@dataclass(frozen=True) class NodeProgress: node_id: str; earned_hours: Decimal; budget_hours: Decimal | None; pct: Decimal | None  # pct = earned / budget, 1 dp, null without budget
@dataclass(frozen=True) class CostLine:     cost_code_id: str | None; code: str | None; earned_hours: Decimal; budget_hours: Decimal | None   # None = the unallocated line
@dataclass(frozen=True) class ProgressRollup: scope: str; as_of_seq: int; cwps: list[CwpProgress]; nodes: list[NodeProgress]; lines: list[CostLine]; notes: list[str]
def progress_rollup(conn, scope: str, *, viewer: Viewer | None = None) -> ProgressRollup
# tl_mod_awp/progress/export.py   (new)
PERIOD_PATTERN: Final = r"^[0-9]{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$"
def csv_cell(value: object) -> str          # text; a cell whose first character is = + - @ TAB or CR gets a leading apostrophe; all cells go through the csv module with QUOTE_ALL
def export_progress(conn, scope: str, period: str, *, viewer: Viewer | None = None) -> str   # header, one row per cost code line, unallocated last; refuses a bad period with ExportError("period: expected YYYY-Www")
# tl_cli/awp_export.py (new)  `tl awp export progress --period YYYY-Www [--project P] [--out FILE]`; registered by one line in tl_cli/awp.py
```
Columns: `period,scope,cost_code,earned_hours,budget_hours,earned_pct,as_of_seq`; `cost_code` is the code text, or `(unallocated)`; empty cell for a null budget or pct.
**Arithmetic.** (1) IWP hours = sum of its non-void item hours (rule 2 null weight); IWP earned = stored `earned_pct` / 100 x IWP hours, exact (`Fraction`/`Decimal`, never float). An IWP in state Cancelled or Split, or void, is out; an IWP with no stored row earns 0 and still counts its hours.
(2) CWP earned = sum over its IWPs. (3) Nodes and cost codes: call the existing `rollup.compute(parents, mapping, budgets, allocations)` with the CWP earned hours as `budgets`; it already spreads a CWP over its WBS allocation percents, adds descendants to ancestors and splits a node over its cost-code
mapping by largest remainder. Do not re-implement it. (4) `budget_hours` of a node or cost line comes from the stored `cur_awp_rollup` rows (`measure budget_hours`, `line total` and `cost_code`); none stored means null and the note `no budget rollup yet`.
(5) With a `viewer`, a CWP or IWP the viewer cannot open drops out and the note `some packages not shown` is added (no count); the figures of what remains are unchanged by hidden items inside a visible IWP (rule 1).
`as_of_seq` is `MAX(seq)` of `events`, read first. Batch the reads (one statement per table, never one per IWP).
**Escalate rather than invent:** a need to store a figure, a new event or table, a change to `rollup.compute`.

## Context (<= 12 files)
`packages/tl-modules/awp/src/tl_mod_awp/{rollup.py,worker.py (the SQL constants only),progress/engine.py,names.py}`; `schema/modules/awp/{rollup,progress,cwp}.yaml`; `packages/tl-cli/src/tl_cli/{awp_report.py,awp_run.py,awp.py}`; `docs/reports/P2-I5/S2.md`;
`grep -rn "formula" packages/tl-api/src/tl_api/routes/materials.py packages/tl-cli/src/tl_cli/mat_report.py` (reuse a guard if one exists; otherwise `csv_cell` above).

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/progress/{rollup.py,export.py}` (new); `progress/__init__.py` (export lines only)
- `packages/tl-cli/src/tl_cli/{awp_export.py (new),awp.py (one register line)}`
- `packages/tl-modules/awp/tests/{test_progress_rollup.py (new),progress_world.py (extend)}`; `packages/tl-cli/tests/test_awp_export.py` (new)
- pinned lists written as the union, each listed in the report: `packages/tl-cli/tests/test_cli_awp.py` (verb list, if it pins one), `packages/tl-cli/tests/test_reports.py` (if the report names or awp help change), `docs/reference/awp.md` (a line for the export verb; plan check F10)
- `dev/accept/P2-I5/S3.py`, `docs/reports/P2-I5/S3.md` (create)
Not allowed: schema, `tl_core/**`, `rollup.py`, `worker.py`, `module.py`, `commands.py`, other modules, `tl-api`, `tl-tui`, `tl-mcp`, `cur_cost_*` writes.

## Acceptance (run once each)
```
just check
uv run python dev/accept/P2-I5/S3.py
just gate packages/tl-modules/awp/tests
just gate packages/tl-cli/tests/test_awp_export.py packages/tl-cli/tests/test_cli_awp.py
```
`S3.py` (SQLite, dialect-neutral; a helper `check(name, ok)` prints `PASS <name>` only when `ok` is true and exits 1 otherwise; final `S3 ok`): the worked example of 3 IWPs (10, 10, 20 hours at 50.0, 100.0, 25.0 percent) gives CWP earned 20.0 of 40.0; a CWP allocated 33/33/34 over three nodes gives parts that sum to the rounded total (rule 3, 10.0 gives 3.3/3.3/3.4);
a node with descendants includes them; the cost-code lines of one node sum to the node total; an IWP with null hours weighs the mean; a Cancelled IWP is out; a hidden CWP is absent for the viewer and the note appears while the unfiltered figure is unchanged; a node without a stored budget exports an empty budget cell and the note; the CSV of a cost code titled `=cmd|' /C calc'!A0` and one starting `+`, `-`, `@` reads back through `csv.reader` with a leading apostrophe on each; a bad period is refused with the fixed text; `cur_cost_*` row counts and the ledger head are unchanged by an export.

## Tests to add
- `packages/tl-modules/awp/tests/test_progress_rollup.py`: each check above as a unit test, plus rebuild equality (rebuild the projections from the ledger; `progress_rollup` returns the same figures) and "the same call twice returns equal output".
- `packages/tl-cli/tests/test_awp_export.py`: `export progress` stdout header and rows, `--out` writes the file with mode 0600 and prints `wrote <path> rows=<n>`, a bad period exits 2 with the fixed text, no `--project` uses the default project like `awp_report.py`.

## Report requirements
Deviations first; <= 60 lines; the pinned files changed; mutation: sentinel plus <= 5 (the half-up rounding, the largest-remainder order, the Cancelled exclusion, the viewer filter, the leading-apostrophe guard), 3 lines.
## Escalation triggers
`rollup.compute` cannot take earned hours as `budgets`; a CWP has IWPs but no allocation (unallocated line shape differs from the spec); a need to write a figure; a frozen contract change.
## Blocked
(builder writes here)
## Decision
(supervisor or orchestrator writes here)
