# P2-I4A-S2 — requisitions engine commands: raise, approve, work order moves, self-approval guard

Status: ready after S1 merges (plan check answered, r2)
Tier: builder
Kind: piece
Review: full
Labels: core, access
Depends on: S1
Branch: `p2/i4a-s2-engine`
Worktree: `/home/user/wt/i4a-s2`
Approver (access words, confidentiality join): orchestrator (P2-Q10; APPROVALS line at merge)

## Goal
After this piece the ten engine commands exist as module commands with their access words, handlers, state guards and
confidentiality rules (a requisition inherits its subject's class); `tl_mod_requisitions.api` gives `open_requisitions_for` and `work_order_for` (contract §3); approval
turns a requisition into a work order in one unit of work; every command is a `ProposableCommand` row or an entry in the
exclusion file; the actions table says which button shows in which state. No fulfilment, forecast or stock call (S3), no
route, CLI, screen or tool (tickets).

## Brief references (pasted; the design `requisitions-and-scaffold.md` and contract §3 are authoritative)
Commands (model, word, effect; every edit takes `expected_version`, ADR-0027 plan-check answer):
| Command | Word | Effect |
|---|---|---|
| `RaiseRequisition` | `requisitions.raise` | `kind` selects the model (discriminated union); creates the record in Requested, number per kind, `requires` link from the named IWP or CWP (`for_record_id`, optional), `references` links to a cost code and an activity (optional); `requester` is the context actor, never an input field (F4) |
| `EditRequisition` | `requisitions.edit` | Requested only; requester or a holder of `requisitions.approve`; `expected_version` |
| `ApproveRequisition` | `requisitions.approve` | Requested -> Approved; one word, no chain; the requester (context actor) may not approve their own request (fixed message); stores `approved_by`, creates the work order (Open) in the same unit and sets `work_order_id` |
| `RejectRequisition` | `requisitions.reject` | Requested -> Rejected with `reason` (required, <= 300) |
| `CancelRequisition` | `requisitions.cancel` | Requested or Approved -> Cancelled; requester or approver; cancels an Open work order with it |
| `ScheduleWorkOrder` | `requisitions.schedule` | Open -> Scheduled with `planned_start`, `planned_finish` (finish >= start), optional `hours_planned`; moves the requisition to Scheduled |
| `AssignWorkOrder` | `requisitions.assign` | sets `assigned_to` (Open or Scheduled) |
| `StartWorkOrder` | `requisitions.start` | Scheduled -> In progress, `actual_start` = optional `at` (not in the future, F6) else now; guard `no_open_blocking_constraints` (phase `start`) |
| `CompleteWorkOrder` | `requisitions.complete` | In progress -> Done, `actual_finish`, `hours_actual` (optional) |
| `CloseWorkOrder` | `requisitions.close` | Done -> Closed; closes the requisition |
Rules: the requisition and its work order move together (D5), by_module, one unit of work; a `Cancelled` or `Rejected` record
accepts no further command (fixed message); all texts bounded and cleaned with `tl_core.text`; ids resolved through a
viewer-filtered lookup that answers "unknown" for a hidden or missing id (same text); an unknown `for_record_id` refuses.
**Confidentiality (F1):** add the generic part to `tl_core/confidentiality.py` `hidden_sql` for record types that name a subject
(`requisitions.*` by `for_record_id`), reusing the LEFT JOIN pattern of the wave 2 close fix for constraints: a requisition whose
subject the viewer cannot read is hidden whole and answers as missing; a null subject falls back to the record's own class.
`api.py` (read; imports only `tl_core` and this module's tables): every function takes `viewer=` (default the lowest
clearance, never widened): `open_requisitions_for(conn, record_id, *, kinds=None, viewer=...)`,
`work_order_for(conn, requisition_id, *, viewer=...)`, row models `RequisitionRow`, `WorkOrderRow`; bounded (<= 500 rows, fixed
`ValueError` over).
ADR-0027 row-or-exclusion: add `ProposableCommand("propose_requisition", RaiseRequisition, handle_raise_requisition,
"user")` to `PROPOSABLE` in `module.py`; list `ApproveRequisition`, `RejectRequisition`, `ScheduleWorkOrder`,
`CloseWorkOrder` (acts) and `EditRequisition`, `AssignWorkOrder`, `StartWorkOrder`, `CompleteWorkOrder`, `CancelRequisition`
(owner-direct field acts; reason "person acts directly") in `tests/tools/proposable_exclusions.toml`, creating the file in
the generated-baseline shape if ADR-0027's test has not landed (grep first; say which in the report).
Intent (ADR-0025, F5): the slot is on the trunk after P2-INT C2. Commands inherit it; `S2.py` asserts that an `intent` sent with
`RaiseRequisition` and `ApproveRequisition` is stored and read back, and that a bad intent refuses the command.

## Interfaces (verbatim shapes to copy; open these)
- Command model, spec and handler shape: `packages/tl-modules/awp/src/tl_mod_awp/{commands,module,actions,handlers/signoff}.py`,
  `packages/tl-modules/materials/src/tl_mod_materials/{commands,guards,handlers/receipts}.py`.
- Numbering and gap-free allocation call: `tl_core.numbering` as used by `handlers/iwp.py` (`allocate_key`).
- Links and links life: `tl_mod_awp/linking.py`; constraint guard kind: `docs/adr/0024-constraints-on-any-record.md` §5.
- Actions table: `tl_mod_awp/actions.py` `Rule(...)` rows.

## Context (<= 14 files)
The files above; `schema/modules/requisitions/*.yaml`, `schema/settings/access-words.yaml` (from S1);
`docs/build-spec/phase2-contracts-draft.md` §3 (abridged); `docs/adr/0027-agent-first-layer.md` decisions 4 and 5 (abridged).
may explore: `docs/reports/P2-I4A/S1.md`, `packages/tl-core/src/tl_core/services/commands.py`.

## Allowed paths
- `packages/tl-modules/requisitions/src/tl_mod_requisitions/**` (create `commands.py`, `handlers/`, `actions.py`, `api.py`,
  `guards.py`, `errors.py`, `views.py` empty stub; edit `module.py`, `names.py`)
- `packages/tl-core/src/tl_core/confidentiality.py` (the generic subject part only) and its test file (one test added)
- `packages/tl-modules/requisitions/pyproject.toml` (only if an import needs a dependency S1 omitted; name it)
- `tests/tools/proposable_exclusions.toml` (create or append)
- pinned lists (rule 12) as union: command lists, proposable lists, `tests/services/test_modules.py`
- `dev/accept/P2-I4A/S2.py`, `docs/reports/P2-I4A/S2.md` (create)
Not allowed: schema, `tl_core/**`, `tl-materials`, other modules, `tl-api` `tl-cli` `tl-tui` `tl-mcp` (registrations are
supervisor glue at C2, <= 50 lines).

## Steps
1. Models and handlers per command; state guards; `module.py` exports `REQUISITIONS_COMMANDS` and `PROPOSABLE`.
2. `api.py`; actions table; exclusions file; pinned lists.
3. Acceptance script covering the table below; one mutation pass (sentinel + <= 5) on the guards named.

## Acceptance (once each; one package per gate)
```
just check
uv run python dev/accept/P2-I4A/S2.py
just gate packages/tl-modules/requisitions/tests tests/services/test_modules.py tests/tools
just gate <the confidentiality test file in packages/tl-core/tests, found with grep>
```
`S2.py` (SQLite, one `PASS <check>` line per check, final `S2 ok`): a labour requisition raised and approved by a holder of
`requisitions.approve` has a work order Open and `work_order_id` set; the requester approving their own is refused; a plain
`user` approving is refused; `requester` in the raise body is refused as an unknown field; reject needs a reason; Approved -> Closed
directly is refused; schedule, assign, start, complete, close walk both records to Closed together; a blocking constraint on
the work order refuses `StartWorkOrder`, clearing it allows it; a stale `expected_version` is refused; a hidden IWP as
`for_record_id` answers the same text as an unknown id; a requisition of a hidden IWP is absent from `open_requisitions_for` and `work_order_for`
for the default viewer and present for a cleared one; an intent round-trips; two threads raising 20 requisitions of one kind get `-0001..-0020`
with no gap and no repeat; `open_requisitions_for` returns only non-terminal records; every command is a row or an exclusion.

## Mutation (<= 5 mutants + sentinel, in this worktree, 3 lines in the report)
Guards: self-approval refusal, the subject-class join, `expected_version` check, terminal-state refusal, constraint guard on start.

## Report requirements
Standard piece report (<= 60 lines): deviations first; files; pinned lists changed; acceptance output (<= 5 lines per
command); intent slot outcome; exclusion-file outcome; mutation 3 lines; candidate learnings.

## Commit
`P2-I4A-S2: <imperative summary>`; body says what and why; end with exactly the attribution trailer your harness requires,
unchanged. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: a command needs a table word not
  in `access-words.yaml`; moving two records in one unit needs a core change; the numbering allocator is not gap-free per
  pattern under two threads; any `tl_core` edit beyond the generic subject part looks necessary.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
