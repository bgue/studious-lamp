# P2-I5 STATE  r=1 base=ec3314d C=0 ck=0 gate=n/a wt=/home/user/wt/p2-i5
## BOARD   (pieces S, tickets T; nothing dispatched r1)
S1 p todo f - schema, package, words, settings; spec written; gate orch P2-Q10
S2 p todo f - engine, progress cmds, IWP start/complete; spec written; needs S1
S3 p todo f - rollup + CSV export; spec at C1
S4 p todo f - weekly cycle, look-ahead, then waiver + hold rule; spec at C1
S5 p todo f - closeout, hours and subcontract CSV readers; spec at C1
S6 p todo f - tests piece at C3
T01 t todo f - tl awp roc CLI; needs S1
T04 t todo f - look-ahead and week CLI; needs S4
T06a t todo f - TUI cycle steps 1-3; needs T11b
T06b t todo f - TUI cycle steps 4-6; needs T06a
T06c t todo f - IWP log mine/counts/state-since, foreman landing
T07a t todo f - pack renderer, flag for PDF and QR
T07b t todo l - pack template, snapshot test
T08 t todo f - closeout reads + CLI; needs S5
T09 t todo l - seven KPIs + ledger recount test
T10 t todo f - subcontract reads + CLI; needs S5
T11a t todo f - API read routes; needs S2-S5
T11b t todo f - client methods + fakes
T11c t todo f - MCP reads, propose_progress, propose_week_commitment
T12 t todo f - demo, ten clauses
T13 t todo l - docs, three runbooks
T14 t todo l - ForemanDesk and foreman actor
T15 t todo f - registrations only if glue > 50 lines
## DEC
D1 2026-11-08 plan is 6 pieces + 17 tickets (>10): PLANCHK asked, nothing dispatched r1; README
D2 2026-11-08 CLI and TUI only; web twins for cycle, look-ahead, progress, pack, closeout, foreman landing go to the web increment row at close
D3 2026-11-08 P2-Q1 C: sample package co.acme.awp-roc@1.0.0, per-project choice by existing setting awp.rules_of_credit.set; RulesOfCredit is a company record with integer weights summing to 100
D4 2026-11-08 P2-Q11: HTML always; PDF and QR behind setting awp.pack.pdf (default off) and optional extra pack (reportlab, segno); S1 adds both
D5 2026-11-08 P2-Q13 A: CWP assigned_party is free text; interface constraints are core constraints, new ConstraintType Interface; CSV progress; no accounts
D6 2026-11-08 W3-5: WaiveConstraint is a core command, word core.constraint.waive = controller, reason required, own event Constraint.Waived; agents excluded; S4 phase B
D7 2026-11-08 W3-6: foreman is an account role (data, derive = user module roles); TUI landing is T06c, not S1
D8 2026-11-08 W3-7: awp.iwp.ready_lead_weeks already exists, default 4; look-ahead reads it; no change
D9 2026-11-08 hold-on-new-constraint rule (P2-I2 Q1) folded into S4 phase B: follower worker reacts to Constraint.Raised on an Issued or In progress IWP, by_module hold, never inside the raise unit
D10 2026-11-08 ADR-0027: S2 and S4 and S5 each list rows or exclusions; approvals, waiver, closes, verify are excluded with reasons; edits take expected_version
D11 2026-11-08 ADR-0026 F5: at of IWP.Started, FieldCompleted, ProgressRecorded tagged tl:valid_time if the annotation exists; else reported
D12 2026-11-08 deferred, not folded: WBS node workflow/opt-in, automatic constraint population, materials screen gaps, tl awp worker access word; folded: hold rule, P2-I2 IWP log follow-ups (T06c)
D13 2026-11-08 parallel with P2-I4-A: I4-A merges first and owns registry conflicts; I5 merges last and regenerates; seams list in README
## SEC   (SR3 I5 rows in README, run at C4 over ec3314d..head)
(none yet)
## OPEN
Q1 Is P2-INT (intent slot, tl:valid_time annotation) on the trunk before I5 merges? S1 and S2 grep and report needs orch raised r1
Q2 Is six pieces (S4 with two phases) acceptable, or split S4 phase B into a seventh? needs orch raised PLANCHK
Q3 api.public_base_url and ConstraintType Interface are absent today: S1 adds both (settings gate) needs orch raised r1
Q4 tests/tools/proposable_exclusions.toml absent on this base: S2 reports; P2-INT or I4-A creates it needs orch raised r1
## NEXT
1. Orchestrator: plan-check README.md, paste findings under `## Plan check`, send `13.` with answers.
2. Round 2: dispatch S1 alone (human gate P2-Q10, APPROVALS line at merge); T01 spec after S1.
3. At C1 (S1, S2 merged) write S3, S4, S5 specs; they run in parallel with disjoint handlers.
4. After S2 and S4 reads exist: T11a, then T11b; screens and CLI after.
5. At C2 do registrations (<= 50 lines) else T15. Pinned lists: union, regenerate after I4-A merges.
6. At close add the web-pages line to DEFERRED.md (not now).
## REFS
Plan source `docs/build-spec/08-phase2-plan.md` Increment 5; module design `module-designs/field-work-packaging.md`; format example `docs/tickets/P2-I2/`; parallel plan on `p2/i4a:docs/tickets/P2-I4A/README.md`.
Patterns: rollup `packages/tl-modules/awp/src/tl_mod_awp/rollup.py`; readiness views `readiness/views.py` (`visible_readiness`); look-ahead `tl_mod_schedule/lookahead.py`; envelope `tl_core/derivation/envelope.py`; constraints `tl_core/constraints/`.
## TRAPS
Gates name test files or one package (OOM on 16 GB); never pkill -f; never delete /tmp/pytest-of-root; pinned lists as union; a check name used twice is an error; tests dialect-neutral (no group_concat).
