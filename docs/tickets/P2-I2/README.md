# P2-I2 — IWP, constraints, readiness, release sign-off (module M3, part 2)

Status: planning (round 1; plan check requested, nothing dispatched). Plan source: `docs/build-spec/08-phase2-plan.md`
"Increment 2" (re-cut here). Wave order and registries: `docs/build-spec/specs/phase2-wave-plan.md` (wave 2) and
`08-phase2-plan.md` §0.3. Contract: `packages/tl-core/src/tl_core/readiness/types.py` (frozen). Board: `STATE.md`.
Branch `p2/i2`, trunk `claude/wizardly-allen-m2v96s` @34696bc (M3 part 1, M4 and web client wave 1 merged).

## Objective
After this increment the `awp` module holds installation work packages (IWPs): scope items (`awp.ScopeItem`, P2-Q7 A),
pinned documents, constraints with need-by dates and owners, a readiness engine of plug-in checks, release by two-person
sign-off, issue to a foreman, and the `IWP.Ready` webhook. The same state reads over terminal, web twin, API and MCP;
readiness history is in the ledger. `materials_reserved` (shipped by M4) turns `ok` on a real IWP. Out of scope: weekly
cycle, rules of credit, progress, IWP pack, closeout commands (I5); scaffold check (I4-B); permit, ITP and model records
(Phase 3). Each new log ships its web twin in this increment (owner decision 3).

## Owner answers applied
P2-Q2: sign-off and issue are `controller`-word commands; signers hold a role in `awp.release.signoff_roles` (default
`[superuser]`, admin holds all), two distinct persons, the record hash in the signature event, no `roles` guard.
P2-Q6 A: simulated people do `user` acts; the scenario names operators for sign-off and issue. P2-Q7 A: `awp.ScopeItem`
(Planned, Installed, Verified). P2-Q8 A: `permit-to-work` expected link at Issued, reported missing, never blocking.

## Demo clauses (`just demo P2-I2`, SQLite then Postgres; spec of record is `08-phase2-plan.md` I2)
1. IWP from 24 scope items, 8 more and 3 tags, all `contains` links, numbered `P123-IWP-PIP-0042`.
2. Two drawings pinned; a new IFC revision of one makes `documents_current` blocked, stale pin as `resolve_via`.
3. Constraints raised by hand and by the materials check; need-by = planned start - `awp.iwp.ready_lead_weeks`; review
   screen groups by owner and type.
4. Readiness screen shows 5/7 with blocked checks named; re-pin and clear turns 7/7; `IWP.Ready` reaches a loopback receiver.
5. Sign-off: two distinct signers with the P2-Q2 access; a plain user refused; second signer not the first; wrong record
   hash refused.
6. Issue to a foreman: Issued; `permit-to-work` reported missing, not blocking.
7. Oversize IWP (hours over `awp.iwp.size_hours`) warns; the split tool makes two.
8. An agent proposes a constraint; a person accepts it.
9. Same state over API, TUI, web and MCP; readiness history in the ledger; dashboard tile shows backlog weeks per foreman.
Added by wave plan: `materials_reserved` is `ok` on the demo IWP (MTO lines reserved), not only in the M4 demo.

## Workstreams
WS-A (owner of the merge): IWP, scope, constraints, sign-off, issue, hold, CLI, reports, MCP, simulator, demo.
WS-B: readiness engine, checks, readiness and IWP screens, tile. They share this branch and one `STATE.md` (board column
`ws`); the orchestrator alternates rounds. WS-B codes against the frozen contract and `tl_mod_awp.facts.iwp_facts` from S1.

## Pieces (builder, `kind: piece`, review full; spec files `S<n>-<slug>.md`)
| Id | ws | Piece | Spec | Depends | Sec |
|---|---|---|---|---|---|
| S1 | A | Schema part 2: IWP, ScopeItem, Constraint, IWPCloseout (schema only), readiness tables and events (`IWP.ReadinessEvaluated`, `IWP.Ready`), three workflows, numbering, `iwp_facts` reader (plan B1/T01). Human gate | written r1 | wave 1 | schema |
| S2 | A | IWP and scope commands: `CreateIwp`, `RevaiseIwp` fields, scope item create/state, `AddIwpScope`/`RemoveIwpScope`, `PinIwpDocument`, `SplitIwp`, state guards, sizing warning (T02) | r2 | S1 | guards |
| S3 | A | Constraint commands: raise (five sources), assign, clear with `resolves` link, aging, `blocks` link, R-P2-11 suppress (T03) | r2 | S1 | by_module sources |
| S4 | A | `SignOffIwp`, `IssueIwp`, `HoldIwp`, `ReleaseHold` (P2-Q2 access, distinct signers, record hash) (B4); leaves references for T04e, T09a, T09b | r3 | S2, S3, S5 | access words |
| S5 | B | Readiness engine: registry use, job `awp.readiness`, `IWP.ReadinessEvaluated`, `IWP.Ready` on first all-green, projector `cur_awp_readiness`, `request` and `evaluate_now`, re-evaluation requests (T05) | r2 | S1 | job, event |
| S6 | B | Checks `documents_current` and `rfis_answered` through `tl_mod_documents.resolver` and the P1-I6 type (T06a); leaves the reference for T06b | r3 | S5 | - |
| T11 | A | Tests piece at C3: schema, guards, sign-off, engine, five-reader walk of every new route and tool, mutants (sentinel + <=5 per piece) | at C3 | all | - |
Owner policy kept from wave 1: tests deferred to T11; each piece leaves `dev/accept/P2-I2/<id>.py`; tour once at C4.

