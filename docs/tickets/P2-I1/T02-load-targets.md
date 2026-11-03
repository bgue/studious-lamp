# P2-I1-T02 — Load targets `awp.wbs` and `awp.cwa`

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: core
Depends on: S3 (merged @f482aad); built beside S4 and S5 (disjoint paths)
Branch: `p2/i1-t02-load-targets`
Worktree: `/home/user/wt/i1-t02` (from `p2/i1` head)

Why a piece, not a Haiku ticket (§6 items 2 and 5): a target is a data-conversion job with five methods and a
compensation rule that is not yet decided anywhere (below). Decision D8 in `STATE.md`. The id stays T02 for the board.

## Goal
After this piece `uv run tl load targets` lists `awp.wbs` and `awp.cwa` (scope `project`), and a loader whose `target`
is one of them can plan, apply, compare and take back a load. T01 (samples, mappings, loaders) builds on it.

## Brief references (pasted; spec `docs/build-spec/specs/m3-wbs-cwp.md` §6 is authoritative)
`awp.wbs` creates nodes (`code`, `title`, `parent`, optional `cost_codes` as `CODE:PCT;CODE:PCT`) parents first, and
plans a row invalid with a fixed reason when its parent is unknown, its depth > 8 or its percentages do not sum to 100
(`allocation sums to 101.00, not 100.00`). `awp.cwa` creates CWAs and, with a `sequence` column, the version-1 path.
The load is create-only and compensable (ADR-0014 rule): a row whose code the project holds is left alone and counted,
never changed; every command carries source `legacy:<system>` and the load's correlation id; no cell text in a
problem (a line number and fixed words or a field name). `tl load` stays an admin act.

Decisions for the undecided points (apply, and report any that proves wrong as *Blocked*):
- Existing-code check: `common.resolve_code(conn, scope, record_type, code)` only (S4 is changing how keys are spelled;
  never query `cur_core_record` keys yourself). A code the viewer cannot read counts as absent (the load runs as admin
  with the lowest-clearance viewer default; do not widen it).
- Apply writes with the awp commands and handlers (`DefineWbsNode`, `MapWbsToCostCodes`, `DefineCwa`,
  `DefinePathOfConstruction`), never with `create_module_record` directly; parents before children (sort by depth, then
  file line). A parent that is in the same file counts as known. A `cost_codes` cell naming an unknown cost code: invalid
  row, fixed reason. Percent text is ASCII digits only.
- `awp.cwa` with a `sequence` column: the version-1 path is defined once, from the file's rows ordered by `sequence`
  (integers, no repeats), only when the project has no path yet; a project that has one: the rows still load as CWAs and
  the path is left alone, counted as `existing`.
- Reversal (`reversals`/`reverse`): a node or CWA the run created is taken back by `RetireWbsNode` / `RetireCwa` with the
  given reason; `reversible=False` with a fixed problem when the command would refuse (a non-void CWP names it, or a child
  that the run did not create exists). The version-1 path the run defined cannot be taken back: report it as an
  irreversible item with a fixed problem, and leave it. Children before parents.
- `compare`: for rows the run created, compare title, parent code, and the cost code lines; `left_alone_differs` counts
  existing rows that differ, as the built-in targets do.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-modules/legacy/src/tl_mod_legacy/targets.py (Protocol Target, lines 133-176)
class Target(Protocol):
    kind: TargetKind;  module: str;  scope: TargetScope   # "project" | "company"
    def plan(self, conn, scope, loader: LoaderDef, grid: Grid) -> Plan: ...
    def apply(self, uow, scope, loader, plan, *, actor, source, correlation_id, confidentiality) -> list[Created]: ...
    def compare(self, conn, scope, loader, grid, created_keys: set[str]) -> Comparison: ...
    def reversals(self, conn, scope, record_ids: list[str], correlation_id: str) -> list[Reversal]: ...
    def reverse(self, uow, scope, record_ids, *, actor, source, correlation_id, reason) -> int: ...
# PlannedRow(line, key, raw, native), Plan(rows, existing, invalid), Created(record_id, key, line, raw),
# Reversal(record_id, key, state, reversible, problem), Comparison(valid, matched, missing, differs,
# left_alone_differs, invalid)
# entry points: [project.entry-points."throughline.load_targets"]  name = "module:function" -> returns a Target
```
Shape to copy: `TagTarget` / `DocumentTarget` in the same file (a handler-based target). `Grid`, `LoaderDef` in
`tl_mod_legacy/model.py`. `packages/tl-modules/awp/src/tl_mod_awp/targets.py` holds the two stubs `wbs_target()`,
`cwa_target()` with the docstring of the contract.

## Context (<= 8 files)
- `docs/build-spec/specs/m3-wbs-cwp.md` §6; `docs/runbooks/legacy-load.md` (the sequence)
- `packages/tl-modules/legacy/src/tl_mod_legacy/targets.py` (Protocol, `TagTarget`), `model.py` (`Grid`, `LoaderDef`)
- `packages/tl-modules/awp/src/tl_mod_awp/{targets,common,commands}.py`, `handlers/wbs.py` (rules and messages to reuse)
may explore: `packages/tl-modules/legacy/tests/test_load_targets.py` for how a target is exercised.

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/targets.py`
- `packages/tl-modules/awp/pyproject.toml` (two entry-point lines under `throughline.load_targets`; the dependency on
  `tl-mod-legacy`, named here; then `uv sync`) and root `uv.lock`
- `dev/accept/P2-I1/T02.py` (create), `docs/reports/P2-I1/T02.md` (create)
Not allowed: `tl_mod_legacy` source, any `schema/**` or generated file, S4's and S5's files, new pytest files.

## Acceptance (run these once; no pytest)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run tl load targets
uv run python dev/accept/P2-I1/T02.py
```
`uv run tl load targets` lists `awp.wbs` and `awp.cwa`, scope `project`. `T02.py` (SQLite tmp db, admin acting,
one `PASS <check>` per check, final `T02 ok`, <= 40 lines; it writes a small CSV in the tmp dir and drives the target
through its methods or the `tl load` sequence of the runbook): 12 nodes load parents first (3 levels, two with cost
codes), a row summing to 101 is invalid with the fixed reason and no cell text, an unknown parent and depth 9 are
invalid, a second run counts all 12 as existing and writes nothing, `compare` matches, CWAs load with `sequence`
and define path v1, a project with a path leaves it alone, `reverse` retires the run's records children first,
a node the run created reverses to Retired, the path is reported irreversible, a `viewer` or `user` cannot start
the load (admin act), no model-visible text of a cell appears in any problem.

## Guards T11 will mutate (name file:line in the report; run no mutants here)
Sum = 100 plan check; parents-first order; create-only (existing left alone); the existing-code check goes through
`resolve_code`; children-before-parents reversal; the admin gate.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first (each undecided point you resolved differently);
files; acceptance output (<= 5 lines per command); guards file:line; candidate learnings. Builder return <= 15 lines.

## Commit
Subject `P2-I1-T02: <imperative summary>`; body says what and why; end with the harness attribution line, then the line
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not
merge; do not push.

## Escalation triggers
- *Blocked* if: the `Target` protocol cannot express the path or the reversal rule; `RetireWbsNode` cannot take back a
  node without a `tl_core` change; the entry-point group needs a change in `tl_mod_legacy`.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
