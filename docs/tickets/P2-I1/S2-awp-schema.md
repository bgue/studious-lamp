# P2-I1-S2 — The awp module schema, CWP workflow, numbering pattern and standards edition

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: schema, core
Depends on: — (wave 0 is on the trunk)
Branch: `p2/i1-s2-awp-schema`
Worktree: `/home/user/wt/i1-s2`
Approver (schema): owner, or the orchestrator where P2-Q10 delegates (line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the `awp` module's data model exists as LinkML under `schema/modules/awp/`, the CWP workflow, its
numbering pattern and the `co.acme.awp@1.0.0` standards edition are fixtures, every record class carries its
`tl:offline` class, and `just gen` output plus every pinned list that names record types or events is current. No
Python package exists yet (S3 creates `packages/tl-modules/awp/`). A reader of the generated models sees six record
types, their child tables and the module's events.

## Brief references (pasted; spec `docs/build-spec/specs/m3-wbs-cwp.md` §2–§4 is authoritative, read it)
All records are project scope (`project:<P>`), confidentiality `internal`, no `ConfidentialSource`. Every record class
carries `tl:current_state` and `tl:record_types`; child tables are non-record classes (as `cost.CostSnapshotValue`).
Envelope `title` = name or subject. Decimals are text in events, ASCII digits; dates `YYYY-MM-DD`.

| Type | Key | Typed fields (table) | States | `tl:offline` |
|---|---|---|---|---|
| `awp.WBSNode` | typed `code` (`^[A-Z0-9][A-Z0-9.\-]{0,31}$`, unique per project) | `cur_awp_wbs_node`: `code`, `parent_id` (WBSNode, null at root), `depth` (0..7), `position` (int), `retired` (bool) | none | `none` |
| child | — | `cur_awp_wbs_allocation`: `node_id`, `cost_code_id` (`cost.CostCode`), `percent` (text `"40.00"`) | — | — |
| `awp.PathOfConstruction` | module-built `P123-POC` (`composed_key=True`), one per project | `cur_awp_path`: `current_version`; child `cur_awp_path_step`: `path_id`, `version`, `position`, `cwa_id`, `reason_code`, `actor`, `recorded_at` | none | `none` |
| `awp.CWA` | typed `code` (same rule as WBS) | `cur_awp_cwa`: `code`, `location_text` (<= 200), `retired` | none | `none` |
| `awp.CWP` | allocator `P123-CWP-PIP-0001`: `{project}-{type}-{discipline}-{seq:4}`, `type_code: CWP`, gap-free, counts per discipline | `cur_awp_cwp`: `discipline` (code list `Discipline`), `cwa_id`, `planned_start`, `planned_finish`, `budget_hours` (1 dp, 0..10 000 000), `quantities_json` (<= 50 rows `{commodity, qty, uom}`; lists `Commodity`, `UnitOfMeasure`), `contractor_text` (<= 120); child `cur_awp_cwp_allocation`: `cwp_id`, `wbs_node_id`, `percent` | workflow `awp-cwp.yaml` | `draft_only` |
| `awp.EWPRef`, `awp.PWPRef` | typed owner package number (unique per type and project) | `cur_awp_ewp_ref` / `cur_awp_pwp_ref`: `package_no`, `status_text` (<= 40), `forecast_date`, `actual_date`, `constraint_source` (bool), `source_system` (<= 40) | none | `none` |
| rollup table | — | `cur_awp_rollup`: `scope`, `subject_kind` (`wbs_node`), `subject_id`, `line` (`total`, `cost_code`, `unallocated`), `cost_code_id` (only on `cost_code` lines), `measure` (`budget_hours`), `value`, `as_of_seq`, `run_id` | — | — (server job only; non-record class) |

Offline: each record class carries `tl:offline` as the wave-0 offline spec defines (see an existing module class,
e.g. `schema/modules/cost/cost_code.yaml`); the reason stays in the spec table, not the schema.

**CWP workflow** (`schema/fixtures/workflows/awp-cwp.yaml`, no `roles` guard; every move is made by a module command
with `by_module=True`, so state the transitions only): Planned -> In development -> Released for IWP development ->
Executing -> Complete -> Closed; Released -> In development (return); Complete -> Executing (reopen); any state but
Closed -> Void. `expected_links` at Released: `awp.EWPRef` by `requires` (reported missing, never blocking).

**Events** (`schema/modules/awp/events.yaml`; each with `tl:event_type`; payload fields per spec §3, §4):
`WBSNode.Defined`, `.Revised`, `.Retired`, `.CostCodesMapped`, `.BudgetRolledUp` {run_id, as_of_seq, total,
by_cost_code[...]}; `PathOfConstruction.Defined`, `.Resequenced` (full new list, version + 1); `CWA.Defined`,
`.Revised`, `.Retired`; `CWP.Defined`, `.Revised`, `.AllocatedToWbs`, `.Released` {by, record_hash}; `EWPRef.Defined`,
`.Updated`; `PWPRef.Defined`, `.Updated`. `feed_policy: none` on `WBSNode.*`, `PathOfConstruction.*`,
`CWP.AllocatedToWbs`, `WBSNode.BudgetRolledUp`; `CWP.Defined` and `CWP.Released` are ordinary feed cards. `Record.*`,
`Link.*`, `Numbering.Allocated`, `Workflow.Transitioned` are core events and are not redefined.

**Standards edition** `schema/fixtures/standards/co.acme.awp@1.0.0.yaml` (data only, shape of
`co.acme.documents@1.0.0.yaml`): code lists `Commodity` = piping, structural steel, concrete, civil and earthworks,
electrical, instrumentation, mechanical equipment, insulation, painting (nine values, `value_list_policy:
extensible`, an editable starter list); `PathReason` (re-sequencing reasons: Access, Procurement, Engineering,
Weather, Crew, Owner request, Other); `ConstraintType` (read by P2-I2: Engineering, Procurement, Materials,
Equipment, Permit, Predecessor, Access, Other). `Discipline` and `UnitOfMeasure` already exist in
`co.acme.standards@1.0.0.yaml`; do not repeat them.

**Numbering**: one CWP line in `schema/fixtures/numbering/patterns.yaml` (template `{project}-{type}-{discipline}-{seq:4}`,
`type_code: CWP`, `gap_free: true`; copy how the correspondence `{kind}` segment is declared for a per-value counter).

## Interfaces (verbatim shapes to copy; open these)
- Module file shape: `schema/modules/cost/module.yaml` (imports list, `tl:module`).
- Record class with `tl:current_state`, `tl:record_types`, `tl:offline`, `tl:table`, `tl:ix_*`:
  `schema/modules/cost/cost_code.yaml`. Child table class: `cost_snapshot.yaml` (`CostSnapshotValue`).
- Event class shape: `schema/modules/cost/events.yaml`.

## Context (<= 10 files; read these, nothing else unless a step says so)
- `docs/build-spec/specs/m3-wbs-cwp.md` §2, §3, §4, §12
- `schema/modules/cost/{module,cost_code,cost_snapshot,events}.yaml`
- `schema/modules/schedule/module.yaml` (a second module, for the import list)
- `schema/fixtures/numbering/patterns.yaml`, `schema/fixtures/standards/co.acme.documents@1.0.0.yaml`
- `schema/fixtures/workflows/schedule-schedule-snapshot.yaml` (workflow fixture shape)
may explore: `packages/tl-schema/src/tl_schema/generated/{type_labels,offline_classes}.py` and the tests that pin them
(`packages/tl-schema/tests/test_type_labels.py`, `test_offline_classes.py`), `dev/accept/P2-W0/OC-S1.py`.

## Allowed paths
- `schema/modules/awp/**` (create: `module.yaml`, `wbs.yaml`, `path.yaml`, `cwa.yaml`, `cwp.yaml`, `external_package.yaml`, `rollup.yaml`, `events.yaml`)
- `schema/fixtures/workflows/awp-cwp.yaml` (create)
- `schema/fixtures/numbering/patterns.yaml` (one CWP block added; nothing else changes)
- `schema/fixtures/standards/co.acme.awp@1.0.0.yaml` (create)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only; never by hand)
- pinned lists (skill rule 12, consequential pins): tests or snapshots that enumerate record types, events, tables,
  code lists, workflows or numbering patterns and change only because awp now exists; list each in the report