## Tickets (ticket tier; `review` lite or full; spec files written after the plan check)
| Id | ws | Title | Rev | Depends |
|---|---|---|---|---|
| T04a | A | Read views: IWP, scope, constraint by owner, type, age (provided test) | full | S3, S5 |
| T04c | A | API read routes (IWP, constraints, readiness), `ApiClient` and TUI client methods with fakes | full | T04a |
| T04d | A | CLI reads: `tl awp iwp\|constraint\|readiness ls\|show` (print keys, L-P2-I3-3) | full | T04a |
| T04e | A | CLI writes: iwp, scope, pin, split, constraint, sign-off, issue, hold | full | S4 |
| T04b | A | `constraint_text.py` (Textual-free) + TUI constraint review screen | full | T04c |
| T07a | B | `readiness_text.py` + TUI readiness screen, `resolve_via` jump | full | T04c |
| T07b | B | `iwp_text.py` + IWP log and record tabs (scope, documents, constraints, readiness, history) | full | T04c |
| T08 | B | Sizing warning surface; backlog-weeks-per-foreman tile (`awp.backlog.target_weeks`) | full | T04c, S5 |
| T06b | B | Five `n_a` checks with fixed notes, each with its provided test | lite | S5 |
| T09a | A | Reports and `tl awp report` (status, readiness, constraint log, by type, owner, age) | lite | T04a |
| T09b | A | MCP reads and proposable `propose_constraint`, `propose_iwp_scope` (access `user`, pinned) | full | T04c, S4 |
| TW1 | C | Web twin: IWP log and record page (over T07b text module) | full | T07b |
| TW2 | C | Web twin: constraint review page (over T04b) | full | T04b |
| TW3 | C | Web twin: readiness page and tile (over T07a, T08) | full | T07a, T08 |
| T10a | A | Simulator desk and `workface_planner` actor; operators for sign-off, issue | lite | T09a |
| T10b | A | `dev/demos/P2-I2.sh`, nine clauses plus materials, both adapters | full | T10a, TW1-3 |
| T12 | A | Docs: awp README and AGENTS rows, runbook `iwp-readiness`, reference page | lite | T10b |
Registrations (`AWP_COMMANDS` splat, `MCP_ACTIONS`, `add_typer`, palette) are supervisor glue at C2, <=50 lines; over
that they become one ticket. 7 pieces, 17 tickets: over the ~10-ticket line, so round 2 waits for the plan check.
Every screen ticket needs its text module in the tree first (L-P2-WEB1-1); one web page per twin ticket.

## Order of work and checkpoints
S1 -> (S5 beside S2, S3) -> S4, S6 -> T04a -> T04c -> read, screen and twin tickets -> T06b, T09, T10 -> T11 -> T10b -> T12.
- C1: S1 and S5 merged (WS-B starts after S1). C2: S2, S3, S4, S6, T04a, T04c merged and registrations done.
- C3: every ticket merged or abandoned, T11 merged. C4: full gate per package, demo green on both adapters, tour once,
  SR2 closed or waived by the owner, report.
Merge order: S1, S5, then S2-S4 and S6, then T04c; A owns conflicts; pinned lists are written as the union of both sides.

## Process lessons applied
Gates name test files or one package (the 4-part whole gate OOMs on 16 GB, L-P2-I1-2, L-P2-I3-2); tests are
dialect-neutral (no `group_concat`); provided tests must pass ruff; a test stand-in module never reuses a real module
name; pinned module and command lists are written as the union; review demos and reports only against the final run
(L-P2-I1-3); write options take the key a read prints (L-P2-I3-3); check target-level fixes before a ticket (L-P2-I1-1).

## Security rows (SR2, owner optional)
S3 raise sources and agent-proposed constraints; S4 access words, signer distinctness, record-hash check; S5 job claim and
settle, bounded `resolve_via`; T04c routes (read) and the five-reader confidentiality walk (hidden looks like missing);
T09b agent tools; TW1-3 any web act through `run_command` with the origin check.

## Risks and escalation
Permit target type has no class (S1 escalates if the annotation validator refuses it). On hold returns to Constraint
check, not the prior state (D5). Gap-free numbering for scope items would serialise adds (S1 uses a non-gap-free
pattern, else escalates). Escalate: a frozen contract change; an access word the roles table lacks; a piece failing twice.

## Plan check
(orchestrator's `plan-check` writes here)
