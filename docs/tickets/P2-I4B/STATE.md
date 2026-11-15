# P2-I4B STATE  r=2 base=d4e92ffc C=1 ck=- gate=n/a wt=/home/user/wt/p2-i4b
## BOARD   (S1 = plan B4; `todo` ready to dispatch, `stg` staged)
S1 p mrg f 256d9014 C1; findings dec by orch; APPROVALS
T06 t mrg f 1c3e1294 review P; F2 ctrl+i is Tab -> T07a (D11)
T01 t mrg f f6bf1990 review P
T05a t todo f - scaffold_tagged check + entry point; 11 provided tests
T05b t stg f - labour_requested replaces awp placeholder; after T05a; 12 provided tests
T09b1 t stg f - API read routes, five-reader walk; spec written after T01 merges
T09b2 t stg f - client methods and fakes; after T09b1
T07a t stg f - TUI register, record view, nav for both screens; ctrl+i (D11)
T10 t stg f - sim actor, demo clauses 2 3 6; after T05b, T07a
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
D9 2026-11-15 T05 split: T05a scaffold_tagged, T05b labour_requested (one name had an awp placeholder; two entry points of a name are refused, so T05b moves it; both edit scaffold pyproject and exact-set pins: sequential). scaffold_tagged: n_a if no live requires link; good = Inspected or In Use, green, next_due_on >= today (Modify, Dismantle, yellow, red block); reads next_due_on, not the setting; T05a, T05b specs
D10 2026-11-15 labour_requested: n_a when estimated_hours is None or 0; else ok if an approved-or-later labour requisition covers planned_start..planned_finish (any one when dates are missing), pending if one is Requested, else blocked; one SQL on the labour table (api has no dates); lives in tl_mod_scaffold/labour.py; T05b
D11 2026-11-15 T07a settles the toolcrib mode keys: Ctrl+I is Tab in a terminal, so bind issue to a letter-free alternative (e.g. F2 issue, F3 return, keep Ctrl+R) and fix KEYS and the T06 text test in T07a; T06 F2
D12 2026-11-15 views: list, detail (+inspections), due_list, export_rows (CSV with formula guard, JSONL; no id column); statement bounds 2/2/1; T01
## SEC
(none yet; SR4 rows: S1 confidentiality part (hidden IWP hides its scaffold and the dismantle text), green-tag word, dismantle guard; T09b1 five-reader walk; one wave review)
## OPEN
Q3 closed 2026-11-15 (orch): accept D10 (blocked when hours and no labour requisition). T05b adds labour requisitions to demo/accept/tour data that expects ready; if more than 3 scripts are affected it stops and lists them.
Q1 Offline-class and `valid_time` choices for scaffold are the supervisor's (D7); orchestrator may veto at the S1 human gate | needs orch | raised r1
Q2 DEFERRED line proposed: scaffold MCP read tools and a `tl scaffold` CLI group (X4 cli_groups hook) | needs orch | raised r1
## DEC-ORCH 2026-11-15 (S1 review 2s)
S1-F2 ruff extend-exclude docs/tickets/*/provided accepted (provided copies are linted where they land)
S1-F3 optional `at` on all scaffold events and the extra optional fields accepted (additive; frozen baseline test)
S1-F4 scaffold reads cur_requisitions_scaffold_request directly: record in phase2-contracts-draft.md §3 As-built (T12)
S1-F5 hidden-IWP test patches _hidden (no confidential IWP exists yet): report says so; real path when IWPs carry classes
T06 size (654 lines, mostly the acceptance script) accepted; its lint block clears once S1 is in p2/i4b
## NEXT
1. Dispatch now: T01 (`provided/T01_test_views.py` -> `packages/tl-modules/scaffold/tests/test_views.py`) and T05a (`provided/T05a_test_scaffold_tagged.py` -> `.../tests/test_scaffold_tagged.py`); disjoint except the exact-set pins T05a edits.
2. After T05a merges: T05b (provided test staged; decide Q3 first). After T01 merges: round 3 writes T09b1 (routes over views.py, five-reader walk: no clearance, cleared, restricted subject, company admin, agent token) and T09b2 (client methods, fakes) from the merged T01 report; check X4 hooks on trunk first (TRAPS).
3. T05b reads `phase2-contracts-draft.md` §1; T10 needs T05b and T07a.
4. After T09b2: T07a (needs T06; settles D11), then T10, T11, T12; DONE round writes `docs/reports/P2-I4B.md` and the AGENTS.md table row.
5. Close: `just check`, whole gate split by package, `just gate-pg` on touched dirs, `just demo P2-I4` (clauses 2, 3, 6 added), SR4.
## REFS
Specs `docs/tickets/P2-I4B/{S1-scaffold-schema-and-lifecycle,T06-toolcrib-screen,T01-read-views,T05a-scaffold-tagged,T05b-labour-requested}.md`; stubs `tl_mod_scaffold/{views,readiness,labour}.py` (bodies raise NotImplementedError); provided tests `docs/tickets/P2-I4B/provided/S1_test_rules.py` (copy to `packages/tl-modules/scaffold/tests/test_rules.py`) `provided/T06_test_toolcrib_text.py` (copy to `packages/tl-tui/tests/test_toolcrib_text.py`), `provided/T01_test_views.py`, `T05a_test_scaffold_tagged.py`, `T05b_test_labour_requested.py` (each linted and type-checked where it lands, then the landing copy removed; the ticket makes the copy; ruff extend-exclude skips `provided/`).
Patterns: `docs/tickets/P2-PUNCH/` (S1 S2, T01 T03 T04 T06), `docs/tickets/P2-I4A/` (T04c1 T04c2 T07a), `packages/tl-modules/quality/`, `tl_mod_awp/readiness/job.py`, `phase2-contracts-draft.md` §3.
Gate paths checked with ls: `packages/tl-schema/tests`, `tests/services/test_modules.py`, `packages/tl-core/tests/auth/test_access_words.py`, `packages/tl-core/tests/test_numbering_config.py`, `packages/tl-tui/tests`; created by items: `packages/tl-modules/scaffold/tests`, `packages/tl-schema/tests/test_scaffold_schema.py`, `packages/tl-tui/tests/test_toolcrib_text.py`.
## TRAPS
Provided tests are formatted and pyright-clean at their landing path before commit; the stubs pass ruff and pyright; fixtures were exercised once (only the stub bodies fail). Scaffold dates come from the real clock: provided tests use fixed far/past days or the row's own `next_due_on`.
X4 (p2/x4, in progress): `ModuleSpec` gains hooks `commands`, `read_routers`, `tools`, `cli_groups` and an `IN_TREE_SURFACES` set. When X4 merges the scaffold module needs its hooks and a set entry (routes, any CLI group): not built now; S1 must not touch `tl_core/modules.py`; a round after X4 C-merge adds a ticket, and T09b1 and T07a registration lines follow whichever form is on the trunk then.
Gates name test files or one package (OOM on 16 GB); the `tests/tools` gate is slow (background); `gate-pg` is slow, name directories; never `pkill -f`; never delete /tmp/pytest-of-root; pinned lists as union.
Commit trailers name the model each agent ran as (session attribution, D-r3e of I4A); reports and files carry no model names.
