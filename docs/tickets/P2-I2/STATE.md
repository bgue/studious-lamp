# P2-I2 STATE  r=8 base=c8c0e20 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i2
## BOARD   (ws A=IWP/constraints/sign-off, B=readiness+screens+web twins; col 6 starts with ws)
S1 p mrg f - A schema part 2 (APPROVALS done)
S2 p mrg f - A IWP+scope cmds; constraint half replaced by C1/C2
T06b t mrg l - B five n_a checks
T06a3 t mrg f 0b78f86 B pin resolver by link ids (waived report 63 lines)
C1 p mrg f 945d126 A core constraint schema; APPROVALS @237149e
C2 p mrg f df08fb6 A core constraint cmds; ADR-0024 accepted, APPROVALS @8b6c393
S3 p mrg f aff0765 A sign-off, issue, hold; APPROVALS @9b3e672
S4 p mrg f 5f6dc29 B readiness engine; fix round merged, APPROVALS @65b803d; S4.py ok
T06a1 t mrg f f607aec B documents_current (waived: cb619ea subject)
T06a2 t mrg f 9098b51 B rfis_answered
S5 p stg f - A tests piece spec r6; twin D26, F3 note, 5 mutants
T04a t mrg f a486da0 A IWP + scope views (subject fix not applied; accepted)
T04a2 t mrg f 9bb01f6 A core owner filter + review_groups; merged @4b5805b
T04c1 t disp f - A API read routes; builder retry running (D32, subject_key)
T04c2 t stg f - A client methods + fakes; spec r8, after T04c1
T04d t mrg f 02f8d50 A iwp+constraint CLI reads; merged @d4cbb23
T04e1 t mrg f 2bbcba4 A awp iwp writes CLI; merged @b2054c3 (LO _cwp_id copy accepted)
T04e2 t mrg f 70c0b00 A tl constraint writes CLI; merged @c8c0e20
T04d2 t stg f - A readiness CLI; blk on gap, respec r8 on visible_readiness, after T04c1
T04g t stg f - A glue: groups, T04d2 register, hook line (dep T04d T04e1 T04e2; T04d2 optional)
T04b t stg f - A constraint_text + screen + per-record log; spec r8, after T04c2
T07a t stg f - B readiness_text + screen; spec r8, after T04c2
T07b t stg f - B iwp_text + log + IWP screen (no tabs, D33); spec r8, after T04c2
T08 t stg f - B backlog weeks + sizing screen (D34); spec r8, after T04c2
T09a t disp l - A six IWP/constraint reports in awp_report; spec r8, dispatched
T09b t stg f - A 7 read tools + 2 proposals; spec r8, after T04c1 (not T04c2)
T07c t todo f - B glue: IWP screen keys to readiness and constraint log, nav, palette (dep T04b T07a T07b)
TW1 t todo f - B web IWP log+record (dep T07b)
TW2 t todo f - B web constraint review (dep T04b)
TW3 t todo f - B web readiness+tile (dep T07a T08)
T10a t todo l - A sim desk + actor (dep T09a)
T10b t todo f - A demo P2-I2 (dep T10a TW1-3 S3; clause 3 seeds constraints)
T12 t todo l - A docs (dep T10b)
## DEC
D1 2026-11-07 owner defaults applied: Q6 A operators, Q7 A awp.ScopeItem, Q8 A expected link missing not blocking, signoff_roles [superuser]; README
D2 2026-11-07 sign-off, issue, hold are controller-word commands, signers checked against awp.release.signoff_roles, never a roles guard; README
D3 2026-11-07 r2 plan re-cut after plan check: 5 pieces (S1 S2 S3 S4 S5) + 20 tickets; old S2+S3 merged, S6 became T06a1/a2, T04c split, T11 became S5; README
D4 2026-11-07 no loaders ticket: demo builds the 24+8+3 scope by commands; README
D5 2026-11-07 On hold returns to Constraint check (no prior-state memory); S1 spec
D6 2026-11-07 readiness tables and IWP.Ready/ReadinessEvaluated schema live in S1 (one schema gate); S4 owns only code; S1 spec
D7 2026-11-07 one branch p2/i2 and one STATE.md for both streams; twins folded into WS-B (two streams only); README
D8 2026-11-07 permit target is reserved name permit.PermitToWork, class-level tl:expects_link at Issued, no workflow guard; Phase 3 adds the class. No allocator start exists: demo says first IWP is 0001; S1, README
D9 2026-11-07 9 checks (documents_current, rfis_answered, materials_reserved, constraints_cleared, 5 n_a); n_a counts as passing; demo 7/9 then 9/9; README
D10 2026-11-07 labour_requested n_a here is replaced by I4-B T05's real check (same name is an error): that ticket deletes the entry; T06b
D11 2026-11-07 access words added by S2: awp.iwp.edit user, awp.constraint.edit user; S3 adds signoff, issue, hold words (controller); S2 spec
D12 2026-11-07 S1 schema gate and S3 signer-role gate are the orchestrator's (P2-Q10), APPROVALS line at merge (F10); README
D13 2026-11-07 materials seam: MTO lines point to IWP by work_package_id (types accepted); S4 maps watched events by it, else evaluate_now; T10b assigns lines to an IWP key first (F3)
D14 2026-11-07 F15 partly waived: tests piece stays one piece (two phases), not split per stream; README
D15 2026-11-07 owner parts A/B: constraints are core records (ADR-0024 v2, plan-checked, all accepted); pieces C1 schema, C2 commands; awp keeps none; effort 5p+2 core pieces
D16 2026-11-07 frozen functions raise_constraint, clear_constraint, open_blocking in ADR-0024 decision 6 and stub tl_core/constraints/__init__.py (NotImplementedError until C2); S4 codes against them
D17 2026-11-07 C1 deletes awp constraint code (tree stays green); C2 moves it from d2409f5 with iwp_id->subject_id; owner optional for non-manual sources (ADR v2)
D18 2026-11-07 IWP opt-in on transition `ready`, phase `ready`; WBS opt-in deferred (docs/build-spec/DEFERRED.md); ADR-0025 intent slot lands after the wave 2 close, not in P2-I2
D19 2026-11-07 orch (ADR-0026 F1): envelope effective_at is capture time only; ADR-0024 s4 and C2 spec drop 'cleared_at also event effective_at'; fields live in payload+row
D20 2026-11-07 orch 9 F1 HI (ADR-0028 PLANCHK): S4 addendum @6392bac (awp.IWP into SCANNED_STREAM_TYPES; ids only in resolve_via; no record text in detail; twin line); T04c1 read drops hidden ids
D21 2026-11-07 orch: new ticket T06a3 (resolver filtered by link ids): documents_current resolved the whole scope (~4 stmts per link, pins past 1000 dropped = false blocked); fixes it in resolver.py + readiness.py
D22 2026-11-07 orch: S5 adds whole-CheckResult twin test, hidden vs missing pinned document (T06a1 F5)
D23 2026-11-07 waived LO: C1 core workflow ~47 lines vs 30 cap; T06a1 cb619ea subject, report 61 lines (orch)
D24 2026-11-07 r5: T04a split by package: T04a (awp iwp_views.py, IWP+scope) and T04a2 (core constraints owner filter + review_groups); one ticket may not touch two public interfaces
D25 2026-11-07 orch r5 b: first constraint read surface enforces core.constraint.view (VIEW_WORD, read): T04c1 first, T04d and T09b repeat it at their entry; queries.py stays word-free (entry points check)
D26 2026-11-07 orch r5 c: S5 keeps the whole-CheckResult hidden-vs-missing pinned-document twin (D22); T04c1 route body twin run once in its acceptance
D27 2026-11-07 r6: T04d split: iwp+constraint reads now, readiness verbs T04d2 after S4 (needs its read name); each CLI module exposes register(app), glue T04g (own spec) makes groups, so T04d/e1/e2 run in parallel with no shared file
D28 2026-11-07 r6: AWP_COMMANDS already carries S3 (api registry splats it); MCP_ACTIONS goes with T09b, palette with screen tickets; glue T04g = awp.py, constraint.py, main.py, module.py hook (S4 report line), pins
D29 2026-11-07 r7: T04c1 names fixed from S4 report: `readiness.views.readiness(conn,scope,key)` (None = missing/hidden/never evaluated, one 404); route drops facts_hash; no project-wide readiness route; constraint word check is a guard dependency
D30 2026-11-07 r7: T04d2 module `awp_readiness_read.register(awp_app)` adds the `readiness` group itself (not under iwp); readiness hook lines for glue: S4 report "Facts for the glue"
D31 2026-11-07 r7: S4 report open items kept for S5/later: F3 raw requeue UPDATE (a tl_core.jobs requeue API), change during a running job not requeued, per-viewer redaction of a hidden-blocker ReadinessEvaluated event deferred (orch logs)
D32 2026-11-07 orch r8: `visible_readiness(conn, scope, key, viewer)` in awp readiness/views.py: refs filtered by viewer in one batch, visible refs carry display keys; check state and counts as evaluated (REVISES D20-22 "counts visible only"); constraint groups `truncated: true` past MAX_LIMIT; T04c1 retry, T04d2 and T09b use it
D33 2026-11-07 r8: T07b has no Ready/Constraints columns and no tabs (IwpRow lacks the counts, no read per row); T07c wires IWP screen keys to the readiness screen and constraint log after T04b, T07a, T07b; list-level counts are a follow-up read
D34 2026-11-07 r8: backlog weeks = sum of ceil(days inclusive/7) over a foreman's Ready and Issued IWPs vs awp.backlog.target_weeks; undated adds 0; sizing = hours outside awp.iwp.size_hours; T08
D35 2026-11-07 r8: T09a extends `tl awp report` (awp_report.py) with six names, no new registration; iwp_readiness prints check names and states only (no refs, no counts)
D36 2026-11-07 r8: T04c1 rows and detail owe `subject_key`, `subject_type` (ConstraintView has only subject_id); noted in its Decision; T04c2 stops if absent
## SEC   (none yet; rows in README "Security rows"; SR2 mandatory at C4, range 34696bc..p2/i2 head, <=450k)
## OPEN
Q1 hold-on-new-constraint rule (brief: a new constraint on an Issued IWP puts it On hold) has no owner; in DEFERRED; needs orch raised r3.
## NEXT
1. Orch: dispatch T09a now (alone; wt i2/t09a). T04c1 builder retry runs (heavy slot 1).
2. On T04c1 merge: T04c2, T04d2 (respec'd), T09b (disjoint paths; one workflow of up to 3, or T04c2 + T04d2 first).
3. After T04c2: T04b, T07a, T07b, T08 in parallel by path (screens; each a full review). Then T07c glue, TW1-3.
4. r9: T04g after T04d2 merges (needs register of awp_readiness_read); T10a after T09a; S5 phase 1 spec check; write T07c, TW1-3 specs once text modules merge.
5. P2-SEED follow-up (branch p2/seed, do not edit): awp generator seeds core constraints; orch adds a ticket line.
6. C3: S5 beside T10b. C4: gate per package, demo both adapters, tour once, SR2 mandatory, report.
7. Capacity: weekly 80%, slice to 90%; new dispatch stops at 89%.
## WAVE2 REMAINS FOR DONE  (H=Haiku ticket, B=builder piece; deps in brackets)
H T04c1 API routes [builder retry] | H T04d2 readiness CLI [T04c1] | H T04g glue [T04d T04e1 T04e2 merged; waits T04d2] | H T04c2 client+fakes [T04c1]
H T04b constraint_text+screen+log [T04c2] | H T07a readiness_text+screen [T04c2] | H T07b iwp_text+log+tabs [T04c2] | H T08 sizing+backlog tile [T04c2]
H TW1 web IWP [T07b] | H TW2 web constraints [T04b] | H TW3 web readiness+tile [T07a T08] (web twins are in plan, D7; each: one page over the text module)
H T09a reports lite [ready now: T04a, S4 merged] | H T09b MCP reads+proposals [T04c2, C2; Haiku only with tool names and access words given in the ticket, else B]
H T10a sim desk+actor lite [T09a] | H T10b demo script P2-I2.sh [T10a TW1-3 S3; heavy, split if over 5 files] | H T12 docs lite [T10b]
B S5 tests piece [all of T04d/e1/e2/g, T04c1 merged; runs beside T10b] | per-folder run = C4 gate per package + demo + tour (orch)
Critical chain: T04c1 -> T04c2 -> T07b -> TW1 -> T10b -> T12. Parallel now: T04c1, T04d2, T09a (3 slots, one workflow each at most 3 items).
## REFS
Staged r8: T04c2, T04b, T07a, T07b, T08, T09b (specs in this folder), T09a (dispatched), T04d2 respec'd, T04g, S5-tests.md (r6). Contract: packages/tl-core/src/tl_core/readiness/types.py (frozen), harness.py. ADR docs/adr/0024-constraints-on-any-record.md (v2), 0025 (later). Specs: C1, C2, S3, S4 in this folder; S2 constraint code reference: git show d2409f5:packages/tl-modules/awp/src/tl_mod_awp/constraints.py.
Template check: packages/tl-modules/materials/src/tl_mod_materials/readiness.py. Owner answers: docs/build-spec/module-designs/OWNER-DECISIONS-2026-10-30.md. README is the spec of record.
T06a3 spec: docs/tickets/P2-I2/T06a3-pin-resolver.md. Seed ledger .accept/p2-i2.db is regenerated by C2's script.
## TRAPS
Whole 4-part gate OOMs on 16 GB (L-P2-I1-2, L-P2-I3-2): gate names files or one package. Tests dialect-neutral, no group_concat;
provided tests pass ruff; stand-in module never reuses a real module name; pinned lists as union (removals in C1: exact numbers). A check name used twice is an error.
documents/correspondence/awp pyproject entry-point tables are new: tickets may touch only that table. C1 and S3 both edit awp commands.py/module.py/names.py: append at list ends.
