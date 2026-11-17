# V3-P0 · `tl report <module>`: every module's line-level data
kind: piece · review: full + security · branch `p2/v3-p0-report` · worktree `/home/user/wt/v3p/p0` · base `p2/v3-forms`
Process: `docs/build-spec/process-v3.md` section 2 (rule 6 is this unit).

## Goal
`tl report <module> --project <P> [--format csv|jsonl] [--out <file>]` writes one row per record of the module,
for the signed-in viewer: hidden records are left out exactly like missing ones (no count, no gap, no hint).
Default format CSV to stdout; header row first; dates ISO; empty values empty (CSV) or null (JSONL). `tl report`
with no module lists the available modules, one per line.

Modules in this unit (one report each): form submissions (and form templates), RFIs, correspondence,
documents, and the modules that already have an export (awp, materials, scaffold): wrap those so `tl report`
lists them. The rest (tags, IWPs, CWPs, constraints, activities, requisitions, work orders, punch, inspections,
permits, isolations, QR codes) are unit P0b, a registration-only follow-up: make adding one a ~20-line change
(a `Report` row plus a pinned-header test) and write `docs/tickets/P2-FORMS/v3/P0b-registrations.md` listing
each remaining module's list view and proposed columns. Columns: the module's log/list columns plus its key
dates and the record key; no internal ids unless the viewer has technical details (same rule as the TUI).

## How
- A new module hook kind `reports` in `packages/tl-core/src/tl_core/modules.py` (beside `commands`,
  `read_routers`, `tools`, `cli_groups`): a module names `<pkg>.reports:REPORTS`, a sequence of
  `Report(name, title, columns, rows(conn, scope, viewer) -> Iterable[Mapping])`. Core modules not yet on hooks
  (RFIs, correspondence, documents, tags) register through the same table in their own package or in tl-cli,
  whichever the hook contract allows. This is a core-interface change: add the APPROVALS line
  ("P2-FORMS V3-P0 (owner asked 2026-11-17; core interface) ...").
- `rows` reuses the module's existing list view (no new SQL unless the view lacks a column; then a minimal
  select with `confidentiality.not_hidden`/`not_hidden_each`). Page through the view rather than one huge read.
- Existing `tl corr report`, `tl doc report`, `tl tag report`, awp and materials reports stay as they are.

## Tests (one file per area is fine)
For each report on the full demo ledger (reuse V3-P1's cached ledger helper if merged; else build a small ledger
with the generator sections the module needs): header pinned; row count equals the module's list view count for
the same viewer; a confidential record present for a full viewer and absent for a low viewer, and the low
viewer's output is byte-identical to the output of a ledger where that record never existed (hidden == missing);
`--format jsonl` lines parse and match the CSV rows.

## Gate
`just check` on changed files; `just gate packages/tl-core/tests packages/tl-cli/tests tests/confidentiality`
plus the test paths you add. `uv run python dev/tools/export_reports.py` unchanged.

## Report
`docs/reports/P2-FORMS/V3-P0.md`, at most 15 lines: modules covered (list), one sample header per area, test
counts, anything not covered and why. No model names. Subject prefix `V3-P0:`.
