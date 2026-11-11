# P2-I4-A — Requisitions and work orders (module M9, part 1), CLI and TUI only

Status: r2, plan check F1-F13 answered (below). 4 pieces, 16 tickets, about 10 weekly points. S1 and S2 specs written; nothing is
dispatched before P2-INT C2 is on the trunk. Plan sources: `docs/build-spec/08-phase2-plan.md`
"Increment 4" (A column), `specs/phase2-wave-plan.md` (wave 3), `module-designs/requisitions-and-scaffold.md`,
`phase2-contracts-draft.md` §3, `roadmap-2026-11-07.md` (item 4, W3-1, W3-4, P2-Q13). Board: `STATE.md`.
Branch `p2/i4a` from `p2/wave2-close` @0ae6527 (P2-I2 merged); the trunk is merged in after P2-INT C2 and before S1 (F5).
Worktree `/home/user/wt/p2-i4a`.

## Trim (owner, 2026-11-09, roadmap row 4b) and r3 ticket set
I4-A keeps raise, edit, approve, reject, cancel, the work order lifecycle, logs and the propose tool. Deferred (`dfr`, roadmap 3c, one `DEFERRED.md` line):
S3, T04e2, T04f, T07c, T08a, S4 (tests ride in each ticket). T13 is folded: each ticket owns its registration lines. Demo clauses kept: 1 (raise to close, no fulfilment, no shortage constraint), 5, 7, 8 (no forecast); clause 4 deferred.
Tickets (11): T04a views; T04e1 CLI writes and the `req`/`wo` groups; T04d CLI reads; T04c1 API routes; T04c2 client methods; T07a requisition screens; T07b work order backlog; T07d TUI glue; T08b MCP tools with `propose_requisition`; T10b demo; T12 docs.
Waves: 1 T04a, T04e1; 2 T04c1, T04d, T08b; 3 T04c2; 4 T07a, T07b; 5 T07d; 6 T10b; 7 T12. The older tables below describe the original plan.

## Objective
After this increment a new module `requisitions` (package `tl-mod-requisitions`) holds the generic request-to-work-order
engine and its four specialisations: labour, material, general (type psets such as a crane lift) and scaffold request.
A person raises a requisition linked to an IWP or CWP; an approver approves or rejects it with a reason; approval opens a
work order that is scheduled, assigned, started, completed and closed; a material requisition is fulfilled by issuing stock
through the I3 movement commands, with partial fulfilment and a shortage constraint raised on the requisition; labour
requisitions give a forecast by craft and week. Numbering is gap-free per kind. State reads over CLI, TUI, API and MCP;
nothing here needs the scaffold module (I4-B) or the web.
Out of scope: thread `/dispatch` wiring (F10); scaffold asset, inspections, tag colour, the two readiness checks, toolcrib (I4-B, wave 4); every web page
(deferred, below); union-hall or subcontractor requisitions as formal correspondence (W3-4: internal only, a General
correspondence item is linked by hand); permits; hire billing.

## Owner answers applied (2026-11-08)
W3-1: one access word per command in `schema/settings/access-words.yaml`; approve, reject, schedule, assign and close map to the
table word `controller` (module superuser), the others to `user`. Approval is the single word `requisitions.approve`: no
per-kind chain, no per-person grant (F4). Moving a word to another role per project is deferred (F13). W3-4: no correspondence coupling, only the by-hand link. P2-Q13 A: no
subcontractor accounts; party is free text on a requisition until Phase 3. ADR-0024: `WorkOrder` opts in on its start move
(phase `start`); a material shortage raises a constraint whose subject is the work order and whose target is the requisition
(S3, F7); clear-on-state rules wait. ADR-0025: the intent slot is on the trunk after P2-INT C2; S2 asserts that an intent
round-trips on its commands (F5). ADR-0027: every new command is a `ProposableCommand` row or an entry in
`tests/tools/proposable_exclusions.toml` with a reason (S2); approve, reject, schedule and close are excluded as acts.
ADR-0026 F5: S1 adds the classes it leaves untagged to `tests/tools/valid_time_baseline.toml` with a reason; `StartWorkOrder` takes an optional `at` (F6).

