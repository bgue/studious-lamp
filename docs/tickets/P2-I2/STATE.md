# P2-I2 STATE  r=2 base=34696bc C=0 ck=0 gate=n/a wt=/home/user/wt/p2-i2
## BOARD   (ws A=IWP/constraints/sign-off, B=readiness+screens+web twins; col 6 starts with ws)
S1 p disp f - A schema part 2; human gate orch P2-Q10
S2 p stg f - A IWP+scope+constraint cmds; spec r2 (dep S1)
S4 p todo f - B readiness engine; spec r3 (dep S1 S2)
S3 p todo f - A sign-off, issue, hold; spec r3 (dep S2 S4)
S5 p todo f - A tests piece at C3; beside T10b
T06b t stg l - B five n_a checks (dep S1)
T06a1 t stg f - B documents_current in documents (dep S1 S2)
T06a2 t stg f - B rfis_answered in correspondence (dep S1 S2)
T04a t todo f - A read views (dep S2)
T04c1 t todo f - A API read routes (dep T04a S4)
T04c2 t todo f - A client methods + fakes (dep T04c1)
T04d t todo f - A CLI reads (dep T04a S4)
T04e t todo f - A CLI writes (dep S3)
T04b t todo f - A constraint_text + screen (dep T04c2)
T07a t todo f - B readiness_text + screen (dep T04c2)
T07b t todo f - B iwp_text + log + tabs (dep T04c2)
T08 t todo f - B sizing surface + backlog tile (dep T04c2 S4)
T09a t todo l - A reports (dep T04a S4)
T09b t todo f - A MCP reads + proposals (dep T04c2 S2)
TW1 t todo f - B web IWP log+record (dep T07b)
TW2 t todo f - B web constraint review (dep T04b)
TW3 t todo f - B web readiness+tile (dep T07a T08)
T10a t todo l - A sim desk + actor (dep T09a)
T10b t todo f - A demo P2-I2 (dep T10a TW1-3 S3)
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
## SEC   (none yet; rows in README "Security rows"; SR2 mandatory at C4, range 34696bc..p2/i2 head, <=450k)
## OPEN
Q2 closed r2 (D8). Q1 closed r2 (plan check done).
## NEXT
1. Orch: merge S1 (gates: schema + signer-role are orch under P2-Q10, APPROVALS line); then spawn r3.
2. r3: verify S1 on log; write S4 spec (needs S2 merged first) and S3 spec later; dispatch S2 + T06b (disjoint paths).
3. r3: after S2 merges write T04a ticket; dispatch T06a1, T06a2 beside S4 (check qualifies on S1 + S2).
4. Later: S3 (after S2 + S4), T04c1 -> T04c2, then screens, twins, reports (D13 seam in S4 spec).
5. C2 glue (<=50 lines): AWP_COMMANDS splat, MCP_ACTIONS, add_typer, palette, readiness hook line; pinned-list tests.
6. C3: S5 tests piece (five-reader walk on every new route and tool), beside T10b.
7. C4: gate per package, demo both adapters, tour once, SR2 (mandatory), report from this file.
## REFS
Contract: packages/tl-core/src/tl_core/readiness/types.py (frozen), harness.py. Template check: packages/tl-modules/materials/src/tl_mod_materials/readiness.py.
Piece spec template: docs/tickets/P2-I1/S4-awp-cwp-packages-actions.md. Specs written: S1, S2 (staged); tickets staged: T06b, T06a1, T06a2.
Settings awp.* on trunk. Owner answers: docs/build-spec/module-designs/OWNER-DECISIONS-2026-10-30.md. README is the spec of record (no m3-iwp spec).
## TRAPS
Whole 4-part gate OOMs on 16 GB (L-P2-I1-2, L-P2-I3-2): gate names files or one package. Tests dialect-neutral, no group_concat;
provided tests pass ruff; stand-in module never reuses a real module name; pinned lists as union. A check name used twice is an error.
documents/correspondence/awp pyproject entry-point tables are new: tickets may touch only that table.
