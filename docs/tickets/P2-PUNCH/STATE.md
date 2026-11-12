# P2-PUNCH STATE  r=4 base=bb6f855b C=2 ck=0 gate=n/a wt=/home/user/wt/p2-punch
## BOARD   (r4: S1, S2 merged with APPROVALS; T01 provided test + views stub committed; tickets re-read against S1, S2; `todo` = deps unmet)
S1 p mrg f 7c4ebaa schema + module spec; APPROVALS done
S2 p mrg f 1752551 six commands, subject join, row; APPROVALS done
T01 t mrg f d6f91e0 read views; provided test + stub committed r4; dispatch now
T02 t mrg f df020f8 tl punch group; D28
T03 t mrg f 028128c 3 GET routes + generic door; D28
T05 t mrg f 49dfc6d MCP reads + propose_punch_item
T04 t mrg f fbd1873 client reads + quality_command + fake; D29
T06 t mrg f 166e112 TUI punch log + record screen
T07 t mrg f d82bb60 generator quality section + roster grant + pins; dispatch now
T08 t mrg f f6fb221 demo 7 sq + 6 pg PASS; D30
T09 t mrg l 065713e docs; 2s on wording only (model name, gate coverage); fixed at merge
## DEC
D1 2026-11-11 module `quality`, one record `quality.PunchItem`, table cur_quality_punch_item; README "Record shape"
D2 2026-11-11 states Open, Cleared, Verified, Void; reopen from Cleared or Verified; Void only terminal; assignment is a field; S1
D3 2026-11-11 seven words: quality.view read; punch.raise|edit|clear user; punch.verify|reopen|void controller; no new setting; S1
D4 2026-11-11 verifier differs from clearer (fixed message); raiser is the context actor, never an input; S2
D5 2026-11-11 hidden when the source record is hidden: SUBJECT_LINKS row ported from p2/i4a shape, punch row only; S2 (core gate)
D6 2026-11-11 numbering {project}-PUN-{seq:4}, gap-free; S1
D7 2026-11-11 PROPOSABLE only propose_punch_item; Edit, Clear (direct) and Verify, Reopen, Void (acts) excluded; S2
D8 2026-11-11 offline class draft_only; all events feed_policy none (no core feed change); S1
D9 2026-11-11 writes: API door by T03 (_module_specs), TUI door quality_command by T04; no web files
D10 2026-11-11 routes use guard("document.read") then require_word quality.view (the constraints _view_reader pattern); T03
D11 2026-11-11 tests ride in tickets and pieces; only T01 gets a provided test, committed at r3 once S2 names exist
D12 2026-11-11 Phase 3 compatibility is additive (kind, response_cycle, escalation_level); table in README
D13 2026-11-11 S1 adds tl-mod-quality to the four consumer pyprojects and uv.lock once: no ticket touches uv.lock
D21 2026-11-12 PunchRow gains `id` (record id, for commands, never printed; as IwpRow): T06 and T04 build `punch_item` from it; stub, provided test, T01 updated r4
D22 2026-11-12 today is an ISO string everywhere (`date.today().isoformat()`): views, CLI, route, tool; T01-T05 text updated r4
D23 2026-11-12 demo: rob holds the quality superuser grant as in punch_world (else his verify is `forbidden`, not the clearer rule); README clause setup and T08 fixed
D24 2026-11-12 command field is `from_record_id` (an id); CLI, route door and MCP resolve keys first; T02, T03, T05, T07 say so
D25 2026-11-12 no-view person = account whose roles derive no module role (`World.person(n, ())`); each ticket says to write Blocked if it cannot be made
D26 2026-11-12 T01 provided test `provided/T01_test_views.py` passes ruff + pyright (checked in a temp copy at tests/test_views.py, removed); views.py stub: bodies raise NotImplementedError
## SEC
(none yet; rows in README "Security rows")
## ORCH 2026-11-11 answers
D14 Q5: S1 may add the new event names to the feed-policy list in tl_core/feed/cards.py if a test refuses them (one line); compat baseline update allowed (additive).
D15 Q1: no fixed order with p2/i4a; whichever merges to trunk second unions SUBJECT_LINKS rows and proposable_exclusions.toml.
D16 Q3: T06 uses the generic record-screen action path if it covers clear/verify/reopen; else quality_command plus a form.
D17 Q4: two hops claimed; the three-hop case is a known limit (DEFERRED line at close, with outside review 1 F5).
D27 T07: restricting two existing letters for hidden sources and the WBS depth-3 title as `system` are accepted; anchors test passes at merge
D30 2026-11-11 T08: sue also holds platform role document_controller in the demo (reads the restricted source in clause 5); accepted
D29 2026-11-11 T04 F1: seed_punch has three Open of six (the source-key item is Open); accepted
D28 2026-11-11 no account can lack quality.view (every role derives it): drop that test case in T02 T03 T04; code keeps the check
D20 S2: quality tests keep conftest.py (path widened by orch; the retry that removed it broke collection, reverted)
D19 S1 blk: FROZEN valid-time baseline never grows; new punch events get optional valid-time `at` (Raised, Edited, Reopened, Voided)
D18 Q2: default applied (superuser verifies, never the clearer; verified can reopen); owner told.
## OPEN
(none: Q1-Q5 answered at D14-D18; the three-hop case is a known limit, DEFERRED line at close)
## NEXT
0. (2026-11-12) Whole suite run split: 20 failures, all registries the punch module must join (test_auth_review x2, test_error_table, test_cli_controller_gates, test_offline_capture x2, twin walk x4, webhook catalog + parity, module_role_seams x2, modules_offline x2, tui module_roles_log x2 + command_palette; dispatcher replay = tour clock leak fixed by I4A S5). Order: I4A to trunk first, merge trunk into p2/punch, then one S-piece modelled on docs/tickets/P2-I4A/S5-done-gate-fixes.md with its widened paths. Logs: .gate/dbg.log, .gate/rest*.txt.
1. Orchestrator: dispatch T01 (gate `packages/tl-modules/quality/tests`) and T07 (gate `tests/tools/test_demo_project_quality.py test_demo_project.py test_demo_project_awp.py`); disjoint.
2. r5 after T01 merges: T02, T03, T05 (disjoint folders). r6 T04. r7 T06. r8 T08 (needs T07 too). r9 T09.
3. After each merge `just gen` last, pinned lists as union; read the merged report and re-spec if a named interface moved (PunchRow, PunchDetail, PunchPage, PUNCH_COMMANDS, punch_world.py).
4. Close: `just check`, whole gate, `just gate-pg` on touched dirs (tests/confidentiality, quality tests), `just demo P2-PUNCH`, security rows with the next wave review.
5. DEFERRED lines for the orchestrator: web punch log and record page; walkdown fast-entry screen and `d` key; photo slot; thread target /raise punch; feed cards; Phase 3 Issue engine takeover and inspections; Phase 4 System/Subsystem links and punch-A completion checks; per-project move of a quality word; three-hop subject chain.
## REFS
Plan `docs/tickets/P2-PUNCH/README.md`; pieces S1, S2 (merged); tickets `T01..T09`. Provided test `docs/tickets/P2-PUNCH/provided/T01_test_views.py` (T01 copies it byte-identical to `packages/tl-modules/quality/tests/test_views.py`); interface stub `packages/tl-modules/quality/src/tl_mod_quality/views.py`; test world `packages/tl-modules/quality/tests/punch_world.py` (people ada uma rob sue dora vera; `World.call(who, "RaisePunchItem", ...)`). Reports `docs/reports/P2-PUNCH/S1.md`, `S2.md`. Shape sources (read-only, p2/i4a): `docs/tickets/P2-I4A/`. Patterns on the trunk: `tl_mcp/iwp_tools.py`, `tl_api/routes/constraints.py`, `tl_cli/awp_iwp_write.py`, `dev/demos/P2-I3.sh`.
## TRAPS
Gates name test files or one package (OOM on 16 GB); tests/tools gate about 10 min (background); gate-pg on tests/confidentiality about 26 min; demo-project gates take minutes; never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union; tests dialect-neutral; `uv sync --all-packages` in a fresh worktree before pyright; an IWP is not confidential, so hidden-source tests use a restricted correspondence item made by commands. A fresh worktree needs `uv sync --all-packages` before pyright (done in /home/user/wt/p2-punch r4).