## Demo clauses (`dev/demos/P2-I4.sh` gets A's clauses 1 (without dispatch), 4, 5, 7, 8; B adds 2, 3, 6; both adapters)
1. A material requisition `requires` an IWP; its approval opens a work order; its fulfilment issues stock through I3
   commands (partial first, then the rest, lots picked first-in first-out); a shortage raises a constraint on the work order.
   Thread `/dispatch` is deferred (F10, `DEFERRED.md`).
4. A labour requisition of 6 pipefitters for two weeks; forecast by craft and week shows it requested, then approved.
5. A general requisition (crane lift) with a type-specific pset.
7. Numbering is gap-free per kind under two concurrent creators (writer lock): 20 raised by two threads give 20 distinct
   numbers `-0001..-0020` per kind.
8. The same state over the API, the TUI (requisition log, work order backlog, labour forecast) and MCP (read tools,
   `propose_requisition`); a viewer who cannot read the IWP does not see its requisitions or count them in the forecast. Clauses 2, 3, 6 and the labour readiness check belong to I4-B.

## Pieces (builder, `kind: piece`, review full; specs `S<n>-<slug>.md`)
| Id | Size | Piece | Spec | Depends | Sec |
|---|---|---|---|---|---|
| S1 | S | Schema and module spec: `schema/modules/requisitions/`, the base and four kinds (no per-kind chain), `WorkOrder`, the crane-lift pset, two workflows, five numbering patterns, events with the work-order stream named, offline classes, WO constraint opt-in, access words, valid-time baseline lines, package skeleton, `ModuleSpec`, contract §3 update. Gate: orchestrator (P2-Q10) | written | trunk after P2-INT C2 | schema |
| S2 | S | Engine commands: `RaiseRequisition` (kind-discriminated), `EditRequisition`, `ApproveRequisition`, `RejectRequisition`, `CancelRequisition`, `ScheduleWorkOrder`, `AssignWorkOrder`, `StartWorkOrder`, `CompleteWorkOrder`, `CloseWorkOrder`; `expected_version`; subject-class confidentiality (generic part in `hidden_sql`); `api.py` reads with `viewer=`; ADR-0027 rows and exclusions; intent round-trip assertion. Gate: orchestrator (access words and confidentiality, APPROVALS) | written | S1 | access words, confidentiality join |
| S3 | S | Fulfilment: `FulfilMaterialRequisition` through `tl_mod_materials.api.post_movements` (checks `requisitions.fulfil` and `materials.move` on the scope), first-in first-out lot pick by received date (stated), partial fulfilment, shortage constraint (subject the work order, phase `start`, target the requisition) through `raise_constraint`; adds `stock()` to `tl_mod_materials` (allowed path). Gate: orchestrator (stock, APPROVALS) | at C1 | S2 | money (stock), module import, materials word |
| S4 | S | Tests piece at C3: schema, guards, approval and access, fulfilment, numbering race, five-reader walk of every new route and tool, sentinel + <= 5 mutants | at C3 | all, T04c2 | — |
Owner policy kept: tests deferred to S4; each piece leaves `dev/accept/P2-I4A/<id>.py`; tour once at C4.

