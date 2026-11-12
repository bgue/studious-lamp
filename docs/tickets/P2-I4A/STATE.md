# P2-I4A STATE  r=3 base=06cfd204 C=1 ck=1 gate=pass wt=/home/user/wt/p2-i4a
## BOARD   (C1 and S2 merged; trimmed per owner 2026-11-09 row 4b; specs staged r3; `dfr` = deferred, roadmap 3c)
S1 p mrg f 010b695 schema + module spec
S2 p mrg f 43a94d5 engine cmds + subject-class join
S3 p dfr f - roadmap 3c (fulfil, FIFO, stock(), shortage)
S4 p dfr f - roadmap 3c; each ticket carries its tests
T04a t mrg f 63b5e3a read views; D-r3c
T04e1 t mrg f 87307ee CLI writes; D-r3a D-r3b
T04d t mrg f bf0ad8d CLI reads; D-r3d
T04c1 t mrg f 931992c API reads + word check
T04c2 t mrg f eb8778b client methods + fakes
T07a t mrg f 1198a97 requisition text, log, page
T07b t mrg f 7f2876f work order backlog
T07d t mrg f a9a14fc TUI glue; item 4 deferred D-r3f
T08b t mrg f 78a134e MCP reads + propose_requisition
T10b t mrg f 6eac974 demo P2-I4 both backends PASS (orch run); D-r3i
T12 t mrg l 6b6b248 docs; review F2 F3 checked false (handler, widget bindings)
S5 p mrg f 44feb42 whole suite green (7 split sessions); review P (nit F1 -> PUNCH piece)
T04f t dfr l - roadmap 3c labour forecast
T07c t dfr f - roadmap 3c forecast screen
T08a t dfr l - roadmap 3c reports
T04e2 t dfr f - roadmap 3c CLI fulfil
T13 t abn - folded: tickets own registration lines
T10a T11 T04c3 t abn - cut r2 (F9 F10 F11)
## DEC
D1 2026-11-08 r2: plan check F1-F13 all accepted; 4 pieces + 16 tickets, ~10 points; README "Plan check"
D2 2026-11-08 CLI and TUI only; web twins deferred to the web increment; README
D3 2026-11-08 W3-1: one word per command; approve, reject, schedule, assign, close = controller; rest user; single approve word, no chain (F4); S1
D4 2026-11-08 WorkOrder workflow gains initial Open so ScheduleWorkOrder is a move (accepted); S1
D5 2026-11-08 requisition states after Approved follow its work order (module-driven moves); S2
D6 2026-11-08 W3-4 internal only: T11 cut, no correspondence coupling (F10); README
D7 2026-11-08 ADR-0027: propose_requisition row; approve, reject, schedule, close and owner-direct field acts excluded; S2
D8 2026-11-08 F6: untagged classes into tests/tools/valid_time_baseline.toml with reason; StartWorkOrder optional `at`; S1, S2
D9 2026-11-08 F7: WO opts in on start (phase start); shortage constraint subject WO, target requisition; no requisition opt-in; S1, S3
D10 2026-11-08 F1: requisition inherits subject class via hidden_sql generic part (S2 allowed tl_core/confidentiality.py); api reads take viewer=
D11 2026-11-08 F2/F3: Fulfil also checks materials.move; S3 adds materials stock() and FIFO by received date; gate orch, APPROVALS
D12 2026-11-08 F5: merge trunk after P2-INT C2 before S1; S2 asserts intent round-trips
D13 2026-11-08 F8: WO events on the WO's own stream; contract §3 updated by S1
D14 2026-11-08 F13: no module-roles edit in S1; T10b grants superuser; SR3 is one wave review with I5
D15 2026-11-08 class names keep contract spelling (LaborRequisition); user words say labour
D16 2026-11-09 owner row 4b: I4-A trimmed; S3 T04e2 T04f T07c T08a S4 `dfr`; one DEFERRED.md line added; README "Trim"
D17 2026-11-11 r3: 11 tickets, 7 waves; T13 folded into tickets; tests ride in tickets (S4 dfr); only T04a has a provided test
D18 2026-11-11 r3: CLI surface fixed in T04e1: req raise-labor|material|general|scaffold, edit, approve, reject, cancel; wo schedule|assign|start|complete|close; T04d adds ls, show
D19 2026-11-11 r3: T08b writes requisition_tools.py on the iwp_tools pattern; PROPOSABLE row exists (S2), not edited; T10b lists each clause's verb
D20 2026-11-11 r3: provided/ test changes state by commands only; hidden subject cannot be made by a command (IWP not confidential): not claimed (Q5)
D-r3e 2026-11-11 orch: commit trailers name the model each agent ran as (session attribution); accepted; reports carry no model names
D-r3g 2026-11-11 demo pins crane_lift in its own schema copy via TL_SCHEMA_DIR; no shared fixture change
D-r3i 2026-11-11 T10b review F1: driver sub-check lines also read `PASS clause 4:`; accepted, nothing counts them
D-r3h 2026-11-11 demo drops the view-word refusal (no account lacks read); MCP word check to DEFERRED
## SEC
(none yet; SR3 rows in README, one wave review with I5)
## OPEN
Q1 closed (trunk merged @06cfd204)
Q5 hidden-subject reads (IWP restricted by a command) untestable until an IWP can be confidential; only the viewer= default and word checks are tested | needs orch | raised r3
Q6 requisitions.view is `read`: T04c1 confirms the route word check maps; T08b uses guarded like iwp_tools | needs builder | raised r3
## DEFERRED lines for the orchestrator (the trim line is in DEFERRED.md; these are the older three, not yet added)
1. Constraints whose target is a reference to a record | needs the ADR-0024 target model | wave 3 follow-up
2. Thread `/dispatch` wiring for requisitions | W3-4 internal only; T11 cut | after P1-I7 WS-B
3. Per-project move of a requisitions access word | S1 drops the module-roles edit | Phase 3
## DEC-ORCH
D-o1 2026-11-08 C2 taken from p2/int @9700d54 (holds trunk @4fff675) instead of waiting for P2-INT on the trunk; P2-INT T02-T05 come with it later
## OPEN-ORCH
Q-o1 feed cards for Requisition.Approved/.Rejected and WorkOrder.Completed need POLICY_EVENT_TYPES in tl_core/feed/cards.py (S2 or a core ticket)
Q-o2 docs/reference/access-words.md and docs/build-spec/specs/offline-classes.md not updated (Haiku docs ticket)
Q-o3 contract §3: say Raised payload is flat and Revised carries changes {field: [old, new]} (review F1 LO)
Q-o4 ModuleSpec declaration for subject links to replace SUBJECT_LINKS (needs tl_core/modules.py; core ticket)
## NEXT
0. (2026-11-12) Slice ended at 35%. Next slice: full reviewer on p2/i4a-s5-done-fixes (wt /home/user/wt/i4a/s5, .gate/summary.txt PASS), merge, gate-pg on touched dirs, SR3 with I5 (D14), trunk merge with SUBJECT_LINKS + proposable_exclusions union (D15). Run the whole gate split: one session at a time, tl-api alone, tl-sim and tl-tui apart (part sessions above 12 GB die).
1. Orchestrator: dispatch wave 1 (T04a, T04e1); T04a gets its provided test copied byte-identical.
2. After T04a merges: wave 2 T04c1, T04d (also needs T04e1), T08b.
3. Then T04c2; T07a with T07b; T07d; T10b; T12. Supervisor r4 refines staged tickets from merged reports (names marked in them).
4. Close: `just check`, whole gate, `just gate-pg` on touched dirs, `just demo P2-I4`, SR3 with I5.
## REFS
Tickets `docs/tickets/P2-I4A/T*.md`; provided test `docs/tickets/P2-I4A/provided/T04a_test_views.py`; world helper `packages/tl-modules/requisitions/tests/req_world.py`; patterns `docs/tickets/P2-I2/` (T04a T04c1 T04c2 T04d T04e1 T07b T07c T09b T10b); `tl_mcp/iwp_tools.py`; reports `docs/reports/P2-I4A/S1.md S2.md`.
Candidate learning: a hidden-subject test needs a confidential IWP; Q-o1..Q-o4 below still stand (Q-o2, Q-o3 go to T12).
## TRAPS
Gates name test files or one package (OOM on 16 GB); `tests/tools` gate takes ~10 min (background); gate-pg on tests/confidentiality ~26 min; never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union.
