# P2-I4B STATE  r=1 base=d4e92ffc C=0 ck=- gate=n/a wt=/home/user/wt/p2-i4b
## BOARD   (S1 = plan B4; `stg` staged, spec not yet written)
S1 p mrg f 256d9014 findings dec by orch; 2nd gate PASS per file; APPROVALS
T06 t mrg f 1c3e1294 review P; F2 ctrl+i is Tab -> T07a
T01 t stg f - read views and export_rows; after S1
T05 t stg f - scaffold_tagged, labour_requested; after S1
T09b1 t stg f - API routes and five-reader walk; after T01
T09b2 t stg f - client methods and fakes; after T09b1
T07a t stg f - TUI register, record view, nav for both screens; after T09b2, T06
T10 t stg f - sim actor, demo clauses 2 3 6; after T05, T07a
T11 t stg l - tour shots (owner rule); after T07a, T06
T12 t stg l - docs, runbook, AGENTS row; last
## DEC
D1 2026-11-15 TagScaffoldGreen is its own command (word scaffold.tag.green, controller); InspectScaffold takes conditional or fail only: one word per command (W3-2); S1, contract §3
D2 2026-11-15 states Requested Designed Erecting Inspected In Use Modify Dismantle Removed; fail on Inspected or In Use moves to Modify; fail on Erecting stays; Release needs a green tag; S1
D3 2026-11-15 dismantle holds while a requiring IWP is Issued, In progress or On hold, or another open scaffold request of that IWP exists (own request excluded: it stays open until Closed); narrows contract §3 wording; hidden IWPs named as "a work package you cannot see"; S1
D4 2026-11-15 plan 6 -> 10 items: T01 views, T09b split, T11 tour, T12 docs added; MCP tools not planned for B (no clause needs them); no PLANCHK (10 is not more than about 10); README
D5 2026-11-15 owner rule 2026-11-14: register export is `export_rows` (CSV, JSONL) in T01; screenshots in the tour (T11, actors `user:<name>`); README
D6 2026-11-15 T06 stays unregistered; T07a registers both screens (one glue owner for app.py and commands.py); T06, T07a
D7 2026-11-15 offline class `none` for both record types (acts on the authority, as WorkOrder); S1
D8 2026-11-15 toolcrib tool = lot key (a serialised tool has its own lot) or an item code with one lot in the crib; I3 has no serial register, none added; T06
## SEC
(none yet; SR4 rows: S1 confidentiality part (hidden IWP hides its scaffold and the dismantle text), green-tag word, dismantle guard; T09b1 five-reader walk; one wave review)
## OPEN
Q1 Offline-class and `valid_time` choices for scaffold are the supervisor's (D7); orchestrator may veto at the S1 human gate | needs orch | raised r1
Q2 DEFERRED line proposed: scaffold MCP read tools and a `tl scaffold` CLI group (X4 cli_groups hook) | needs orch | raised r1
## DEC-ORCH 2026-11-15 (S1 review 2s)
S1-F2 ruff extend-exclude docs/tickets/*/provided accepted (provided copies are linted where they land)
S1-F3 optional `at` on all scaffold events and the extra optional fields accepted (additive; frozen baseline test)
S1-F4 scaffold reads cur_requisitions_scaffold_request directly: record in phase2-contracts-draft.md §3 As-built (T12)
S1-F5 hidden-IWP test patches _hidden (no confidential IWP exists yet): report says so; real path when IWPs carry classes
T06 size (654 lines, mostly the acceptance script) accepted; its lint block clears once S1 is in p2/i4b
## NEXT
1. Orchestrator: dispatch S1 (builder, `/home/user/wt/i4b/s1`) and T06 (`/home/user/wt/i4b/t06`); T06 gets the provided test copied byte-identical; S1 gets `provided/S1_test_rules.py` copied to `packages/tl-modules/scaffold/tests/test_rules.py`.
2. After S1 merges (C1): round 2 writes T01 and T05 (with their provided tests from S1's names), then refines T09b1 and T09b2 from the merged report.
3. T05 reads `phase2-contracts-draft.md` §1 (statuses, `IwpFacts`) and `tl_mod_awp/readiness/checks.py`; labour check needs `tl_mod_requisitions.api` reads only.
4. After T09b2: T07a (needs T06 merged for the nav), then T10, T11, T12; DONE round writes `docs/reports/P2-I4B.md` and the AGENTS.md table row.
5. Close: `just check`, whole gate split by package, `just gate-pg` on touched dirs, `just demo P2-I4` (clauses 2, 3, 6 added), SR4.
## REFS
Specs `docs/tickets/P2-I4B/S1-scaffold-schema-and-lifecycle.md`, `T06-toolcrib-screen.md`; provided tests `docs/tickets/P2-I4B/provided/S1_test_rules.py` (copy to `packages/tl-modules/scaffold/tests/test_rules.py`) and `provided/T06_test_toolcrib_text.py` (copy to `packages/tl-tui/tests/test_toolcrib_text.py`).
Patterns: `docs/tickets/P2-PUNCH/` (S1 S2, T01 T03 T04 T06), `docs/tickets/P2-I4A/` (T04c1 T04c2 T07a), `packages/tl-modules/quality/`, `tl_mod_awp/readiness/job.py`, `phase2-contracts-draft.md` §3.
Gate paths checked with ls: `packages/tl-schema/tests`, `tests/services/test_modules.py`, `packages/tl-core/tests/auth/test_access_words.py`, `packages/tl-core/tests/test_numbering_config.py`, `packages/tl-tui/tests`; created by items: `packages/tl-modules/scaffold/tests`, `packages/tl-schema/tests/test_scaffold_schema.py`, `packages/tl-tui/tests/test_toolcrib_text.py`.
## TRAPS
X4 (p2/x4, in progress): `ModuleSpec` gains hooks `commands`, `read_routers`, `tools`, `cli_groups` and an `IN_TREE_SURFACES` set. When X4 merges the scaffold module needs its hooks and a set entry (routes, any CLI group): not built now; S1 must not touch `tl_core/modules.py`; a round after X4 C-merge adds a ticket, and T09b1 and T07a registration lines follow whichever form is on the trunk then.
Gates name test files or one package (OOM on 16 GB); the `tests/tools` gate is slow (background); `gate-pg` is slow, name directories; never `pkill -f`; never delete /tmp/pytest-of-root; pinned lists as union.
Commit trailers name the model each agent ran as (session attribution, D-r3e of I4A); reports and files carry no model names.