## Tickets (Haiku; `review` lite or full; specs written when their dependencies are in the tree)
| Id | Title | Size | Rev | Depends |
|---|---|---|---|---|
| T04a | Read views: requisition, work order, open-for-record (provided test; every read takes `viewer=`) | H | full | S2 |
| T04f | Labour forecast by craft and week (view; hidden requisitions filtered as a set before counting) | H | lite | T04a |
| T04c1 | API read routes (requisitions, work orders, forecast) with the route word check before any read, embedded and remote | H | full | T04a, T04f |
| T04c2 | `ApiClient` and TUI client methods with fakes | H | full | T04c1 |
| T04d | CLI reads `tl req ls\|show\|forecast`, `tl wo ls\|show` (print keys, L-P2-I3-3) | H | full | T04a, T04f |
| T04e1 | CLI writes: raise, edit, approve, reject, cancel, schedule, assign, start, complete, close | H | full | S2 |
| T04e2 | CLI write: `tl req fulfil` | H | full | S3, T04e1 |
| T07a | `requisition_text.py` (Textual-free) + TUI requisition log and record panel | H | full | T04c2 |
| T07b | `work_order_text.py` + TUI work order backlog screen and actions | H | full | T04c2 |
| T07c | TUI labour forecast grid screen (`forecast_text.py`) | H | full | T04c2 |
| T07d | TUI glue: palette and navigation rows, record-screen actions, technical-mode rows | H | full | T07a-c |
| T08a | Reports and `tl req report`: open requisitions, labour forecast, work order backlog (no hire report) | H | lite | T04a, T04f |
| T08b | MCP read tools and `propose_requisition` (access `user`, pinned; closed list line). Approver: orchestrator | H | full | T04c2 |
| T10b | `dev/demos/P2-I4.sh` clauses 1, 4, 5, 7, 8, both adapters; grants the demo people the module superuser role | H | full | T07d, T08b, S3 |
| T12 | Docs: module README and AGENTS row, `docs/modules/requisitions/`, runbook `requisitions.md`, reference page | H | lite | T10b |
| T13 | Registrations are glue (<= 50 lines at C2); this row is the one ticket if they pass 50: `MCP_ACTIONS`, `add_typer`, palette, module entry point, ADR-0027 baseline refresh | H | full | S3 |
Cut by the plan check: T10a (simulator desk, F9), T11 (thread dispatch, F10), T04c3 (folded into T04c1, F11).

Count: 4 pieces + 16 tickets = 20 items, about 10 weekly points (4 S + 16 H at 1 and 0.25 plus wave overhead, F12). One workflow and one builder per round.

## Order of work and checkpoints
After P2-INT C2 merges to the trunk: merge it into `p2/i4a`. Then rounds, one builder plus one ticket workflow at a time:
r2 S1 alone (human gate) -> r3 S2 -> r4 S3 beside T04a -> r5 T04f, T04c1 -> r6 T04c2, T04d, T04e1 -> r7 T07a-c, T08a-b, T04e2 -> r8 T07d, T10b, S4 -> r9 T12.
- C1: S1 merged. C2: S2, S3, T04a, T04f, T04c1, T13 (registrations) merged. C3: every ticket merged or abandoned, S4 merged.
- C4: per-folder gate on the touched packages, demo clauses 1, 4, 5, 7, 8 green on both adapters, tour once, SR3 (A rows) run with I5.
Merge order: S1, S2, S3, then tickets; I5 merges last and regenerates pinned lists.

## Deferred (owner: CLI and TUI first)
Web twins: requisition log and record page, work order backlog page, labour forecast page, requisition create form (old
P2-WEB2); this increment adds no `tl-web` file. Also: thread `/dispatch` wiring (F10); per-project moves of an access word
(F13); constraints whose target is a reference to a record (F7); clear-on-state constraint rules; correspondence coupling (W3-4);
scaffold material lines; hire quantities and the hire report. The three `DEFERRED.md` lines are listed in `STATE.md` for the orchestrator.

## Security rows (SR3, one wave review over wave 3 together with I5; owner-optional beyond it)
Scope when run: commit range `0ae6527..` wave 3 head, <= 450k tokens, findings `F<n> <HI|MD|LO> file:line`.
S2 approve and reject word checks, requester taken from the context actor, never from input; S2 `expected_version`; S2 subject-class
confidentiality join (a requisition of a hidden IWP is hidden whole and answers as missing; `viewer=` defaults to the lowest
clearance on every `api.py` read); S3 fulfilment holds `requisitions.fulfil` and `materials.move`, `by_module` skips the type
allow-list never the word, partial arithmetic and Decimal bounds, lot pick order; T04c1 routes and the five-reader walk, forecast
counts filtered as a set before counting; T08b agent tool and the row-or-exclusion test; T04e1 and T04e2 take no password or token.

