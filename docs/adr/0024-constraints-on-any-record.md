# ADR-0024 — Constraints are a core record type that can sit on any record

Status: proposed
Date: 2026-11-07
Deciders: repository owner (decision, paraphrased below); P2-I2 orchestrator (drafting)
Brief sections: §7.1 (links), §8 (guards), §9 M3 (constraints), §22 (offline). Related: ADR-0010, ADR-0016, P2-Q8

## Context
P2-I2 (branch `p2/i2`) models a constraint as `awp.Constraint`: one row per IWP (`iwp_id` is required in
`schema/modules/awp/constraint.yaml`), workflow `awp.constraint` (Open, Assigned, Cleared, Void), a `blocks` link
to the IWP. Piece S2 is finishing `RaiseConstraint`, `AssignConstraint`, `ClearConstraint`, `VoidConstraint` on it.

The owner has decided that this is too narrow: a requisition waits for a purchase order, a WBS node for a
predecessor, a work order for a permit. A constraint should sit on any record, name the move it holds back, say
whether it really blocks, and say what must happen to clear it.

What the code gives us today:
- Workflow guards are a closed union in `tl_core/workflow/definition.py` (`required_psets`, `conformance`,
  `required_links`, `expected_links`, `roles`), run by `workflow/engine.py`. A workflow YAML opts in by listing
  guards on a transition; a transition with none is untouched.
- The link vocabulary already has `blocks` / `blocked_by` and `resolves` / `resolved_by`. Expected links can name
  a target type with no class yet; P2-Q8 option A reports that as missing, not blocking.
- Every event already carries `effective_at` beside `recorded_at` (`ledger/types.py`): a valid-time slot.

## Decision
1. **One core record type.** `core.Constraint`, a record of its own (a `cur_core_record` row plus the typed table
   `cur_core_constraint`, ADR-0010 storage, generated from `schema/core/`). Numbered `{project}-CON-{seq:4}`,
   gap-free, as today. The awp class, table, workflow and events are removed from `schema/modules/awp/`.
2. **Subject, phase, severity, category.**
   `subject_id` (any record the actor can see); `phase` (the gated move, a lowercase code, `start` and `completion`
   common; decision 5); `severity` (`blocking` stops a move, `advisory` is only shown); `category` (closed list:
   `materials`, `labour`, `scaffold`, `equipment`, `permit`, `engineering`, `rfi`, `predecessor`, `other`; it replaces
   the awp `ConstraintType`). Kept from awp: `owner`, `description` (500), `source` (`manual`, `check`, `rule`,
   `feed_hold`, `thread_hold`), `check_name`, `facts_hash`, `suppress_hash`, `clear_reason`.
3. **Target: a record or a plain reference.** A constraint says what must happen to clear it.
   - `target_kind = record`: `target_id` names an existing record (RFI, document, take-off line or reservation,
     upstream work package or WBS node), joined by a `targets` link (inverse `targeted_by`).
   - `target_kind = reference`: `target_ref_type` (`purchase_order`, `labour_requisition`, `scaffold_requisition`,
     `equipment`, `permit`, `other`) and `target_ref_text` (60 characters) for types that do not exist yet. Reported
     like P2-Q8 option A: "not tracked yet", never a blocker by itself. Wave 3 links it to the new record later.
4. **Valid time, kept apart from ledger time.** The constraint carries `effective_at` (when it began to hold
   things back), `due_at` (when it must be cleared; replaces awp `need_by`) and `cleared_at` (when it truly stopped
   holding things back). All three are world time, supplied by the person or module and editable only by a new
   event. Ledger recorded time is the event's own `recorded_at` and is never a field. A supplied `cleared_at` is
   also passed as the event's `effective_at`, so the two copies agree. `cleared_at` before `effective_at` is refused.
