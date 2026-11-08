# P2-I4-A — Requisitions and work orders (module M9, part 1), CLI and TUI only

Status: round-1 plan, waiting for the planner-tier check (`4 PLANCHK`). 4 pieces, 17 tickets (over the ~10-ticket line, so
nothing is dispatched in round 1; S1 and S2 specs are written ahead). Plan sources: `docs/build-spec/08-phase2-plan.md`
"Increment 4" (A column), `specs/phase2-wave-plan.md` (wave 3), `module-designs/requisitions-and-scaffold.md`,
`phase2-contracts-draft.md` §3, `roadmap-2026-11-07.md` (item 4, W3-1, W3-4, P2-Q13). Board: `STATE.md`.
Branch `p2/i4a` from `p2/wave2-close` @0ae6527 (P2-I2 merged). Worktree `/home/user/wt/p2-i4a`.

## Objective
After this increment a new module `requisitions` (package `tl-mod-requisitions`) holds the generic request-to-work-order
engine and its four specialisations: labour, material, general (type psets such as a crane lift) and scaffold request.
A person raises a requisition linked to an IWP or CWP; an approver approves or rejects it with a reason; approval opens a
work order that is scheduled, assigned, started, completed and closed; a material requisition is fulfilled by issuing stock
through the I3 movement commands, with partial fulfilment and a shortage constraint raised on the requisition; labour
requisitions give a forecast by craft and week. Numbering is gap-free per kind. State reads over CLI, TUI, API and MCP;
nothing here needs the scaffold module (I4-B) or the web.
Out of scope: scaffold asset, inspections, tag colour, the two readiness checks, toolcrib (I4-B, wave 4); every web page
(deferred, below); union-hall or subcontractor requisitions as formal correspondence (W3-4: internal only, a General
correspondence item is linked by hand); permits; hire billing.

## Owner answers applied (2026-11-08)
W3-1: one access word per command in `schema/settings/access-words.yaml`; the approving and scheduling words map to the table
word `controller` (module superuser), raise, edit, cancel, start, complete and fulfil map to `user`; a project can later
move a word to another role by data, no code (D3). W3-4: no correspondence coupling, only the by-hand link. P2-Q13 A: no
subcontractor accounts; party is free text on a requisition until Phase 3. ADR-0024: `Requisition` and `WorkOrder` opt in to
constraints (opt-in line in S1); automatic population from a material shortage is built here (S3), clear-on-state rules wait.
ADR-0025: the intent slot is on every command already or lands before wave 3 closes; new commands take no part in it (S2
greps and says which). ADR-0027: every new command is a `ProposableCommand` row or an entry in
`tests/tools/proposable_exclusions.toml` with a reason (S2); approve, reject, schedule and close are excluded as acts.
ADR-0026 F5: events with a when-it-happened field carry `tl:valid_time` (`WorkOrder.Started` `at`, `.Completed` `at`).

## Demo clauses (`dev/demos/P2-I4.sh` gets A's clauses 1 (without dispatch), 4, 5, 7, 8; B adds 2, 3, 6; both adapters)
1. A material requisition `requires` an IWP; its approval opens a work order; its fulfilment issues stock through I3
   commands (partial first, then the rest); a shortage raises a constraint on the requisition. `/dispatch material-request`
   from a thread: `deferred` unless P1-I7 WS-B is on the trunk (T11 checks and says).
4. A labour requisition of 6 pipefitters for two weeks; forecast by craft and week shows it requested, then approved.
5. A general requisition (crane lift) with a type-specific pset.
7. Numbering is gap-free per kind under two concurrent creators (writer lock): 20 raised by two threads give 20 distinct
   numbers `-0001..-0020` per kind.
8. The same state over the API, the TUI (requisition log, work order backlog, labour forecast) and MCP (read tools,
   `propose_requisition`). Clauses 2, 3, 6 and the labour readiness check belong to I4-B.

## Pieces (builder, `kind: piece`, review full; specs `S<n>-<slug>.md`)
| Id | Size | Piece | Spec | Depends | Sec |
|---|---|---|---|---|---|
| S1 | S | Schema and module spec: `schema/modules/requisitions/`, the five record classes and the base, two workflows, four numbering patterns, events, offline classes, constraint opt-in, access words, new package skeleton and `ModuleSpec`, settings keys. Human gate: orchestrator (P2-Q10) | written | wave 2 close | schema |
| S2 | S | Engine commands: `RaiseRequisition` (one command, kind-discriminated), `EditRequisition`, `ApproveRequisition`, `RejectRequisition`, `CancelRequisition`, `ScheduleWorkOrder`, `AssignWorkOrder`, `StartWorkOrder`, `CompleteWorkOrder`, `CloseWorkOrder`; approval chain, `expected_version`, links, `api.py` reads, actions table, ADR-0027 rows and exclusions. Access-word commands: orchestrator gate | written | S1 | access words, approval chain |
| S3 | S | Fulfilment and labour: `FulfilMaterialRequisition` through `tl_mod_materials.api.post_movements` (first module-to-module import), partial fulfilment, shortage constraint through `tl_core.constraints.raise_constraint`, labour forecast query `labour_forecast(conn, scope, weeks)`, label and psets for general kind | at C1 | S2 | money (stock), module import |
| S4 | S | Tests piece at C3: schema, guards, approval and access, fulfilment, numbering race, five-reader walk of every new route and tool, sentinel + <= 5 mutants | at C3 | all, T04c2 | — |
Owner policy kept: tests deferred to S4; each piece leaves `dev/accept/P2-I4A/<id>.py`; tour once at C4.

