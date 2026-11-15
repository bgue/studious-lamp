# P2-INSP S1 — Quality module: schema, workflows, numbering, words and projectors for checklists and inspections

kind: piece
review: full
branch: p2/insp-s1-schema
worktree: /home/user/wt/insp/s1
Depends on: `p2/ip` (after P2-QR S1 is merged there, or merge it in and regenerate). Gated: schema, settings, access
words (APPROVALS lines before merge). Labels: schema.
Merge rule (P2-QR README, fan-out): the first S1 with signed APPROVALS merges first; a later S1 merges `p2/ip`, re-runs
`just gen` and `just compat-update` and re-pins its counts. At most 2 heavy runs: INSP S1 runs with QR S1.

## Why
`docs/build-spec/module-designs/inspections.md` §1, §3, §4: inspections extend the `quality` module beside the punch
list. Today the module has one class (`schema/modules/quality/punch_item.yaml`) and one projector. Commands (S2), the
readiness check (S3) and fifteen tickets are written against the names, tables and states this piece creates.
Additive only: no existing class, event, word, workflow or column changes.

## Goal
1. **Schema** in `schema/modules/quality/`: new `checklist.yaml`, `inspection.yaml`; `events.yaml` and `module.yaml`
   gain the new classes and imports. Copy conventions from `punch_item.yaml` (id, scope, annotations, date patterns).

   | Class | Table, offline | Fields |
   |---|---|---|
   | `Checklist` (`quality.Checklist`) | `cur_quality_checklist`, `none` | `discipline` (≤ 64, indexed), `version` (int ≥ 1, default 1), `questions` (`tl:json`, required, default `[]`), `question_count` (int ≥ 0), `supersedes_id` (indexed), `published_by`, `published_on`, `retired_on` |
   | `Inspection` (`quality.Inspection`) | `cur_quality_inspection`, `draft_only` | `subject_id` (indexed; the confidentiality subject), `for_iwp_id` (indexed), `checklist_id` (indexed), `checklist_version` (int), `point` (enum `InspectionPoint`: hold, witness, review, surveillance), `area` (≤ 64, indexed), `planned_on`, `scheduled_for` (indexed), `inspector` (≤ 120), `result` (enum `InspectionOutcome`: accept, reject, conditional; null until Done), `done_at`, `answers` (`tl:json`, default `[]`), `note` (≤ 1000), `recorded_by`, `verified_by`, `verified_on`, `reinspection_of_id` (indexed), `cancel_reason` (≤ 300), `punch_count` (int ≥ 0, default 0) |

   The title of each record is on the envelope. The shape of one question and one answer is documented in the class
   description (S2 validates it in `insp_rules`; the schema stores JSON): question `{id, text, kind, required, unit,
   min, max, choices, fails_when}`, at most 60; answer `{q, value, note}`.
2. **Events** (`feed_policy: none`; every payload names `record_id`; `tl:json` where a list is carried):
   `Checklist.Created` {discipline, questions, question_count, version, supersedes_id}, `Checklist.Edited` {changes},
   `Checklist.Published` {published_on}, `Checklist.Retired` {retired_on};
   `Inspection.Planned` {subject_id, for_iwp_id, point, area, planned_on, reinspection_of_id},
   `Inspection.Scheduled` {checklist_id, checklist_version, scheduled_for, inspector},
   `Inspection.ResultRecorded` {answers, result, done_at, note, punch_item_ids},
   `Inspection.Verified` {verified_on}, `Inspection.Cancelled` {reason}.
   Valid time (ADR-0026): tag `done_at` on `ResultRecorded` and `verified_on` on `Verified` with `tl:valid_time`; put
   the others in `tests/tools/valid_time_baseline.toml` with a reason each.
3. **Workflows** (`schema/fixtures/workflows/`, every move `by_module`, no role guard; copy the header comment style
   of `quality-punch-item.yaml`):
   `quality-checklist.yaml`: initial Draft; `publish` Draft → Published; `retire` Published → Retired, Draft → Retired.
   Final: Retired.
   `quality-inspection.yaml`: initial Planned; `schedule` Planned → Scheduled and Scheduled → Scheduled (reschedule);
   `record` Scheduled → Done; `verify` Done → Verified; `cancel` Planned → Cancelled, Scheduled → Cancelled.
   Final: Verified, Cancelled.
4. **Numbering** (`schema/fixtures/numbering/patterns.yaml`, same form as the `quality.PunchItem` block, gap-free as
   that block is): `quality.Checklist` type_code `CHK`, `quality.Inspection` type_code `INS`.
5. **Access words** (`schema/settings/access-words.yaml`, appended to the quality block): `quality.checklist.edit:
   user`, `quality.checklist.publish: controller`, `quality.inspection.plan: user`, `quality.inspection.record: user`,
   `quality.inspection.verify: controller`, `quality.inspection.cancel: controller`. Six new words; reads keep the existing
   `quality.view`. Do not change the seven punch words.
6. **Setting** (`schema/settings/platform.yaml`): `quality.inspections.required_for_iwp` (bool, default false, scopes
   `[platform, company, project]`, lockable; "when on, an IWP with no planned inspection is not ready").
7. **Fixtures** `schema/fixtures/quality/checklists/`: `hydrotest-precheck.yaml`, `flange-makeup.yaml`,
   `scaffold-handover.yaml`; 6 to 10 questions each, covering all four kinds and both `fails_when` forms; plain data
   in the question shape above. A loader is not this piece.
