# Report P2-I4B: scaffold module

Status: done (C4, 2026-11-16). Base `485b85b5`, branch `p2/i4b`; trunk with P2-X4 merged in by S2 (`da006372`). Written from `docs/tickets/P2-I4B/STATE.md` and `docs/reports/P2-I4B/`.

## What was built
Scaffold requests become scaffolds with a lifecycle, inspections, a green tag and a readiness check, reachable over the API, the TUI, a demo and the tour. Increment plan: `docs/tickets/P2-I4B/README.md`. Runbook `docs/runbooks/scaffold.md`; module doc `docs/modules/scaffold/README.md`.

| Item | Kind | Result |
|---|---|---|
| S1 | piece | schema, module spec, commands, handlers, rules, `inspections_due` job (D1 to D3, D7) |
| T01 | ticket | read views: list, detail, due_list, export_rows CSV and JSONL (D12) |
| T05a, T05b | tickets | readiness checks `scaffold_tagged` and `labour_requested` (D9, D10) |
| T06, T07a, T07b | tickets | toolcrib screen; toolcrib keys F2, F3, Ctrl+R; scaffold register and record screens (D11, D15) |
| T09a, T09b1, T09b2, T09c | tickets | command door, API read routes and export, client methods, scaffold error rows (D13, D14, D18) |
| T10a, T10b | tickets | demo clauses 5 and 6 (scaffold), clause 7 (toolcrib) in `dev/demos/P2-I4.sh`, driver `dev/demos/p2_i4b_demo.py` (D17) |
| T11a, T11b | tickets | demo-project scaffold section; tour shots 13 to 15 and fixes to shots 05 and 07 (D19) |
| T12 | ticket | docs, contracts §3 As built |

Plan grew from 6 to 14 items (D4, D18) with one piece. No supervisor-built code. No plan check (items small, one batch per seam).

## Decisions worth knowing
- One word per command: `TagScaffoldGreen` is its own command; `InspectScaffold` takes conditional or fail only (D1).
- Fail on Inspected or In Use moves to Modify; fail on Erecting stays; Release needs a green tag (D2).
- Dismantle holds while a requiring IWP is Issued, In progress or On hold, or another open request of that IWP exists; hidden IWPs read "a work package you cannot see" (D3).
- `labour_requested` is blocked when hours are set and no approved labour requisition covers the dates (D10, Q3 accepted).
- Orchestrator rulings on S1 review: provided copies are linted where they land (ruff `extend-exclude` for `docs/tickets/*/provided`); optional `at` on all scaffold events; direct read of `cur_requisitions_scaffold_request` recorded in contracts §3; hidden-IWP test patches `_hidden` until IWPs carry classes.

## Review and security
Every piece and full-review ticket passed review; S1 needed a second pass (findings decided by the orchestrator). No SEC findings recorded yet. SR-I4B rows: S1 confidentiality (hidden IWP hides its scaffold and the dismantle text), green-tag word, dismantle guard, T09b1 five-reader walk.

## Open gates (orchestrator)
1. DONE gate: `just check`; whole suite per directory; `just gate-pg` on touched directories (`packages/tl-modules/scaffold/tests`, `packages/tl-api/tests/test_api_scaffold_commands.py`, `tests/api/test_client_scaffold.py`); `just demo P2-I4` on both adapters.
2. SR-I4B: running.
3. `just tour phase2` is optional here; T11b read by the orchestrator only (lite).

## Deferred
- Richer scaffold states in P200: the demo has one approved scaffold request, so the seed builds 1 scaffold (Designed); Erecting, In Use and Modify paths are coded but have no P200 data.
- MCP scaffold read tools and a `tl scaffold` CLI group (Q2): wait for X4 C2.
- Move the command splat in `tl_api/commands.py` and the route line in `app.py` into `module.py` hooks after X4 C2 (D13).
- Rename `test_nine_checks` (T05a, T05b: the check set is now smaller).
- Smaller: T09b2 has no non-empty due list in client tests (T09b1 and fakes cover it); T07b `register_page` tuple shape accepted as built; the demo echo "clauses 1-4 passed" understates the run (T10a).

## Learnings
Appended to `docs/memory/LEARNINGS.md`: L-P2-I4B-1 to L-P2-I4B-4.

## DONE (orchestrator, 2026-11-16)
- SR-I4B: S1b fixed the hidden-IWP dismantle check collapse; F2 and F5 LO are in DEFERRED.
- T13 (scaffold events carry record_id) and the green-tag agent decision (`TagScaffoldGreen` agent-may-not) closed the DONE-gate fallout.
- S2 merged trunk (P2-X4 hooks) and moved scaffold onto its `ModuleSpec` hooks (`commands`, `read_routers`); `scaffold` joins
  `IN_TREE_SURFACES` (one core line, APPROVALS); no scaffold line is left in the tl-api registries; nine scaffold commands are
  excluded:reserved.
- Gates: whole suite per directory before S2 (all pass, schema generate and offline classes alone); after S2: tl-api five chunks,
  tl-mcp 648, tests/services 677, contract 189, webhooks 105, scaffold 126, plus S2's named files. Demo clauses 5 to 7 OK earlier.