## Tickets (Haiku; `review` lite or full; specs written when their dependencies are in the tree)
| Id | Title | Size | Rev | Depends |
|---|---|---|---|---|
| T04a | Read views: requisition, work order, open-for-record (provided test) | H | full | S2 |
| T04c1 | API read routes (requisitions, work orders, forecast), embedded and remote | H | full | T04a, S3 |
| T04c2 | `ApiClient` and TUI client methods with fakes | H | full | T04c1 |
| T04c3 | Route access-word check before any read (as I2 T04c3) | H | full | T04c1 |
| T04d | CLI reads `tl req ls\|show\|forecast`, `tl wo ls\|show` (print keys, L-P2-I3-3) | H | full | T04a, S3 |
| T04e | CLI writes: raise, edit, approve, reject, cancel, schedule, assign, start, complete, close, fulfil | H | full | S3 |
| T07a | `requisition_text.py` (Textual-free) + TUI requisition log and record panel | H | full | T04c2 |
| T07b | `work_order_text.py` + TUI work order backlog screen and actions | H | full | T04c2 |
| T07c | TUI labour forecast grid screen (`forecast_text.py`) | H | full | T04c2, S3 |
| T07d | TUI glue: palette and navigation rows, record-screen actions, technical-mode rows | H | full | T07a-c |
| T08a | Reports and `tl req report`: open requisitions, quantities on hire (hire quantities: none yet, empty report), labour forecast, work order backlog | H | lite | T04a |
| T08b | MCP read tools and `propose_requisition` (access `user`, pinned; closed list line) | H | full | T04c2 |
| T10a | Simulator desk and `requisition_clerk` actor (labour and material requests, user acts only) | H | lite | T08a |
| T11 | Thread `/dispatch` wiring for `material-request`, `labour`, `crane-lift`, `general` if the P1-I7 parser is on the trunk, else a `deferred` note | H | full | T04e |
| T10b | `dev/demos/P2-I4.sh` clauses 1, 4, 5, 7, 8, both adapters | H | full | T10a, T07d, T08b |
| T12 | Docs: module README and AGENTS row, `docs/modules/requisitions/`, runbook `requisitions.md`, reference page | H | lite | T10b |
| T13 | Registrations are glue (<= 50 lines at C2); this row is the one ticket if they pass 50: `MCP_ACTIONS`, `add_typer`, palette, module entry point, ADR-0027 baseline refresh | H | full | S3 |

Count: 4 pieces + 17 tickets = 21 items; S 4, H 17 (about 8 points). Over the 10-ticket line, so PLANCHK.

## Order of work and checkpoints
S1 -> S2 -> S3 beside T04a -> T04c1 -> T04c2 (T04c3 beside) -> T04d, T04e, T07a-c, T08a-b -> T07d, T10a, T11 -> T10b -> T12; S4 beside T10b.
- C1: S1 merged. C2: S2, S3, T04a, T04c1, T13 (registrations) merged. C3: every ticket merged or abandoned, S4 merged.
- C4: per-folder gate on the touched packages, demo clauses 1, 4, 5, 7, 8 green on both adapters, tour once, SR3 (A rows) closed.
Merge order: S1, S2, S3, then tickets; this increment owns registry conflicts in wave 3 (I5 merges last, regenerates pinned lists).

## Deferred to the web increment (owner: CLI and TUI first)
Web twins: requisition log and record page, work order backlog page, labour forecast page, requisition create form (old
P2-WEB2). They go on `DEFERRED.md` under "Web pages for the wave 3 and 4 logs"; this increment adds no `tl-web` file.
Also deferred: clear-on-state constraint rules, correspondence coupling (W3-4), scaffold material lines, hire quantities.

## Security rows (SR3, A part; owner-optional beyond these, no extra review unless the owner asks)
Scope when run: commit range `0ae6527..p2/i4a` head, <= 450k tokens, findings `F<n> <HI|MD|LO> file:line`.
S2 approve and reject word checks and the approval chain (a requester cannot approve their own; chain is data, not trusted
input); S2 `expected_version`; S3 stock issue by module (`by_module` skips the type allow-list, never the word), partial
fulfilment arithmetic and Decimal bounds; T04c1 routes and the five-reader walk (a hidden IWP hides its requisitions;
hidden looks like missing); T08b agent tool and the row-or-exclusion test; T04e CLI never takes a password or token.

## Process lessons applied
Gates name test files or one package (L-P2-I1-2, L-P2-I3-2); dialect-neutral tests; provided tests pass ruff; write options
take the key a read prints (L-P2-I3-3); pinned module, command and tool lists are written as a union (wave 1 close); every
screen ticket needs its text module in the tree first (L-P2-WEB1-1); new tools stay closed until listed (L-P1-I4-17).

## Risks and escalation
- WorkOrder initial state: the plan's workflow starts at Scheduled, but `ScheduleWorkOrder` must be a move, so S1 adds an
  initial `Open` state (D4, asked of the plan check).
- Requisition state after approval follows its work order by module-driven moves (D5); a requisition with no work order
  (rejected, cancelled) never leaves its first states.
- `tl_mod_materials` import from `tl_mod_requisitions`: first module-to-module import; recorded in contract §3 by S3.
- Escalate: a frozen contract change; an access word the table lacks; the intent slot absent when S2 needs it; a piece
  failing twice. Naming: record classes keep the contract's spelling (`LaborRequisition`); words shown to people say "labour".

## Plan check
(left empty; the orchestrator pastes the planner-tier findings here and round 2 answers each)
