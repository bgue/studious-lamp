# V3-P1 · Speed: per-row hidden-record check, and the speed budget gate
kind: piece · review: full + security · branch `p2/v3-p1-speed` · worktree `/home/user/wt/v3p/p1` · base `p2/v3-forms`
Process: `docs/build-spec/process-v3.md` (read section 2 first; it replaces the ticket anatomy for this unit).

## Goal
1. `confidentiality.not_hidden_each` / `hidden_sql(viewer, only=...)` / `is_hidden` / `hidden_among` (the per-row
   forms in `packages/tl-core/src/tl_core/confidentiality.py`) return exactly the same rows as today for every
   viewer, and are fast. Today the statement is ~105 KB (16 subject rows, two hops, the forms draft chain,
   LEFT JOINs on `COALESCE(...)` that no index can serve); `requisition_list` for `user:treyes` takes ~85 s on the
   full demo ledger (46 rows). Target: every module list view under 1 s on the full demo ledger (SQLite), and no
   slower on Postgres than today.
2. `tests/perf/test_budget.py`: builds (or reuses) the full demo ledger (`just demo-project <db>`, all sections,
   ~4 min) cached under `.gate/demo-full/<hash of dev/seed/** and schema/**>.db`; times each module's list view
   (and, once V3-P0 lands, each `tl report` module) as a low viewer (`user:treyes`) and a full viewer, median of 5; fails any
   call over 1.0 s; also caps the per-row hidden statement size (say 20 KB); build the cache under a file lock
   with an atomic rename, printing the slowest five. Mark it so `just gate tests/perf` runs it (one pytest marker or
   path; not in the 4-part whole suite unless cheap).

## Design freedom and limits
- Your choice of form: a correlated `NOT EXISTS` over a `UNION ALL` of one indexable lookup per subject row,
  resolving the subject id once per row; or another equivalent. No schema change, no new event, no projection
  table (if you conclude an index or projection is the only way, stop and return 4 with the measurement).
- PERF1 (`_cf_chain` CTE, whole-ledger form) is already on the base: keep it and its test green.
- Hidden must look exactly like missing: same row sets, same 404 texts, same counts. Differential test: extend
  `tests/confidentiality/test_hidden_sql_equal_old.py` (or a sibling) so the new per-row form is compared with
  the old one (kept as a test-only copy) over every viewer class and every subject row, including two-hop chains
  and own drafts.
- Mutation: sentinel + up to 5 targeted mutants on the guards (author exemption, two-hop link, level compare);
  3 lines in the report.

## Gate
`just check` on changed files; `just gate tests/confidentiality packages/tl-core/tests tests/perf`; one
`just gate-pg tests/confidentiality` run in the background with `timeout 3600` and a per-test timeout
(`-o faulthandler_timeout=300` or `--timeout` if installed) so a hang names its test — report result and time (a hang
is reported, not a blocker; the owner deferred it). Then the phase 2 tour with the normal wait:
`just tour phase2 <scratch dir>` must exit 0 (it failed at 08-requisitions on the slow read).

## Report
`docs/reports/P2-FORMS/V3-P1.md`, at most 15 lines: before/after timings (top 5), statement size before/after,
differential test result, mutants, pg result, tour exit. No model names. Subject prefix `V3-P1:`.
