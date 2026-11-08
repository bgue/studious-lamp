# P2-I4A-S1 — requisitions schema and module spec: Requisition base, four kinds, WorkOrder

Status: ready (after the plan check is answered; dispatch round 2)
Tier: builder
Kind: piece
Review: full
Labels: schema, core
Depends on: — (wave 2 close `p2/wave2-close` @0ae6527 is the base)
Branch: `p2/i4a-s1-schema`
Worktree: `/home/user/wt/i4a-s1`
Approver (schema): orchestrator (P2-Q10; line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the LinkML under `schema/modules/requisitions/` holds the abstract `Requisition`, its four kinds and
`WorkOrder`; two workflows, four requisition numbering patterns plus one for work orders, the events, the offline classes and the
access words are fixtures; the new package `packages/tl-modules/requisitions` (`tl-mod-requisitions`) exists with a
`ModuleSpec` that registers the record types (names only) and its projectors; the generated models, DDL and every pinned
list are current. No command exists yet (S2 builds them). The Haiku read tickets start from this.

## Brief references (pasted; `phase2-contracts-draft.md` §3 and `module-designs/requisitions-and-scaffold.md` are authoritative)
All records project scope, confidentiality `internal`, no `ConfidentialSource`. Dates `YYYY-MM-DD`; decimals text, ASCII digits.
Copy conventions from `schema/modules/materials/*.yaml` and `schema/modules/awp/iwp.yaml` (identifier `id`, `scope`, `tl:table`,
`tl:ix_*`, `tl:current_state`, `tl:record_types`).

| Type | Fields (table `cur_requisitions_<snake>`) |
|---|---|
| `Requisition` (abstract) | `kind` (enum `RequisitionKind`: labor, material, general, scaffold), `subject` (<= 200), `requester` (actor text, <= 64), `need_by`, `location_text` (<= 200), `priority` (enum low, normal, high, urgent), `approval_chain` (list of access words or `user:<name>`, <= 5), `approved_by`, `approved_at`, `reject_reason` (<= 300), `work_order_id` (null until approved) |
| `requisitions.LaborRequisition` | `craft` (<= 64), `classification` (<= 64), `headcount` (int 1..500), `start_date`, `end_date` (>= start, <= 366 days), `shift` (<= 32), `requirements` (<= 500) |
| `requisitions.MaterialRequisition` | `from_location_id` (materials.Location, null ok), `lines_json` (<= 200 lines of `{item_id, qty, uom, cost_code_id?, fulfilled_qty}`; Decimal text) |
| `requisitions.GeneralRequisition` | `general_type` (code list `GeneralRequisitionType`: crane_lift, hot_work_support, other; type psets bind by class) |
| `requisitions.ScaffoldRequest` | `purpose` (<= 300), `elevation`, `gridline`, `length_m`, `width_m`, `height_m` (decimals text), `load_class` (<= 32), `duration_days` (int 1..1000) |
| `requisitions.WorkOrder` | `requisition_id`, `work_kind` (erect, modify, dismantle, lift, general, labour, issue), `assigned_to` (actor or free text <= 120), `planned_start`, `planned_finish`, `actual_start`, `actual_finish`, `hours_planned`, `hours_actual` (text, 1 dp, 0.0..10 000 000.0) |

Names: record classes keep the contract's spelling (`LaborRequisition`); labels shown to people say "Labour requisition".
Table per concrete class, as ADR-0010; the abstract base has no table.

**Numbering** (`schema/fixtures/numbering/patterns.yaml`, all `gap_free: true`, one counter per kind): material
`{project}-REQ-MAT-{seq:4}`, labour `{project}-REQ-LAB-{seq:4}`, general `{project}-REQ-GEN-{seq:4}`, scaffold
`{project}-REQ-SCF-{seq:4}`; work order `{project}-WO-{seq:4}`. First number of each is `-0001`; there is no allocator start.

**Requisition workflow** `schema/fixtures/workflows/requisitions-requisition.yaml` (one definition, `record_type` per class;
no `roles` guard; every move a module command with `by_module=True`): Requested -> Approved -> Scheduled -> In progress ->
Done -> Closed; Requested -> Rejected; Requested, Approved -> Cancelled. Terminal: Closed, Rejected, Cancelled. After
Approved the moves follow the work order (D5): the engine moves the requisition when its work order moves.
**Work order workflow** `requisitions-work-order.yaml`: Open -> Scheduled -> In progress -> Done -> Closed; Open, Scheduled ->
Cancelled. Terminal: Closed, Cancelled. `Open` is an addition to the plan's list (D4) so scheduling is a move; say so in
the report. **Constraint opt-in** (ADR-0024 §5; read it, same guard kind `no_open_blocking_constraints` as the IWP `ready`
line): on `requisitions.WorkOrder` Scheduled -> In progress (phase `start`) and on every requisition kind Approved ->
Scheduled (phase `schedule`). Both are guards of the moves, no other transition is gated.

**Events** (`schema/modules/requisitions/events.yaml`, each with `tl:event_type`): `Requisition.Raised`, `.Revised`,
`.Approved` {approved_by, work_order_id}, `.Rejected` {by, reason}, `.Cancelled` {by, reason}, `.Fulfilled` {lines,
shortage_qty} (S3 writes it), `WorkOrder.Opened`, `.Scheduled`, `.Assigned`, `.Started` {at}, `.Completed` {at, hours_actual},
`.Closed`. Feed cards: `Requisition.Approved`, `.Rejected`, `WorkOrder.Completed`; policy `none` on `.Revised`,
`.Assigned`, `.Opened`. Webhook-visible: `Requisition.Approved`, `WorkOrder.Completed` (design "Integrations").
**Valid time (ADR-0026 F5):** tag `at` of `WorkOrder.Started` and `.Completed` with `tl:valid_time` if the generator accepts the
annotation (`grep -rn "valid_time" packages/tl-schema`); if it does not yet, leave them untagged and write that under
Deviations (the tagging pass is ADR-0026's). No other field is tagged: `need_by`, `planned_*` are plans, not valid time.

**Offline classes** (`docs/build-spec/specs/offline-classes.md`; confirm, change one only with the reason in the report):
`Requisition` kinds `draft_only` (a foreman raises offline); `WorkOrder` `none`.
**Access words** (`schema/settings/access-words.yaml`, D3): `requisitions.view: read`, `requisitions.raise: user`,
`requisitions.edit: user`, `requisitions.cancel: user`, `requisitions.approve: controller`, `requisitions.reject: controller`,
`requisitions.schedule: controller`, `requisitions.assign: controller`, `requisitions.start: user`, `requisitions.complete: user`,
`requisitions.close: controller`, `requisitions.fulfil: user`. Add the module to `schema/settings/module-roles.yaml` as the
other modules appear there (viewer reads, user user-words, superuser controller-words). **Settings** in
`schema/settings/platform.yaml` (copy the `awp.iwp.size_hours` shape): `requisitions.approval.labor|material|general|scaffold`
(list of access words, default `[requisitions.approve]`, <= 5), `requisitions.forecast.weeks` (default 8, 1..52).

## Interfaces (verbatim shapes to copy; open these)
- Base and module: `docs/build-spec/phase2-contracts-draft.md` §3 (class shapes); `packages/tl-modules/materials/src/tl_mod_materials/{module,names,projectors/__init__}.py`
  and `packages/tl-modules/materials/pyproject.toml` (entry points `throughline.modules` only).
- Guard kind and opt-in syntax: `docs/adr/0024-constraints-on-any-record.md` §5; `schema/fixtures/workflows/awp-iwp.yaml` (the `ready` line).
- Projector pattern: a record projector per class writing the `cur_*` row from `Record.*` and module events, as `MtoProjector`.

## Context (<= 12 files)
`docs/build-spec/phase2-contracts-draft.md` §3 (abridged); `schema/modules/materials/{module,receipt,events}.yaml`;
`schema/fixtures/workflows/materials-receipt.yaml`, `awp-iwp.yaml`; `schema/fixtures/numbering/patterns.yaml`;
`schema/settings/{access-words,module-roles,platform}.yaml` (abridged); `packages/tl-modules/materials/src/tl_mod_materials/{module,names}.py`;
`docs/build-spec/specs/offline-classes.md`; `docs/adr/0024-constraints-on-any-record.md` §5.
may explore: `docs/reports/P2-I3/S1.md`, `packages/tl-core/src/tl_core/workflow/definition.py`.

## Allowed paths
- `schema/modules/requisitions/**` (create `module.yaml`, `requisition.yaml`, `work_order.yaml`, `events.yaml`)
- `schema/fixtures/workflows/requisitions-requisition.yaml`, `requisitions-work-order.yaml` (create)
- `schema/fixtures/numbering/patterns.yaml` (five blocks added); `schema/fixtures/standards/co.acme.awp@1.0.0.yaml` only if
  `GeneralRequisitionType` needs a code list home (say so)
- `schema/settings/{access-words,module-roles,platform}.yaml` (lines added)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only)
- `packages/tl-modules/requisitions/**` (create: `pyproject.toml`, `README.md`, `AGENTS.md`, `src/tl_mod_requisitions/{__init__,module,names,projectors/}.py`, `tests/__init__.py`); root `pyproject.toml` and `uv.lock` (workspace member line only)
- pinned lists (rule 12): tests that enumerate record types, events, tables, workflows, numbering patterns, modules, words or
  settings and change only because these exist; write each as the union; list each in the report
- `dev/accept/P2-I4A/S1.py`, `docs/reports/P2-I4A/S1.md` (create)
Not allowed: commands or handlers, `tl_core/**`, other modules, any `tl-api`, `tl-cli`, `tl-tui`, `tl-mcp` file.

## Steps
1. LinkML, fixtures, settings; `just gen`; commit schema and generated output together.
2. Package skeleton: `names.py` constants (types, tables, events), projectors, `module.py` `spec` with the record types and
   projectors and no commands (`REQUISITIONS_COMMANDS = ()` placeholder S2 fills); workspace member line; `uv sync`.
3. Fix pinned lists that fail only because these types exist. Then the acceptance script.

## Acceptance (run once each; one package per gate, pinned-list files named, never the whole suite)
```
just gen
just check
uv run python dev/accept/P2-I4A/S1.py
just gate packages/tl-schema/tests
just gate packages/tl-modules/requisitions/tests tests/services/test_modules.py tests/webhooks
just gate tests/schema
```
Also run by name every pinned-list test found with `grep -rln "materials.StockLot" tests packages/*/tests packages/tl-modules/*/tests`, at
least the DDL test (`test_ddl.py`), `test_generate.py`, and the settings and access-word tests under `tests/`.
`S1.py` (SQLite, dialect-neutral, one `PASS <check>` line per check, final `S1 ok`): the five concrete types are in `TYPE_LABELS`
and `OFFLINE_CLASSES` as stated; every table exists in generated DDL; both workflows load with the terminal states stated,
`Approved -> Closed` and `Open -> Done` refused; each of the four patterns allocates `-0001`, `-0002` and counters are
independent per kind; the two constraint opt-in guards are present and no other transition has one; every event has
`tl:event_type` and the stated feed policy; every access word resolves to its table word; the module spec loads through
`tl_core.modules` and a `Requisition` of each kind round-trips through its projector from a hand-written `Record.Created`.

## Tests for the end run (S4 writes them; none here)
Guards S4 will mutate: `headcount` and `duration_days` bounds, `end_date >= start_date`, the terminal states, the two opt-in
guards, `gap_free` on all five patterns. Name file:line for each in the report.

## Report requirements
Standard piece report (<= 60 lines): deviations first (Open state, valid-time tagging outcome); files; pinned lists updated and
why; acceptance output (<= 5 lines per command); offline classes as built; events and fields added or dropped.

## Commit
`P2-I4A-S1: <imperative summary>`; body says what and why; end with exactly the attribution trailer your harness requires,
unchanged. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: the guard kind cannot be put on a transition of an abstract-base workflow shared by four record types; a
  non-gap-free or per-kind counter is not expressible; a pinned list change goes beyond a name added; `just gen` changes a
  non-requisitions generated file other than all-module registries; an access word needs a table word the roles MVP lacks.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