5. **Opt-in is a guard kind, as guards work today.** A new guard `no_open_blocking_constraints` with an optional
   `phase` (default: the transition's own name) joins the `Guard` union, e.g. `{kind: no_open_blocking_constraints,
   phase: start}` on `start_execution`. It fails, with a fixed message and the keys, when the record has an open
   blocking constraint of that phase. Transitions without the guard are untouched. A phase is whatever some guard of the
   subject's workflow names, so phases map to transitions only through guards. A blocking raise with a phase no
   guard names is refused (`phase_not_gated`); an advisory one is allowed anywhere. `by_module` moves run it too.
6. **Commands and events (core, `tl_core/constraints/`).** `RaiseConstraint {subject, phase, severity, category,
   target?, owner, description, effective_at?, due_at?, source?, check_name?, facts_hash?}`, `AssignConstraint
   {constraint, owner}`, `ClearConstraint {constraint, reason, cleared_at?, resolved_by?}`,
   `WithdrawConstraint {constraint, reason}` (replaces `VoidConstraint`). Events: `Constraint.Raised` (all fields
   above, plus `constraint_id`, `subject_id`), `Constraint.Assigned` {constraint_id, owner}, `Constraint.Cleared`
   {constraint_id, cleared_at, cleared_by, reason, resolved_by?, suppress_hash?}, `Constraint.Withdrawn`
   {constraint_id, reason}; each followed by `Workflow.Transitioned` in `core.constraint` (Open, Assigned, Cleared,
   Withdrawn). Links: `blocks` constraint to subject, `targets` constraint to target, `resolves` resolved_by to
   constraint. The awp rules stay (a person raises only `manual`; other sources need `by_module`; a check clears
   only what a check raised; a person's clear of a check-raised one stores `suppress_hash`, R-P2-11). The readiness
   engine (S4) keeps raising and clearing on IWPs through the core functions `raise_constraint` and
   `clear_constraint` with `by_module`; awp stores no constraint.
7. **Access.** Core words, one rule for every record type: `core.constraint.edit` = user (raise, assign, clear,
   withdraw) and `core.constraint.view` = read; `awp.constraint.edit` is dropped. A person may raise only on a
   record they can see.
8. **Confidentiality (ADR-0016).** A constraint is hidden whenever its subject is hidden: it uses the subject's
   class, so a constraint on a restricted correspondence item is absent for a viewer who cannot read the item,
   from lists, counts, the log, events, feed and links. A viewer who can see the subject but not the target sees
   the target as missing, and the constraint count never changes with what the viewer can see: only the target's
   own display does. A hidden `resolved_by` or target on a command answers as an unknown id, never as "hidden".
   The guard counts every open blocking constraint (system viewer inside the engine); its message names only keys
   the viewer can read.
9. **Offline class `draft_only`**, as awp had: numbered on the authority (P3-Q8); clearing is an authority act.
10. **Migration: none.** `awp.Constraint` exists only on branch `p2/i2` and never reached the trunk. The awp
    schema, projector, fixtures and S2 constraint code are replaced before wave 2 merges; the seed ledger
    `.accept/p2-i2.db` is regenerated.

**Thin slice in P2-I2:**
- Core type, workflow, four commands, `targets` relation, access words, confidentiality filter, the guard kind.
- Opt-in on `awp.CWP` (`start_execution`, `complete`), `awp.IWP` (`start`, `complete`) and `awp.WBSNode`. WBSNode
  has no workflow today, so a two-move one (`start`, `complete`) is added. Open point: owner to confirm.
- A constraint log screen (TUI) and `tl constraint ls` (CLI) per record, filters state, category, phase, blocking,
  opened from the record screens (T04b rebased onto it). The demo generator seeds a realistic set (materials,
  scaffold, predecessor, RFI target, advisory, plain-reference permit, one cleared with `cleared_at`).

**Wave 3, not now:** automatic population from requisitions, scaffold and POs; requisitions and work orders carry
constraints from the start; clear-on-target-state rules; readiness beyond IWPs; correspondence, schedule activities.

## Consequences
- Contracts changed: `Guard` gains a member; `schema/core` gains a class, events, a relation; the access words swap
  one word. Gates: `schema/**` (human gate, P2-Q10); guard and confidentiality filter go on the security review list.
- Cost against an awp-only constraint (P2-I2 plan: about 10 rounds, 5 pieces, 19 tickets), and the pause:

## Effort

| Item | Builder pieces | Tickets |
|---|---|---|
| Core schema (class, events, workflow, code lists, relation, words) | 1 | 0 |
| Core commands, guard kind and engine, confidentiality filter and test walk | 1 | 0 |
| S4 raise/clear hook rework (calls core functions) | 0 | 1 |
| WBS node workflow, opt-in lines on CWP and IWP workflows | 0 | 1 |
| Log screen and CLI per record with four filters (on top of T04b/T04d) | 0 | 2 |
| Demo generator seeds | 0 | 1 |
| **Extra versus awp-only** | **2** | **about 5** |

Pause: S3 (sign-off, issue, hold) does not depend on constraints and is not paused. S2 finishes its IWP, scope
and pin half; its constraint half is redone in the two new pieces (about 1 round each, one after the other).
S4 pauses its raise and clear hook for about 2 rounds; the rest of S4 runs. Constraint tickets (T04a views, T04b,
T04c1, T04d, T09b, demo) start 2 rounds later. Net: the increment grows by about 2 rounds, 1 if the first piece
runs beside S3.

## Stubs for the knowledge graph
`effective_at`, `due_at` and `cleared_at` are valid-time fields apart from ledger transaction time, so a graph can
later ask "what held this package back on 3 March, as we knew it on 5 March". `targets` and `blocks` give an edge
per dependency; a plain reference is a node waiting for a type. P2 builds no graph.

## Alternatives considered
| Option | Why not |
|---|---|
| Keep `awp.Constraint`, copy it per module later | Each module would copy the type, commands and screens |
| Constraint as a pset or plain link | No numbering, owner, history, dates or log screen; the guard has nothing to count |
| Guard on every transition by default | Breaks transitions nobody asked to gate; owner wants opt-in |
| Phase as a closed list in code | Workflows differ; the guard keeps the phase in the workflow YAML |

## Plan check (2026-11-07) and answers
Findings that concern this ADR (F1, F2, F7–F13 of `4 PLANCHK docs/adr/0024+0025`); all accepted by the orchestrator.
v2 of this ADR folds them in before the first core piece.
- F1 HI: the IWP opt-in goes on the `ready` move, not `start`; S4 raises with phase `ready`; `constraints_cleared` counts open blocking constraints of phase `ready`. **Accepted.**
- F2 HI: freeze `raise_constraint(uow, *, subject_id, phase, severity, category, source, check_name, facts_hash, by_module)` and `clear_constraint(...)` in this ADR now, so S4 codes against them from dispatch; no S4 rework ticket, no hook pause. **Accepted** (net about +1 round).
- F7 MD: records are never deleted, so a hidden target is shown as no target (not "not available"); the walking test compares against a no-target twin. **Accepted.**
- F8 MD: take the confidentiality class by a join to the subject at read time, never copy it at raise; no system viewer; the guard message names constraint keys and phase only. **Accepted.**
- F9 MD: `phase_not_gated` checks the subject's effective (project-override, versioned) workflow at raise; the log flags rows whose phase is no longer gated. **Accepted.**
- F10 MD: the WBS node workflow is deferred to wave 3 (no wave 2 demo clause needs it; it overlaps I5 progress); opt-in on CWP and IWP only now. **Accepted**, logged in DEFERRED.
- F11 MD: no separate log screen ticket: the core `tl constraint` CLI and the per-record log fold into T04b and T04d; generator seeds go in the generator's awp ticket and T10b clause 3; the pause list adds T04e, T09a, TW2, T10a. **Accepted.**
- F12 MD: the opt-in workflow lines go in the core schema piece under its gate; piece 2 moves S2's constraint code (iwp_id -> subject_id), S2 is merged whole first (done). **Accepted.**
- F13 MD: approver "orchestrator, with an APPROVALS line"; Sec rows: the guard and the constraint class join, each with its commit range. **Accepted.**
