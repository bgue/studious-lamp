# P2-I4B STATE  r=4 base=485b85b5 C=1 ck=- gate=n/a wt=/home/user/wt/p2-i4b
## BOARD   (S1 = plan B4; `todo` ready to dispatch, `stg` staged)
S1 p mrg f 256d9014 C1; findings dec by orch; APPROVALS
T06 t mrg f 1c3e1294 review P; F2 ctrl+i is Tab -> T07a (D11)
T01 t mrg f f6bf1990 review P
T05a t mrg f 7e1651ce review P; amend 1; rename test_nine_checks later
T05b t mrg f de6ff369 review P; amend 1+2 (seed labour reqs)
T09a t mrg f fcbb52e0 review P
T09b1 t mrg f 49ab7045 review P
T09b2 t mrg f 7480bded review P
T07a t mrg f f4b66174 review P
T07b t mrg f 3fc897e2 review P
T09c t mrg f cb1e81ef review P
T11a t mrg f 9d5237e5 review P; 1 scaffold (Designed)
T12 t mrg l d1484534 esc settled amend 1
T10a t mrg f 863b91a3 review P; stale echo fix in T10b
T10b t stg f - demo clause 7 toolcrib; after T10a
T11b t stg l - tour shots 13-15; after T11a
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
D13 2026-11-15 r3: scaffold commands are not in the API door and no CLI group exists (X4 hook not on trunk), so T09a splats SCAFFOLD_COMMANDS into tl_api/commands.py (pre-hook form, as quality); T09b1 adds routes/scaffold.py and one app.py line; both move into module.py hooks when X4 C2 reaches trunk (later ticket); T09a, T09b1
D14 2026-11-15 r3: T09b1 also serves GET scaffold-export (csv|jsonl over views.export_rows) so the owner export rule is reachable without a CLI; T09b2 adds client export_scaffolds; T09b1
D15 2026-11-15 r3: plan T07a split: T07a = toolcrib keys (F2 issue, F3 return, Ctrl+R kept; app-level F2/F3 panel toggles lose to the modal) + palette entry; T07b = scaffold register and record screens; D6 registration stays with T07a/T07b (one owner of app.py/commands.py per ticket, sequential); T07a, T07b
D16 2026-11-15 r3: `just demo P2-I2` failure (awp.worker.run word) does not touch this DONE demo: T10 clause 3 runs job scaffold.inspections_due in-process (JobRunner, as dev/accept/P2-I4B/S1.py), never `tl awp run`; no fix ticket; T10
D17 2026-11-15 r4: demo clause numbers 5 (plan 2), 6 (plan 3), 7 (plan 6) follow A's 1-4; IWP "closes" = Cancelled via `tl awp iwp cancel` (Closed needs signoffs); IWP to Issued by by_module TransitionWorkflow in the driver; scaffold commands over the API door; new driver `dev/demos/p2_i4b_demo.py` (A's driver untouched); T10a
D18 2026-11-15 r4: T09c added (T09a Q): scaffold errors map to 422 scaffold_error, scaffold_scope, scaffold_rule; 409 scaffold_state, scaffold_dismantle_refused, scaffold_stale_version; plan 10 -> 14 items (T09c, T10 split a/b, T11 split a/b), still pieces=1; no PLANCHK (items are small, one batch per seam)
D19 2026-11-15 r4: P200 has 4 scaffold requisitions and no scaffolds, so the tour needs data: T11a adds a demo-project section with no `requires` links (IWP readiness unchanged); T11b the shots
## SEC
(none yet; T09a Q (500 on a domain refusal) -> T09c; SR4 rows: S1 confidentiality part (hidden IWP hides its scaffold and the dismantle text), green-tag word, dismantle guard; T09b1 five-reader walk; one wave review)
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
1. Orch: merge T09c, T11a, T12 when passed (T12 and T11a touch disjoint paths; no known conflicts).
2. Round 5: dispatch T10a (needs T09c), T11b (needs T11a), then T10b (needs T10a; same script and driver, sequential).
3. DONE round after all merged: `docs/reports/P2-I4B.md` (<=80 lines), root AGENTS.md table row (scaffold: module, runbook, API, TUI, demo, tour), learnings, README status; `88`.
4. Close gates (orch): `just check`; whole gate split by package; `just gate-pg` on packages/tl-modules/scaffold/tests packages/tl-api/tests/test_api_scaffold_commands.py tests/api/test_client_scaffold.py; `just demo P2-I4`; `just tour phase2`; SR4 (S1 confidentiality, green-tag word, dismantle guard, T09b1 five-reader walk).
5. X4 C2 on trunk (still not at r4): ticket to move command splat and router line into module.py hooks; MCP tools and `tl scaffold` stay DEFERRED (Q2).
6. Open from reports (decide at DONE, no ticket now): T07b register_page tuple shape accepted as built; T09b2 non-empty due list in client tests not added (T09b1 and fakes cover it); T05b/T05a rename test_nine_checks later.
## REFS
Specs `docs/tickets/P2-I4B/{S1-scaffold-schema-and-lifecycle,T06-toolcrib-screen,T01-read-views,T05a-scaffold-tagged,T05b-labour-requested}.md`; stubs `tl_mod_scaffold/{views,readiness,labour}.py` (bodies raise NotImplementedError); provided tests `docs/tickets/P2-I4B/provided/S1_test_rules.py` (copy to `packages/tl-modules/scaffold/tests/test_rules.py`) `provided/T06_test_toolcrib_text.py` (copy to `packages/tl-tui/tests/test_toolcrib_text.py`), `provided/T01_test_views.py`, `T05a_test_scaffold_tagged.py`, `T05b_test_labour_requested.py` (each linted and type-checked where it lands, then the landing copy removed; the ticket makes the copy; ruff extend-exclude skips `provided/`).
Round 4 specs `T09c-scaffold-error-rows`, `T11a-demo-project-scaffold-section`, `T12-docs`, staged `T10a-demo-scaffold-clauses`, `T10b-demo-toolcrib-clause`, `T11b-tour-scaffold-toolcrib` (all under `docs/tickets/P2-I4B/`). Gate paths (ls checked): `packages/tl-api/tests/{test_error_table,test_api_scaffold_commands,test_openapi_baseline}.py`, `tests/tools/test_demo_project{,_quality}.py`; demos and tour: `TL_DEMO_BACKENDS=sqlite just demo P2-I4`, `just tour phase2 /tmp/phase2-tour` (background).
Round 3 specs `T09a-command-door`, `T09b1-api-read-routes`, `T09b2-client-methods`, `T07a-toolcrib-keys-and-nav`, `T07b-scaffold-screens` (all under `docs/tickets/P2-I4B/`; no provided tests: the tickets copy the punch tests' shape).
Patterns: `docs/tickets/P2-PUNCH/` (S1 S2, T01 T03 T04 T06), `docs/tickets/P2-I4A/` (T04c1 T04c2 T07a), `packages/tl-modules/quality/`, `tl_mod_awp/readiness/job.py`, `phase2-contracts-draft.md` §3.
Gate paths checked with ls: `packages/tl-schema/tests`, `tests/services/test_modules.py`, `packages/tl-core/tests/auth/test_access_words.py`, `packages/tl-core/tests/test_numbering_config.py`, `packages/tl-tui/tests`; created by items: `packages/tl-modules/scaffold/tests`, `packages/tl-schema/tests/test_scaffold_schema.py`, `packages/tl-tui/tests/test_toolcrib_text.py`.
## TRAPS
Provided tests are formatted and pyright-clean at their landing path before commit; the stubs pass ruff and pyright; fixtures were exercised once (only the stub bodies fail). Scaffold dates come from the real clock: provided tests use fixed far/past days or the row's own `next_due_on`.
X4 (p2/x4: S1, S3, T01 merged there; not on trunk, C2 waits X2 C2; checked r3): `ModuleSpec` gains hooks `commands`, `read_routers`, `tools`, `cli_groups` and an `IN_TREE_SURFACES` set. When X4 merges the scaffold module needs its hooks and a set entry (routes, any CLI group): not built now; S1 must not touch `tl_core/modules.py`; a round after X4 C-merge adds a ticket, and T09b1 and T07a registration lines follow whichever form is on the trunk then.
Gates name test files or one package (OOM on 16 GB); the `tests/tools` gate is slow (background); `gate-pg` is slow, name directories; never `pkill -f`; never delete /tmp/pytest-of-root; pinned lists as union.
Commit trailers name the model each agent ran as (session attribution, D-r3e of I4A); reports and files carry no model names.
