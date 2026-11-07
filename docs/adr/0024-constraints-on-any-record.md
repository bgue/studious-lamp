# ADR-0024 — Constraints are a core record type that can sit on any record

Status: proposed (v2, plan-check findings folded in; the orchestrator accepts it at the core piece merge)
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
   the awp `ConstraintType`). Kept from awp: `owner` (required for source `manual`, optional otherwise: an unowned constraint stays Open until assigned), `description` (500), `source` (`manual`, `check`, `rule`,
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
   `phase_not_gated` reads the subject's effective workflow (project override, versioned) at raise time; a later
   workflow change can leave a phase ungated, so the log flags such rows (`phase_ungated`) and they never block.
   The IWP opt-in is on the `ready` transition (Constraint check to Ready), phase `ready`: S4 raises with phase
   `ready` and `constraints_cleared` counts open blocking constraints of phase `ready` on the IWP.
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
   engine (S4) keeps raising and clearing on IWPs through the core functions below with `by_module`; awp stores
   no constraint. **Frozen signatures** (module `tl_core.constraints`; a stub with these exact signatures is in the
   tree before the core pieces; changing one is an orchestrator decision):
   ```python
   ConstraintAction = Literal["raised", "exists", "suppressed", "cleared"]
   class ConstraintOutcome(BaseModel):   # frozen
       constraint_id: str | None; key: str | None; action: ConstraintAction

   def raise_constraint(uow, *, subject_id: str, phase: str, severity: Literal["blocking", "advisory"],
                        category: str, source: str, check_name: str | None, facts_hash: str | None,
                        by_module: str, owner: str | None = None, description: str | None = None,
                        due_at: str | None = None, effective_at: str | None = None,
                        target_id: str | None = None, target_ref_type: str | None = None,
                        target_ref_text: str | None = None) -> ConstraintOutcome: ...
   def clear_constraint(uow, *, constraint_id: str, reason: str, by_module: str,
                        cleared_at: str | None = None, resolved_by: str | None = None) -> ConstraintOutcome: ...
   def open_blocking(conn, subject_id: str, phase: str) -> list[str]: ...   # constraint keys, no viewer
   ```
   Semantics: sources other than `manual` need `by_module`; source `check` needs `check_name` and `facts_hash`. An open
   constraint of the same subject, phase and `check_name` answers `exists` (no new row). A raise whose `facts_hash`
   equals the `suppress_hash` of a person-cleared one answers `suppressed` (R-P2-11). `clear_constraint` from a
   module clears only a constraint whose source is not `manual` (action `cleared`); a person's clear goes through
   the `ClearConstraint` command, which stores `suppress_hash` for a check-raised one.
7. **Access.** Core words, one rule for every record type: `core.constraint.edit` = user (raise, assign, clear,
   withdraw) and `core.constraint.view` = read; `awp.constraint.edit` is dropped. A person may raise only on a
   record they can see.
8. **Confidentiality (ADR-0016).** A constraint is hidden whenever its subject is hidden: its class is taken by a
   join to the subject at read time, never copied at raise, and there is no system viewer anywhere (the engine
   guard counts through `open_blocking`, a keys-only count that needs no class). So a constraint on a restricted correspondence item is absent for a viewer who cannot read the item,
   from lists, counts, the log, events, feed and links. Records are never deleted, so a viewer who can see the subject but not the
   target sees the constraint with no target at all (not "not available"), identical to a constraint raised without
   one; the walking test compares the two. The constraint count never changes with what the viewer can see: only the
   target's own display does. A hidden `resolved_by` or target on a command answers as an unknown id, never as
   "hidden". The guard counts every open blocking constraint; its message names the constraint keys and the phase
   only (never a description, owner or target).
9. **Offline class `draft_only`**, as awp had: numbered on the authority (P3-Q8); clearing is an authority act.
10. **Migration: none.** `awp.Constraint` exists only on branch `p2/i2` and never reached the trunk. The awp
    schema, projector, fixtures and S2 constraint code are replaced before wave 2 merges; the seed ledger
    `.accept/p2-i2.db` is regenerated.

**Thin slice in P2-I2:**
- Core type, workflow, four commands, `targets` relation, access words, confidentiality filter, the guard kind.
- Opt-in lines on `awp.CWP` (`start_execution`, `complete`) and `awp.IWP` (`ready`, phase `ready`; `start`,
  `complete`), in the core schema piece under its gate. The WBS node workflow is deferred to wave 3 (no wave 2 demo
  clause needs it; it overlaps I5 progress).
- No separate log ticket: the per-record log and the core `tl constraint` CLI (filters state, category, phase,
  blocking) fold into T04b (screen) and T04d (CLI). Generator seeds (materials, scaffold, predecessor, RFI target,
  advisory, plain-reference permit, one cleared with `cleared_at`) go in the awp ticket of the P2-SEED generator
  and in demo clause 3 of T10b.

**Wave 3, not now:** automatic population from requisitions, scaffold and POs; requisitions and work orders carry
constraints from the start; clear-on-target-state rules; readiness beyond IWPs; correspondence, schedule activities.

## Consequences
- Contracts changed: `Guard` gains a member; `schema/core` gains a class, events, a relation; the access words swap
  one word. Gates: `schema/**` (human gate, P2-Q10); guard and confidentiality filter go on the security review list.
- Cost against an awp-only constraint (P2-I2 plan: about 10 rounds, 5 pieces, 19 tickets), and the pause:

## Effort

| Item | Builder pieces | Tickets |
|---|---|---|
| C1 core schema (class, events, workflow, guard kind in the model, relation, words, opt-in lines, awp class removed) | 1 | 0 |
| C2 core commands (frozen functions), guard evaluation, confidentiality join, moved S2 code | 1 | 0 |
| Log and CLI per record (inside T04b and T04d) | 0 | 0 |
| Generator seeds (P2-SEED awp ticket) | 0 | 0 |
| **Extra versus awp-only** | **2** | **0** |

Pause: S3 (sign-off, issue, hold) does not depend on constraints and is not paused. S2 finishes its IWP, scope
and pin half; its constraint half is redone in the two new pieces (about 1 round each, one after the other).
S4 does not pause: it codes against the frozen signatures above (stub in tree) and merges after C1; its tests that call
the functions run once C2 merges. Constraint tickets (T04a views, T04b,
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

## Folded in v2 (2026-11-07)
F1, F2, F7, F8, F9, F11, F12 and F13 are in the Decision text above; F10 in the thin slice. Plan: pieces C1 (schema, gate:
orchestrator with an APPROVALS line) and C2 (commands), see `docs/tickets/P2-I2/C1-core-constraint-schema.md` and
`C2-core-constraint-commands.md`. Sec rows: the guard evaluation and the constraint class join, each over its commit range.
