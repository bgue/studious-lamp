# P2-I2 STATE  r=1 base=34696bc C=0 ck=0 gate=n/a wt=/home/user/wt/p2-i2
## BOARD   (ws A=IWP/constraints/sign-off, B=readiness, C=web twins)
S1 p todo f - A schema part 2 + iwp_facts; spec written; human gate
S2 p todo f - A IWP + scope commands; spec r2 (dep S1)
S3 p todo f - A constraint commands; spec r2 (dep S1)
S4 p todo f - A sign-off, issue, hold; spec r3 (dep S2 S3 S5)
S5 p todo f - B readiness engine, job, projector; spec r2 (dep S1)
S6 p todo f - B documents_current, rfis_answered; spec r3 (dep S5)
T04a t todo f - A read views (dep S3 S5)
T04c t todo f - A API reads + client methods + fakes (dep T04a)
T04d t todo f - A CLI reads (dep T04a)
T04e t todo f - A CLI writes (dep S4)
T04b t todo f - A constraint_text + TUI screen (dep T04c)
T07a t todo f - B readiness_text + screen (dep T04c)
T07b t todo f - B iwp_text + log + tabs (dep T04c)
T08 t todo f - B sizing surface + backlog tile (dep T04c S5)
T06b t todo l - B five n_a checks (dep S5)
T09a t todo l - A reports (dep T04a)
T09b t todo f - A MCP reads + proposals (dep T04c S4)
TW1 t todo f - C web IWP log + record (dep T07b)
TW2 t todo f - C web constraint review (dep T04b)
TW3 t todo f - C web readiness + tile (dep T07a T08)
T10a t todo l - A sim desk + actor (dep T09a)
T10b t todo f - A demo P2-I2 (dep T10a TW1-3)
T11 p todo f - A tests piece at C3
T12 t todo l - A docs (dep T10b)
## DEC
D1 2026-11-07 owner defaults applied: Q6 A operators, Q7 A awp.ScopeItem, Q8 A expected link missing not blocking, signoff_roles [superuser]; README
D2 2026-11-07 sign-off, issue, hold are controller-word commands, signers checked against awp.release.signoff_roles, never a roles guard; README
D3 2026-11-07 plan re-cut: 7 pieces + 17 tickets (plan said 6 pieces, 15); added T04d/e CLI, T11, TW1-3, T12; registrations are glue at C2; README
D4 2026-11-07 no loaders ticket: demo builds the 24+8+3 scope by commands; README
D5 2026-11-07 On hold returns to Constraint check (no prior-state memory); S1 spec
D6 2026-11-07 readiness tables and IWP.Ready/ReadinessEvaluated schema live in S1 (one schema gate); S5 owns only code; S1 spec
D7 2026-11-07 one branch p2/i2 and one STATE.md for both streams (board col ws); README
## SEC   (none yet; rows in README "Security rows")
## OPEN
Q1 plan has 17 tickets: planner-tier check before dispatch needs orch (skill rule 8) raised r1
Q2 permit-to-work target type has no class; S1 stops if validator refuses needs builder raised S1
## NEXT
1. Orch: plan-check agent writes findings under README "## Plan check"; answer or waive each.
2. r2: write S2, S3, S5 specs; dispatch S1 alone first (schema gate), then S5 beside S2/S3 after S1 merges.
3. r2: commit provided references the next batch needs (none yet); check iwp_facts landed.
4. r3: S4, S6 specs; after S1+S5 merge dispatch T04a; later T04c, then screens, twins, reports.
5. C2 glue (<=50 lines): AWP_COMMANDS splat, MCP_ACTIONS, add_typer, palette; run pinned-list tests.
6. C3: T11 tests piece; five-reader walk on every new route and tool.
7. C4: gate per package (L-P2-I2 below), demo both adapters, tour once, SR2, report from this file.
## REFS
Contract docs/build-spec/specs: readiness types at packages/tl-core/src/tl_core/readiness/types.py (frozen); pipeline
signatures in its trailing comment. materials check: packages/tl-modules/materials/src/tl_mod_materials/readiness.py.
Settings awp.* already in schema/settings/platform.yaml. Piece spec template: docs/tickets/P2-I1/S2-awp-schema.md.
Owner answers: docs/build-spec/module-designs/OWNER-DECISIONS-2026-10-30.md. No spec file m3-iwp exists; README is it.
## TRAPS
Whole 4-part gate OOMs on 16 GB (L-P2-I1-2, L-P2-I3-2): gate names files or one package. Tests dialect-neutral, no
group_concat; provided tests pass ruff; stand-in test module never reuses a real module name; pinned lists as union.