8. **Module code** in `packages/tl-modules/quality/src/tl_mod_quality/`: `names.py` gains the record types, states,
   the six words and the event names (add, never rename); `projectors/checklist.py`, `projectors/inspection.py`
   (follow `projectors/punch_item.py`; `question_count` and `punch_count` are set from the payloads);
   `projectors/__init__.py` exports them; `module.py` adds the two record types and projectors to `spec()` and to
   `projectors()`. No commands, no generic-command rows, no hook change (S2).
9. `just gen`, `just compat-update` (additive); commit sources and generated output together.

## Allowed paths
- `schema/modules/quality/{checklist,inspection}.yaml` (create), `schema/modules/quality/{events,module}.yaml` (add only)
- `schema/fixtures/workflows/quality-checklist.yaml`, `quality-inspection.yaml` (create);
  `schema/fixtures/numbering/patterns.yaml` (two blocks); `schema/fixtures/quality/checklists/*.yaml` (create)
- `schema/settings/access-words.yaml` (six lines); `schema/settings/platform.yaml` (one key);
  `tests/tools/valid_time_baseline.toml` (lines); `docs/build-spec/specs/offline-classes.md` (two rows)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only); `packages/tl-schema/compat/event-schemas.json`
- `packages/tl-modules/quality/src/tl_mod_quality/{names,module}.py`, `projectors/{__init__,checklist,inspection}.py`
- `packages/tl-modules/quality/tests/test_insp_projectors.py` (create), `tests/test_module_spec.py` (record-type list)
- `packages/tl-schema/tests/test_quality_schema.py` (add tests; keep the punch tests as they are)
- Pinned lists, union form, each named in the report with old and new count: `packages/tl-schema/tests/test_offline_classes.py`
  (+2), `test_ddl.py`, `test_generate.py`, `test_ddl_views.py`, `packages/tl-core/tests/auth/test_access_words.py`
  (the `QUALITY` set +6), `packages/tl-core/tests/test_numbering_config.py` (two patterns),
  `tests/settings/test_phase2_keys.py` and `packages/tl-core/tests/test_settings_definitions.py` (one key), and any
  other test that fails only because the classes, words or key now exist
  (`grep -rln "quality.PunchItem" tests packages/*/tests packages/tl-modules/*/tests`)
- `packages/tl-core/src/tl_core/feed/cards.py`: only if a test refuses the new quiet events, add their names to the
  list it names (the P2-PUNCH S1 precedent, decision D14); say so in the report
- `docs/reports/P2-INSP/S1.md` (create)
Not allowed: `commands.py`, `handlers/**`, `guards.py`, `actions.py`, `views.py`, `api.py`; any `tl_core/**` other
than the one line above; `tl_api`, `tl_cli`, `tl_mcp`, `tl_tui`, `tl_web`; the awp module; `punch_item.yaml`.

## Tests to add
- `test_quality_schema.py`: both classes, tables and indexes; the two enums and their values; nine event types with
  their payload fields; offline classes `none` and `draft_only`; both workflows load with the moves above and reject
  `Done → Planned` and any move out of Verified, Cancelled or Retired; numbering keys `P123-CHK-0001`, `P123-INS-0001`;
  the three fixtures parse, have 6 to 10 questions, unique question ids and only the four kinds.
- `test_insp_projectors.py` (events appended through the ledger, never a projection write): a checklist created,
  edited, published, retired gives the expected row at each step; an inspection planned, scheduled, rescheduled,
  recorded (two punch ids), verified gives the expected row; cancelled from Planned; a rebuild of both tables equals
  the live rows; the punch table is untouched by every event above.
- `test_module_spec.py`: three record types; the punch commands and words are exactly as before.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); then, one run at a time:
`just gate packages/tl-schema/tests/test_quality_schema.py packages/tl-schema/tests/test_offline_classes.py packages/tl-schema/tests/test_ddl.py packages/tl-schema/tests/test_ddl_views.py packages/tl-schema/tests/test_generate.py packages/tl-schema/tests/test_compat.py packages/tl-schema/tests/test_valid_time_tag.py`
and
`just gate packages/tl-core/tests/auth/test_access_words.py packages/tl-core/tests/test_numbering_config.py packages/tl-core/tests/test_settings_definitions.py tests/settings/test_phase2_keys.py tests/services/test_modules.py tests/services/test_modules_offline.py packages/tl-modules/quality/tests/test_module_spec.py packages/tl-modules/quality/tests/test_insp_projectors.py packages/tl-modules/quality/tests/test_punch_commands.py packages/tl-modules/quality/tests/test_views.py tests/tools/test_demo_project_quality.py`.
`just gate-pg packages/tl-modules/quality/tests/test_insp_projectors.py`. Every existing path above was checked with
`ls` on trunk @d4e92ffc; `test_insp_projectors.py` is created by this piece.

## Mutation cap
One sentinel plus at most 3 targeted mutants: the inspection workflow allows `record` from Planned; the projector
drops `checklist_version` on reschedule; `punch_count` not set from the payload. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-INSP/S1.md`; first line: deviations or none; list
every pinned file changed with old and new count, and the final names (record types, states, events, words) as one
table for S2 and the tickets. Commit `P2-INSP-S1: ...` with the session trailers; no model names in committed text.
