# P2-I2 STATE  r=5 base=8b6c393 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i2
## BOARD   (ws A=IWP/constraints/sign-off, B=readiness+screens+web twins; col 6 starts with ws)
S1 p mrg f - A schema part 2 (APPROVALS done)
S2 p mrg f - A IWP+scope cmds; constraint half replaced by C1/C2
T06b t mrg l - B five n_a checks
T06a3 t mrg f 0b78f86 B pin resolver by link ids (waived report 63 lines)
C1 p mrg f 945d126 A core constraint schema; APPROVALS @237149e
C2 p mrg f df08fb6 A core constraint cmds; ADR-0024 accepted, APPROVALS @8b6c393
S3 p mrg f aff0765 A sign-off, issue, hold; APPROVALS @9b3e672
S4 p disp f - B readiness engine + ADR-0028 addendum @6392bac; SKIPs till C2
T06a1 t mrg f f607aec B documents_current (waived: cb619ea subject)
T06a2 t mrg f 9098b51 B rfis_answered
S5 p todo f - A tests at C3; adds CheckResult twin hidden vs missing pin
T04a t disp f - A IWP + scope read views (awp iwp_views.py); wf r5
T04a2 t disp f - A core constraint owner filter + review_groups (split from T04a, D24); wf r5
T04c1 t stg f - A API routes (dep T04a T04a2 S4); spec staged; D20-22 + view word copied in
T04c2 t todo f - A client methods + fakes (dep T04c1)
T04d t todo f - A CLI reads + core tl constraint ls/show (dep T04a S4)
T04e t todo f - A CLI writes; split at spec: T04e1 awp iwp writes, T04e2 tl constraint writes (dep T04a)
T04b t todo f - A constraint_text + screen + per-record log (dep T04c2)
T07a t todo f - B readiness_text + screen (dep T04c2)
T07b t todo f - B iwp_text + log + tabs (dep T04c2)
T08 t todo f - B sizing surface + backlog tile (dep T04c2 S4)
T09a t todo l - A reports (dep T04a S4)
T09b t todo f - A MCP reads + proposals (dep T04c2 C2)
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
## SEC   (none yet; rows in README "Security rows"; SR2 mandatory at C4, range 34696bc..p2/i2 head, <=450k)
## OPEN
Q1 hold-on-new-constraint rule (brief: a new constraint on an Issued IWP puts it On hold) has no owner; in DEFERRED; needs orch raised r3.
## NEXT
1. Orch: dispatch ONE workflow T04a + T04a2 (disjoint: awp / core constraints; wts t04a, t04a2). With S4 running and P2-SEED: 3 heavy slots.
2. After S4 merges: rerun dev/accept/P2-I2/S4.py (SKIPs need C2); APPROVALS line for S4's confidentiality.py change (trivial merge with C2's hidden_sql part: keep both).
3. r6: refine and dispatch T04c1 (staged; needs S4 report for the readiness read), beside T04d spec (add the view-word line, D25) and T04e1/T04e2 (need T04a; core commands run via core registry, see C2 report).
4. C2 glue (<=50 lines, after S4 merge): AWP_COMMANDS splat for S3 (check), MCP_ACTIONS, add_typer (`tl constraint`: T04d and T04e2 own one module each, glue adds both lines), palette, readiness hook line from the S4 report.
5. P2-SEED follow-up (branch p2/seed, do not edit): awp generator section seeds core constraints; orch adds a ticket line.
6. Then T04c2 -> T04b, T07a, T07b, T08 (screens) ; T09a/T09b; C3: S5 (five-reader walk, guard and class-join mutants, D22 twin) beside T10b. C4: gate per package, demo both adapters, tour once, SR2 mandatory, report.
## REFS
Staged: T04c1-api-read-routes.md (tentative paths). Contract: packages/tl-core/src/tl_core/readiness/types.py (frozen), harness.py. ADR docs/adr/0024-constraints-on-any-record.md (v2), 0025 (later). Specs: C1, C2, S3, S4 in this folder; S2 constraint code reference: git show d2409f5:packages/tl-modules/awp/src/tl_mod_awp/constraints.py.
Template check: packages/tl-modules/materials/src/tl_mod_materials/readiness.py. Owner answers: docs/build-spec/module-designs/OWNER-DECISIONS-2026-10-30.md. README is the spec of record.
T06a3 spec: docs/tickets/P2-I2/T06a3-pin-resolver.md. Seed ledger .accept/p2-i2.db is regenerated by C2's script.
## TRAPS
Whole 4-part gate OOMs on 16 GB (L-P2-I1-2, L-P2-I3-2): gate names files or one package. Tests dialect-neutral, no group_concat;
provided tests pass ruff; stand-in module never reuses a real module name; pinned lists as union (removals in C1: exact numbers). A check name used twice is an error.
documents/correspondence/awp pyproject entry-point tables are new: tickets may touch only that table. C1 and S3 both edit awp commands.py/module.py/names.py: append at list ends.
