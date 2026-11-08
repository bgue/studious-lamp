# P2-I4A STATE  r=2 base=0ae6527 C=0 ck=0 gate=n/a wt=/home/user/wt/p2-i4a
## BOARD   (ws all A; pieces S, tickets T; nothing dispatches before P2-INT C2 is on the trunk and merged here)
S1 p todo f - schema + module spec; spec r2; gate orch P2-Q10
S2 p todo f - engine cmds + subject-class join; spec r2; needs S1; gate orch
S3 p todo f - fulfil, FIFO lots, stock(), shortage constraint; spec at C1; gate orch
S4 p todo f - tests piece at C3
T04a t todo f - read views, viewer=; needs S2
T04f t todo l - labour forecast view, set-filtered; needs T04a
T04c1 t todo f - API reads + word check; needs T04a T04f
T04c2 t todo f - client methods + fakes
T04d t todo f - CLI reads req, wo, forecast
T04e1 t todo f - CLI writes (not fulfil); needs S2
T04e2 t todo f - CLI fulfil; needs S3 T04e1
T07a t todo f - requisition text + log + panel
T07b t todo f - work order backlog screen
T07c t todo f - labour forecast screen
T07d t todo f - TUI glue, palette, technical rows
T08a t todo l - reports (no hire report)
T08b t todo f - MCP reads + propose_requisition; approver orch
T10b t todo f - demo P2-I4 A clauses; grants superuser role
T12 t todo l - docs, runbook
T13 t todo f - registrations if >50 lines
T10a t abn - cut F9
T11 t abn - cut F10
T04c3 t abn - folded into T04c1 F11
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
## SEC
(none yet; SR3 rows in README, one wave review with I5, range 0ae6527..wave 3 head)
## OPEN
Q1 P2-INT C2 on trunk? S1 dispatch waits for it and the trunk merge needs orch raised r1
Q2 closed r2 (intent slot arrives with P2-INT C2; S2 asserts round-trip)
## DEFERRED lines for the orchestrator (do not edit DEFERRED.md here)
1. Constraints whose target is a reference to a record (not the record itself), e.g. a requisition constraint pointing at its subject | needs the ADR-0024 target model extended | wave 3 follow-up
2. Thread `/dispatch` wiring for material-request, labour, crane-lift, general requisitions | W3-4 internal only; T11 cut by plan check F10 | after P1-I7 WS-B is on trunk
3. Moving a requisitions access word to another role per project (data edit through module roles) | S1 drops the module-roles edit, T10b grants superuser (F13) | Phase 3 with module-role editing
## NEXT
1. Orchestrator: merge trunk after P2-INT C2 into p2/i4a; send `13.` with the merge sha.
2. r3 dispatch: S1 alone (human gate P2-Q10, APPROVALS line). S2 after it merges; nothing else is ready.
3. Write S3 spec at C1; T04a, T04f specs once S2 merges.
4. At C2 do registrations (<= 50 lines) else dispatch T13.
5. Round order r4 S3+T04a, r5 T04f+T04c1, r6 T04c2+T04d+T04e1, r7 T07a-c+T08a-b+T04e2, r8 T07d+T10b+S4, r9 T12.
## REFS
Contract draft `docs/build-spec/phase2-contracts-draft.md` §3, §4; module design `module-designs/requisitions-and-scaffold.md`;
patterns `packages/tl-modules/awp`, `materials`; words `schema/settings/access-words.yaml`; format example `docs/tickets/P2-I2/`.
## TRAPS
Gates name test files or one package (OOM on 16 GB); never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union.