- `dev/accept/P2-I1/S2.py` (create), `docs/reports/P2-I1/S2.md` (create)
Not allowed: any `packages/**/src` outside `generated/`, `tl_core/**`, any other module's schema, `pyproject.toml`,
`uv.lock`, other fixtures, the `awp.*` keys and access words (already on the trunk from wave 0).

## Steps
1. Write the LinkML and fixtures above; mirror cost-module conventions (identifier `id`, `scope`, `tl:table`, indexes
   for `(scope, code)` and the foreign-key columns the spec's queries need).
2. `just gen`; commit schema and generated output together.
3. Update pinned lists that fail `just check` only because awp exists.
4. Write `dev/accept/P2-I1/S2.py` (SQLite; header says how to run; one `PASS <check>` line per check; exit 0).

## Acceptance (run these once; no pytest, no `just gate`)
```
just gen
just check
uv run python dev/accept/P2-I1/S2.py
```
`S2.py` checks: the six record types are in `TYPE_LABELS` and in `OFFLINE_CLASSES` with the classes of the table
(CWP `draft_only`, the rest `none`); the child and rollup tables exist in the generated DDL on SQLite; the `Commodity`
list holds the nine values in order; loading `co.acme.awp@1.0.0` twice changes nothing (the second load adds no
entry, as the standards loader reports it); the workflow fixture loads and has the seven states plus Void; the CWP
pattern allocates `P123-CWP-PIP-0001` then `-0002` and `P123-CWP-CIV-0001` for another discipline (use the numbering
service the way an existing acceptance script does); every event above has a `tl:event_type` and the feed policy of
the list. Print at most the PASS lines and the final `S2 ok`.

## Tests for the end run (T11 writes them; this piece writes none)
`packages/tl-schema/tests/test_awp_schema.py`. Guards T11 will mutate: the percent text pattern, the `depth` bound,
the workflow `Closed` terminal state, the `feed_policy: none` rows. Name in the report where each sits (file:line).

## Report requirements
Standard piece report (`docs/templates/haiku-report.md` shape, <= 60 lines): deviations first; files created;
pinned lists updated (each, with why); acceptance output (<= 5 lines per command); offline classes table as built;
any event name or field you added or dropped relative to the spec.

## Commit
`P2-I1-S2: <imperative summary>`; body says what and why; end with exactly the attribution trailer your harness
requires, unchanged. Do not discuss the trailer in the report. No model names anywhere in committed files. Do not
merge; do not push.

## Escalation triggers
- *Blocked* if: the offline annotation or a reserved prefix named in the spec does not exist on the trunk; a pinned
  list change goes beyond a name added; the spec's table needs a column the generator cannot express; `just gen`
  changes any non-awp generated file other than registries that list all modules.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
