# P2-TOUR2 S2 — Why demo actors are refused the newer modules' read words, and the fix

kind: piece
review: full
branch: p2/tour2-s2
worktree: /home/user/wt/tour2/s2

## Why (P2-TOUR2-T01, DEFERRED row 2026-11-14)
On the demo project P200 (`dev/seed/demo_project`, roster in `core.py:36-58`), every actor is refused:
`core.constraint.view needs the read access word for core on project:P200` (ConstraintScreen),
`requisitions.view needs the read access word for requisitions` (RequisitionLogScreen, WorkOrderBacklogScreen),
`quality.view needs the read access word for quality` (PunchLogScreen), even `hsato` who holds `("quality", "superuser")`
and `gwhitfield` with `("*", "viewer")`. `lhartmann` with `("awp", "superuser")` reads awp screens fine. The check is
`tl_core.auth.module_roles.require_word` -> `holds_word` -> `effective_roles(...).words` (`module_roles.py:374-427`).

## Goal
1. Find the cause with a probe (scratch script, not committed): build P200 with `dev.seed.demo_project.__main__.run`
   on a temp SQLite file, then print `effective_roles(conn, holder_for_actor(conn, "user:hsato"), scope="project:P200",
   module="quality")` and the same for requisitions, core and awp. Candidates: the module's role table lacks `read`; the
   module is not enabled on P200; the seed grants at another scope; `*` does not expand to modules registered later;
   the `core` module has no grantable roles at all.
2. Fix at the cause, the smallest change: if it is product code (role catalogue, `*` expansion), fix there with a
   test that a superuser and a `*` viewer hold `read` on quality and requisitions; if it is the seed only, fix the seed
   grants (give `hsato` quality, `treyes` requisitions, `gwhitfield` viewer that reaches them, and some actor the core
   constraint view word) without changing who may write what. Never widen an access word for agents (ADR-0009).
   If the fix needs a schema or core-interface change, stop and report (orchestrator decides).
3. Add the four shots to `dev/tour/phase2.py` (02-constraints, 08-requisitions, 09-work-orders, 10-punch; the
   T01 report lists screen classes) with an actor that now reads them, and regenerate `docs/reports/tour/phase-2/`.

## Allowed paths
- `packages/tl-core/src/tl_core/auth/module_roles.py` (only if the cause is there) and its tests
- `packages/tl-modules/**/module.yaml` or role tables of quality and requisitions (only if the cause is there)
- `dev/seed/demo_project/core.py` (grants only)
- `dev/tour/phase2.py`, `docs/reports/tour/phase-2/**`
- `packages/tl-core/tests/test_module_read_words.py` (create, if product code changes)
- `tests/tools/test_demo_project*.py` (only to update a pinned grant count)
- `docs/reports/P2-TOUR2/S2.md` (create)

## Gate
`NODE_OPTIONS=--max-old-space-size=6144 just check`; `just gate <the test files you touched or created> tests/tools`
(at most these; another heavy run is live on the box); `just tour phase2` exits 0 with 12 screenshots. Run the
tour after the gate, not beside it.
Mutation: only if product code changed: sentinel plus at most 2 targeted mutants, 3 lines in the report.

## Report
Cause in 3 lines with the probe output that shows it. Builder return ≤ 15 lines; report ≤ 60 lines; commit
`P2-TOUR2-S2: ...` with the session trailers; no model names in committed text.
