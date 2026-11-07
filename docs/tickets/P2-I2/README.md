# P2-I2 — IWP, constraints, readiness, release sign-off (module M3, part 2)

Status: plan re-cut r2 after the plan check (5 pieces, 20 tickets); S1 dispatched alone. Plan source: `docs/build-spec/08-phase2-plan.md`
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
1. IWP from 24 scope items, 8 more and 3 tags, all `contains` links, numbered `P123-IWP-PIP-<seq:4>` (first is 0001; no allocator start exists, D8).
2. Two drawings pinned; a new IFC revision of one makes `documents_current` blocked, stale pin as `resolve_via`.
3. Constraints raised by hand and by the materials check; need-by = planned start - `awp.iwp.ready_lead_weeks`; review
   screen groups by owner and type.
4. Readiness screen shows 7/9 with blocked checks named (`documents_current`, `constraints_cleared`; `n_a` counts as passing, D9); re-pin and clear turns 9/9; `IWP.Ready` reaches a loopback receiver.
5. Sign-off: two distinct signers with the P2-Q2 access; a plain user refused; second signer not the first; wrong record
   hash refused.
6. Issue to a foreman: Issued; `permit to work` reported missing (class-level `tl:expects_link`, no workflow guard), not blocking.
7. Oversize IWP (hours over `awp.iwp.size_hours`) warns; the split tool makes two.
8. An agent proposes a constraint; a person accepts it.
9. Same state over API, TUI, web and MCP; readiness history in the ledger; dashboard tile shows backlog weeks per foreman.
Added by wave plan: `materials_reserved` is `ok` on the demo IWP: T10b assigns MTO lines to the `awp.IWP` key (`work_package_id`, types already accepted), then reserves.

## Workstreams
WS-A (owner of the merge): IWP, scope, constraints, sign-off, issue, hold, CLI, reports, MCP, simulator, demo.
WS-B (now also the web twins, F14): readiness engine, checks, readiness and IWP screens, tile, TW1-3. Two streams only. They
share this branch and one `STATE.md` (board column `ws`); the orchestrator alternates rounds. WS-B codes against the frozen
contract and `tl_mod_awp.facts.iwp_facts` from S1.

## Pieces (builder, `kind: piece`, review full; spec files `S<n>-<slug>.md`)
| Id | ws | Piece | Spec | Depends | Sec |
|---|---|---|---|---|---|
| S1 | A | Schema part 2: IWP, ScopeItem, Constraint, IWPCloseout (schema only), readiness tables and events, three workflows, numbering, class-level permit `tl:expects_link`, `iwp_facts`. Human gate: orchestrator (P2-Q10) | written, r2 fixed | wave 1 | schema |
| S2 | A | IWP, scope and constraint commands (old S2+S3, F5): `CreateIwp`, scope item create, `AddIwpScope`/`RemoveIwpScope`, `PinIwpDocument`, `SplitIwp`, state guards, sizing warning, constraint raise (five sources), assign, clear with `resolves` link, aging, `blocks` link, R-P2-11 suppress. Owns `module.py`, `names.py`, `AWP_COMMANDS` edits | r2 | S1 | guards, by_module sources |
| S3 | A | `SignOffIwp`, `IssueIwp`, `HoldIwp`, `ReleaseHold` (P2-Q2 access, distinct signers, record hash). Signer-role check is permission code: orchestrator gate (P2-Q10) | r3 | S2, S4 | access words |
| S4 | B | Readiness engine in `tl_mod_awp/readiness/` only: registry use, job `awp.readiness`, `IWP.ReadinessEvaluated`, `IWP.Ready`, projector `cur_awp_readiness`, `request`, `evaluate_now`; Constraint check <-> Ready moves; check-source constraints through S2's raise (F6); check `constraints_cleared` (F4); event-to-IWP mapping by `work_package_id` for watched types, else `evaluate_now` (F3). Hook line in `module.py` is C2 glue (F5) | r3 | S1, S2 | job, event |
| S5 | A | Tests piece (old T11, F14, F15): schema, guards, sign-off, engine, five-reader walk of every new route and tool, mutants (sentinel + <=5 per piece). Runs beside T10b | at C3 | all pieces, T04c2 | - |
Owner policy kept from wave 1: tests deferred to S5; each piece leaves `dev/accept/P2-I2/<id>.py`; tour once at C4.

