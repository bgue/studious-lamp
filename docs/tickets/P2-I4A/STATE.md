# P2-I4A STATE  r=1 base=0ae6527 C=0 ck=0 gate=n/a wt=/home/user/wt/p2-i4a
## BOARD   (ws all A; pieces S, tickets T)
S1 p todo f - schema + module spec; spec written; gate orch P2-Q10
S2 p todo f - engine commands; spec written; needs S1
S3 p todo f - fulfilment into I3, labour forecast; spec at C1
S4 p todo f - tests piece at C3
T04a t todo f - read views; needs S2
T04c1 t todo f - API read routes; needs T04a S3
T04c2 t todo f - client methods + fakes
T04c3 t todo f - route word check before read
T04d t todo f - CLI reads req, wo, forecast
T04e t todo f - CLI writes
T07a t todo f - requisition text + log + panel
T07b t todo f - work order backlog screen
T07c t todo f - labour forecast screen
T07d t todo f - TUI glue, palette, technical rows
T08a t todo l - reports
T08b t todo f - MCP reads + propose_requisition
T10a t todo l - simulator desk + requisition_clerk
T11 t todo f - thread /dispatch wiring or deferred note
T10b t todo f - dev/demos/P2-I4.sh A clauses
T12 t todo l - docs, runbook
T13 t todo f - registrations if >50 lines
## DEC
D1 2026-11-08 plan is 4 pieces + 17 tickets (>10): PLANCHK asked, nothing dispatched r1; README
D2 2026-11-08 CLI and TUI only; web twins (log, backlog, forecast, create form) deferred to web increment; README
D3 2026-11-08 W3-1: one access word per command; approve, reject, schedule, assign, close = controller word; raise, edit, cancel, start, complete, fulfil = user; movable by data; S1 spec
D4 2026-11-08 WorkOrder workflow gains initial Open (Open > Scheduled > In progress > Done > Closed; Cancelled) so ScheduleWorkOrder is a move; asked of plan check
D5 2026-11-08 requisition states after Approved follow its work order by module-driven moves; S2 spec
D6 2026-11-08 W3-4: labour requisitions internal only; no correspondence coupling; README
D7 2026-11-08 ADR-0027: each command is a ProposableCommand row or in proposable_exclusions.toml; approve, reject, schedule, close excluded; S2 spec
D8 2026-11-08 ADR-0026 F5: WorkOrder.Started and .Completed carry tl:valid_time at; S1 spec
D9 2026-11-08 ADR-0024: Requisition and WorkOrder opt in to constraints (S1); shortage raises one from S3; clear-on-state rules deferred
D10 2026-11-08 class names keep contract spelling (LaborRequisition); user-facing words say labour
## SEC
(none yet; SR3 rows in README, run at C4 over 0ae6527..head)
## OPEN
Q1 WorkOrder initial state Open (D4) and requisition-follows-WO moves (D5): confirm or change needs orch raised PLANCHK
Q2 Is the ADR-0025 intent slot on the trunk at wave 2 close? S2 greps; base has ADR proposed only needs orch raised r1
Q3 T04e/T11: is the P1-I7 /dispatch parser on the trunk? T11 checks needs builder raised r1
## NEXT
1. Orchestrator: run plan-check on README.md, paste findings under `## Plan check`, send `13.` with answers.
2. Round 2: dispatch S1 (human gate P2-Q10, APPROVALS line at merge) alone; nothing else is ready.
3. At C1 write S3 spec; then T04a, T04c1 specs once S2 is merged.
4. At C2 do registrations (<= 50 lines) else dispatch T13.
5. Add the web twins line to DEFERRED.md at close (not now).
## REFS
Contract draft `docs/build-spec/phase2-contracts-draft.md` §3 (base) and §4 (materials api); module design
`docs/build-spec/module-designs/requisitions-and-scaffold.md`; patterns: `packages/tl-modules/awp`, `materials`;
access words `schema/settings/access-words.yaml`; format example `docs/tickets/P2-I2/`.
## TRAPS
Gates name test files or one package (OOM on 16 GB); never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union.
