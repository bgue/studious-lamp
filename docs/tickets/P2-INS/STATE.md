# P2-INS STATE  r=1 base=0ae6527 C=0 ck=0 gate=n/a wt=/home/user/wt/p2-ins
## BOARD   <id> <t|p> <todo|stg|disp|pass|mrg|abn|2s|gr|blk> <l|f> <sha|-> <note, <= 8 words>
S1 p stg f - INS-A1 Activity read, route, client; hold for wave 2 merge
S2 p stg f - INS-B1+T1 Checks read, telemetry table, note_need; schema gate
T01 t todo l - INS-A2 record_activity_text.py; needs S1 merged
T02 t todo f - INS-A3 Activity tab, owns record_view.py, key 9 stub
T03 t todo f - INS-B2 Insights tab, Checks list, three unmet subtabs
T04 t todo f - INS-A4+B5 twin tests; needs S1, S2
## DEC     D<n> <date> <one line: what, why, where recorded>
D1 2026-11-08 Activity pages by outbox seq (before_seq), not recorded_at: stable key; S1 spec
D2 2026-11-08 Link events where record is the to-end found by subject_id IN + stream_id IN (no stream_id index); S1
D3 2026-11-08 Check sources are module functions per package, assembled once in tl_api/insights_sources.py; route and embedded share it; S2
D4 2026-11-08 Related hop: 6 cause relations, 6 event types, caps 100 far ends, 30 rows, 1000 candidates; S1
D5 2026-11-08 note_need route: 204, 30 per 10 min per actor, agent refused, role from token; screen rows carry record_type only; S2
D6 2026-11-08 T02 owns record_view.py and creates the Insights stub pane and key 9; T03 never edits it (plan check F9)
D7 2026-11-08 Intent why absent on base: Why column drops out, no why-open line; no skipped test written for it (T04)
D8 2026-11-08 Stale pins, orphan links, data health, log marker, panel line stay roadmap item 1 (F4)
## SEC     F<n> <HI|MD|LO> <fixed@sha|open> <one line>
S-A scope row: Activity related-hop filter (S1); S-B: Checks resolve_via and detail (S2); S-C: note_need route (S2). No findings yet.
## OPEN    Q<n> <question> needs <orch|owner|builder> raised <id>
Q1 APPROVALS: one schema line (schema/core/telemetry.yaml + setting telemetry.retention_days) and one interface line (activity, checks, note_need, 3 routes) needs orch raised r1
Q2 No just demo P2-INS ticket in the 2 S + 4 H budget; add a Haiku demo ticket or accept tour + accept scripts needs orch raised r1
Q3 Owner question I-Q5 (screen-opened telemetry notes record type only, one per session): default as built needs owner raised r1
Q4 After wave 2 merge: rebase p2/ins onto trunk or keep p2/wave2-close base; wave 2 fixes may touch constraints/readiness views needs orch raised r1
## NEXT
1. Orchestrator: confirm wave 2 merge, answer Q1 Q2 Q4, then dispatch S1 and S2 in one workflow (batch of 2, disjoint paths).
2. After S1 and S2 merge and APPROVALS are written: round 2 re-reads merged code, refreshes T01 to T04 pasted blocks, runs the section 6 checklist.
3. Round 2 dispatches T01 and T04; round 3 T02; round 4 T03.
4. DONE: whole gate, gate-pg on touched dirs, security review S-A to S-C, tour rows, report (<= 80 lines).
## REFS
Plan `docs/tickets/P2-INS/README.md`; specs S1, S2; tickets T01 to T04 (drafts). Spec `docs/build-spec/specs/insights-and-activity.md`; ADR-0028 plan check. Owner words `/home/user/wt/OWNER-2026-11-07-insights.md`. No stubs or held tests committed yet (contracts are pasted in S1; tests are built by the pieces).
## TRAPS
Docs-only round: just check and gates not run (ck0 means not run). outbox_events has no stream_id index. Shared client files (client.py, embedded.py, remote.py, fakes.py, app.py) are touched by both pieces: append-only conflicts. Never pkill -f; never delete /tmp/pytest-of-root.