## Tickets (ticket tier; `review` lite or full; spec files written when their dependencies are in the tree)
| Id | ws | Title | Rev | Depends |
|---|---|---|---|---|
| T04a | A | Read views: IWP, scope, constraint by owner, type, age (provided test) | full | S2 |
| T04c1 | A | API read routes (IWP, constraints, readiness), embedded and remote | full | T04a, S4 |
| T04c2 | A | `ApiClient` and TUI client methods with fakes | full | T04c1 |
| T04d | A | CLI reads: `tl awp iwp\|constraint\|readiness ls\|show` (print keys, L-P2-I3-3) | full | T04a, S4 |
| T04e | A | CLI writes: iwp, scope, pin, split, constraint, sign-off, issue, hold | full | S3 |
| T04b | A | `constraint_text.py` (Textual-free) + TUI constraint review screen | full | T04c2 |
| T07a | B | `readiness_text.py` + TUI readiness screen, `resolve_via` jump | full | T04c2 |
| T07b | B | `iwp_text.py` + IWP log and record tabs (scope, documents, constraints, readiness, history) | full | T04c2 |
| T08 | B | Sizing warning surface; backlog-weeks-per-foreman tile (`awp.backlog.target_weeks`) | full | T04c2, S4 |
| T06a1 | B | Check `documents_current` in `tl_mod_documents` (F7: awp may not import it) | full | S1, S2 |
| T06a2 | B | Check `rfis_answered` in `tl_mod_correspondence` (F7) | full | S1, S2 |
| T06b | B | Five `n_a` checks in `tl_mod_awp` with fixed notes (contract only, F9) | lite | S1 |
| T09a | A | Reports and `tl awp report` (status, readiness, constraint log, by type, owner, age) | lite | T04a, S4 |
| T09b | A | MCP reads and proposable `propose_constraint`, `propose_iwp_scope` (access `user`, pinned) | full | T04c2, S2 |
| TW1 | B | Web twin: IWP log and record page (over T07b text module) | full | T07b |
| TW2 | B | Web twin: constraint review page (over T04b) | full | T04b |
| TW3 | B | Web twin: readiness page and tile (over T07a, T08) | full | T07a, T08 |
| T10a | A | Simulator desk and `workface_planner` actor; operators for sign-off, issue | lite | T09a |
| T10b | A | `dev/demos/P2-I2.sh`, nine clauses plus materials, both adapters | full | T10a, TW1-3, S3 |
| T12 | A | Docs: awp README and AGENTS rows, runbook `iwp-readiness`, reference page | lite | T10b |
Registrations (`AWP_COMMANDS` splat, `MCP_ACTIONS`, `add_typer`, palette, readiness hook line) are supervisor glue at C2,
<=50 lines; over that they become one ticket. 5 pieces, 20 tickets (the checker's ~19 plus the T06a split). Every screen
ticket needs its text module in the tree first (L-P2-WEB1-1); one web page per twin ticket.

## Order of work and checkpoints
S1 -> S2 (T06b beside S1) -> S4 (T06a1, T06a2, T04a beside) -> S3 -> T04c1 -> T04c2 -> read, screen and twin tickets -> T09, T10a -> T10b beside S5 -> T12.
- C1: S1 merged (WS-B starts after S1). C2: S2, S3, S4, T06a1, T06a2, T04a, T04c1 merged and registrations done.
- C3: every ticket merged or abandoned, S5 merged. C4: full gate per package, demo green on both adapters, tour once,
  SR2 closed (mandatory, F11), report.
Merge order: S1, S2, S4, S3, then T04c1; A owns conflicts; pinned lists are written as the union of both sides.

## Process lessons applied
Gates name test files or one package (the 4-part whole gate OOMs on 16 GB, L-P2-I1-2, L-P2-I3-2); tests are
dialect-neutral (no `group_concat`); provided tests must pass ruff; a test stand-in module never reuses a real module
name; pinned module and command lists are written as the union; review demos and reports only against the final run
(L-P2-I1-3); write options take the key a read prints (L-P2-I3-3); check target-level fixes before a ticket (L-P2-I1-1).

## Security rows (SR2, mandatory at C4)
SR2 scope: the rows below only, commit range `34696bc..p2/i2` head, <= 450k tokens, findings `F<n> <HI|MD|LO> file:line`.
S2 raise sources and agent-proposed constraints; S3 access words, signer distinctness, record-hash check; S4 job claim and
settle, bounded `resolve_via`; T04c1 routes (read) and the five-reader confidentiality walk (hidden looks like missing);
T09b agent tools; TW1-3 any web act through `run_command` with the origin check. Gates: S1 schema and S3 signer-role
checks are the orchestrator's under P2-Q10 (APPROVALS line at merge).

## Risks and escalation
The permit target type has no class: reserved name `permit.PermitToWork`, D8 (S1 escalates if the validator refuses it). On hold returns to Constraint
check, not the prior state (D5). Gap-free numbering for scope items would serialise adds (S1 uses a non-gap-free
pattern, else escalates). Escalate: a frozen contract change; an access word the roles table lacks; a piece failing twice.

## Plan check
Planner-tier check, 2026-11-07 (pasted by the orchestrator; the checker does not edit files). Every finding is to be
answered below it in round 2 (accepted with the change made, or waived with a reason).

```
4 PLANCHK docs/tickets/P2-I2/README.md
F1 HI S1 IWP workflow: an expected_links entry is a guard (definition.py L13), so it would block Issue against P2-Q8 A -> put tl:expects_link (by_state Issued) on the IWP class in iwp.yaml, add no guard
F2 HI S1/STATE Q2: expected.py has no check on target_type, so the permit STOP never fires -> close Q2 and record the reserved name permit.PermitToWork as a DEC for Phase 3
F3 HI seam materials_reserved: reservations are StockLot events and MTO lines point to the IWP by a work_package_id column, not a link. Materials never calls request -> S5 maps watched events to IWPs by work_package_id, else evaluate_now. T10b assigns lines to an awp.IWP key, then reserves
F4 HI scope demo 4: clearing constraints moves 5/7 to 7/7, but no constraints check exists. Checks are 3 real + 5 n_a = 8 -> S5 adds constraints_cleared and says how n_a counts. Fix the demo numbers
F5 MD seams: S2, S3 and S5 run in parallel and all edit tl_mod_awp module.py, names.py and AWP_COMMANDS with no owner -> merge S2+S3 into one piece. S5 stays in readiness/ and its hook line is C2 glue
F6 MD seams: nobody owns the Constraint check<->Ready moves or the check-source constraints in demo 3 -> S5 job does both through by_module and calls S3's raise
F7 MD tiers S6: a check plugin on the frozen contract (precedent P2-I3-T03) -> two t full tickets, depending on S1+S2 not S5. Ship them from documents and correspondence: the contract bars awp importing tl_mod_documents
F8 MD tiers T04c: routes for 3 resources + ApiClient + client.py, embedded, remote, fake + tests is over 5 files, failing 01-tiers §6 item 4 -> split into T04c1 routes and T04c2 client methods with fakes
F9 MD deps: T04a needs S2 (IWP projector), not S5. T04c and T09a need S5 views. T09b needs S3, not S4. T06b needs only the contract -> fix the table. Dispatch T06b in r2
F10 MD gates: S4 signer-role check is permission code (AGENTS never-list) and has no human gate. S1 approver says "owner, or" -> both gates go to the orchestrator under P2-Q10, with an APPROVALS line
F11 MD gates: SR2 is "owner optional" with no commit range, against skill rule 4 -> make it mandatory at C4, scoped to the Sec rows and 34696bc..p2/i2 head, at most 450k tokens
F12 MD S1 gate: one run covers two packages (OOM trap). Pinned lists such as tests/services/test_modules.py, tests/webhooks/scenario.py, test_ddl.py and test_generate.py are not run -> run one package per gate and name those files
F13 LO scope S2: the I2 demo never uses scope-item state moves; RevaiseIwp is a typo and is not in the plan -> leave the moves to I5. Write ReviseIwp only if the demo needs it
F14 LO waves: T11 runs before T10b although their paths do not overlap. Stream C is a third stream (0.2 allows two) -> run T11 beside T10b and fold the twins into WS-B. Demo 0042 needs a gap-free seed or start, named in S1
F15 LO cost: about 10 rounds, 7p/17t, roughly 0.28-0.35 B, at the top of the band. Cost drivers are T11 (split it per stream), S2/S3 (merge them as in F5) and S6 (make it tickets as in F7). Result is 5p/19t
73 Contract use is sound: the registry, harness and settings keys are on trunk; TW twins over text modules; Q2/Q6/Q7 applied correctly; readiness schema folded into one S1 gate (D6)
30
```

### Answers (round 2)
F1 accepted: permit expectation is `tl:expects_link` on `awp.IWP` (by_state Issued); the workflow carries no `expected_links` guard; S1 text fixed.
F2 accepted: Q2 closed; reserved name `permit.PermitToWork` recorded as D8 for Phase 3; S1 acceptance checks the annotation.
F3 accepted: S4 maps watched types to IWPs by `work_package_id` (materials already accepts IWP keys), else `evaluate_now`; T10b assigns MTO lines to an IWP key before reserving.
F4 accepted: S4 adds `constraints_cleared` (9 checks: 4 real, 5 `n_a`); `n_a` counts as passing; demo is 7/9 then 9/9 (D9).
F5 accepted: S2 and S3 merged into one piece (new S2); S4 stays in `readiness/`, its hook line is C2 glue.
F6 accepted: S4's job makes the Constraint check <-> Ready moves and the check-source constraints through S2's raise; S4 depends on S2.
F7 accepted: S6 becomes T06a1 (documents) and T06a2 (correspondence), both `t full`, depending on S1 and S2, staged.
F8 accepted: T04c split into T04c1 (routes) and T04c2 (client methods with fakes).
F9 accepted: T04a needs S2; T04c1, T04d, T09a need S4; T09b needs S2 (not sign-off); T06b needs S1 only (contract); T06b dispatched r2.
F10 accepted: S1 approver and S3 signer-role gate are "orchestrator (P2-Q10)", APPROVALS line at merge.
F11 accepted: SR2 mandatory at C4, Sec rows only, `34696bc..p2/i2` head, <= 450k.
F12 accepted: S1 gates one package per run and names the pinned-list files.
F13 accepted: scope-item state moves left to I5; no `ReviseIwp` or `RevaiseIwp` command in S2 unless the demo needs a field change (it does not).
F14 accepted: S5 (tests) runs beside T10b; twins folded into WS-B (two streams); 0042 cannot be seeded (no allocator start; `reserved` is per pattern), clause 1 says first is 0001 (D8).
F15 partly waived: S2+S3 merged, S6 made tickets, T11 renamed S5; the per-stream split of the tests piece is waived (one cold start reads both streams once; S5 stays one piece, two ordered phases), giving 5p/20t.