## Process lessons applied
Gates name test files or one package (L-P2-I1-2, L-P2-I3-2); dialect-neutral tests; provided tests pass ruff; write options
take the key a read prints (L-P2-I3-3); pinned module, command and tool lists are written as a union (wave 1 close); every
screen ticket needs its text module in the tree first (L-P2-WEB1-1); new tools stay closed until listed (L-P1-I4-17).

## Risks and escalation
- WorkOrder initial state: S1 adds an initial `Open` state so `ScheduleWorkOrder` is a move (D4, accepted by the plan check).
- Requisition state after approval follows its work order by module-driven moves (D5).
- `tl_mod_requisitions` imports `tl_mod_materials`: first module-to-module import; recorded in contract §3 by S1 and S3.
- S2 edits `tl_core/confidentiality.py` (generic subject join) and S3 edits `tl_mod_materials` (`stock()`); both named in their Allowed paths.
- Escalate: a frozen contract change; an access word the table lacks; a piece failing twice. Naming: record classes keep the
  contract's spelling (`LaborRequisition`); words shown to people say "labour".

## Plan check (2026-11-08) and answers
Planner-tier check on r1, all findings accepted by the orchestrator. Each is applied in this file, S1, S2 and `STATE.md`.
| F | Finding | Answer |
|---|---|---|
| F1 | A requisition of a hidden IWP would show and be counted | A requisition inherits its subject's confidentiality class, as constraints do: a generic part in `hidden_sql` reusing the LEFT JOIN pattern of the wave 2 close fix (S2, `confidentiality.py` allowed). Every `api.py` read takes `viewer=` (lowest default); forecast counts filter as a set before counting (T04f). Sec row |
| F2 | Fulfil needed only the requisition word, so it could move stock a person may not move | `FulfilMaterialRequisition` also checks `materials.move` on the scope (S3); Sec row |
| F3 | `stock()` absent in materials; lot choice unstated | S3 adds `stock()` to `tl_mod_materials` (allowed path, APPROVALS) and states first-in first-out by received date |
| F4 | Per-kind chains and per-person grants are unbuilt policy | One word `requisitions.approve`; no chain, no setting, no `approval_chain` slot; the requester is the context actor, never an input field |
| F5 | Intent slot not on base | Merge the trunk after P2-INT C2 before S1; S2 asserts an intent round-trips; Q2 closed |
| F6 | Valid-time tagging unsettled | S1 adds untagged classes to `tests/tools/valid_time_baseline.toml` with a reason (allowed path); `StartWorkOrder` takes optional `at` |
| F7 | Shortage constraint subject and opt-in unclear | Subject = the work order, phase `start`, target = the requisition; the requisition opt-in is dropped; reference-to-record targets go to `DEFERRED.md` |
| F8 | Event stream of a work order unnamed | S1 names it: work order events are on the work order's own stream, requisition events on the requisition's; contract §3 updated |
| F9 | Simulator desk and hire report earn nothing in the demo | T10a cut, hire report dropped; T10b depends on T07d and T08b |
| F10 | Thread dispatch has no owner answer to depend on | T11 cut (W3-4: internal only); `DEFERRED.md` line |
| F11 | Tier and size cuts | Forecast is a Haiku lite ticket (T04f); crane-lift pset into S1; T04c3 folded into T04c1; T04e split (writes after S2, fulfil after S3) |
| F12 | Too many streams, estimate low | One workflow and one builder per round; estimate about 10 points; order of work rewritten |
| F13 | Module-roles edit and loose approvers | S1 drops the `module-roles.yaml` edit; T10b grants the superuser role; `DEFERRED.md` line for per-project word moves; approvers named for S3 and T08b (orchestrator); SR3 is one wave review with I5 |
