# P2-I6 — Simulation, lake marts, reports, Phase 2 exit (prep stream, wave 1)

Status: r1 prep. This round stages only the wave-1 prep: B2 (marts sync pass), T02 (gold marts), T03 (base reports audit).
B1, T01, T04, T05 (the exit) are wave-5 work after the web increment; they have board rows only. Plan sources:
`docs/build-spec/08-phase2-plan.md` "Increment 6" and §0.3/§0.4, `12-extension-plan.md` §3 and §4 (wave 1, SR-X1).
Board: `STATE.md`. Branch `p2/i6` from the trunk merge of `p2/ext-plan` @4624fcf. Worktree `/home/user/wt/p2-i6`.

## Objective
After the prep stream, `tl lake sync` copies the materials movement and stock projections into silver and rebuilds three gold marts from
silver and bronze with the same guarantee as the rest of the lake: a lake built by many incremental syncs equals one rebuilt in a single
load, and nothing a reader may not read is in a row or a count. The gold marts are versioned SQL models, not Python. A written audit
lists every §12 base report of M3 (AWP), M4 (materials) and M9 (requisitions and work orders) with its CLI command and API route, and
files each gap as a draft ticket.

## Demo (prep part of the I6 exit demo, clause 4 and 5 of `08-phase2-plan.md`)
1. `uv run tl lake sync` on a seeded ledger, then `uv run tl lake mart ls` lists `mart_iwp_readiness_history`, `mart_materials`,
   `mart_schedule_vs_readiness`; `uv run tl lake query "SELECT * FROM mart_iwp_readiness_history"` answers the readiness history of
   an IWP and prints `as of seq N`, the ledger seq the rows cover.
2. A second `tl lake sync` after one more `IWP.ReadinessEvaluated` adds exactly the new row; `tl lake rebuild --yes` gives the same rows.
3. The audit `docs/reports/P2-I6/T03-reports-audit.md` has one row per §12 report of M3, M4, M9, each with a command and a route that run
   (or a draft ticket under `docs/tickets/P2-I6/drafts/`). The full exit demo `dev/demos/P2-I6.sh` is T04, later.

## Pieces and tickets staged now
| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| S1 (B2) | Marts sync pass: silver adds materials movement and stock; gold model runner and the three model stubs; property test | builder, full | none | lake guard |
| T02 | Gold marts: write the three SQL models over S1's runner and provided tests | H full | S1 merged | lake guard |
| T03 | Base reports audit vs §12 for M3, M4, M9 | H lite | P2-I5 on trunk (not yet): `stg` blocked | none |

Not staged (exit wave): B1 injections and scenario, T01 scenario v2, T04 exit demo, T05 phase report (see `08-phase2-plan.md`).

## Order of work
1. S1 (builder, alone: it owns `packages/tl-lake`; checkpoint **C1** = S1 merged).
2. T02 after S1 merged (the runner, stubs and provided tests are its interface).
3. T03 when P2-I5 is merged to trunk (it audits `docs/reference/openapi.json` and the CLI; it merges before X4 S2 rewrites the registry lists, `12 §3`).
Concurrency: S1 and T03 have disjoint paths; T02 waits for S1.

## Risks and escalation triggers
- Silver gains tables that name record ids (`lot_id`, `iwp_id`, `requisition_id`); each must be in `_VISIBLE_ENDS` or a hidden record leaks (L-P1-I8-6). Escalate (9) on any leak found.
- `IWP.ReadinessEvaluated` payload carries `checks[].detail` and `resolve_via`, which can name hidden records: the marts never carry them.
- S1 changes a public symbol (`SilverTable`) of `tl_lake`: no other package imports it (checked at spec time); if the builder finds one, stop (interface change).
