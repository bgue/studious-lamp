# P2-INSP-S2 — The eleven checklist and inspection commands, punch items in the same step, the subject row, the hook

kind: piece
review: full
branch: p2/insp-s2-commands
worktree: /home/user/wt/insp/s2
Base: `p2/ip` with `p2/x4` merged (`p2/ip-x4`, made by the orchestrator). Merge note: **waits for X4 on trunk**. Order: second of three S2s (after QR S2: merge it, or `p2/ip` after it, before your row commit).
Depends on: INSP S1 and T00 (merged: `names.py`, projectors, `insp_rules.py`). Read first: `docs/tickets/P2-IP/S2-common.md`. Gated: access-worded commands, a `confidentiality.py` subject part (APPROVALS lines at merge).
Labels: core, access, confidentiality, security.

## Why
`docs/build-spec/module-designs/inspections.md` §3, §4, §8 and `docs/tickets/P2-INSP/README.md`. The schema, workflows, words, projectors and the pure rules exist; nothing runs. T01, T03-T07, T09 and S3 are written against the names this piece freezes.

## Goal (commands as in the design §4; every model has the base envelope, `extra="forbid"`, `expected_version: int | None` on state commands, texts cleaned with `tl_core.text`)
| Command | Word (table word) | Rule |
|---|---|---|
| `CreateChecklist`, `EditChecklist` | `quality.checklist.edit` (user) | Draft only; `questions` checked by `insp_rules.validate_questions` on publish, bounds on create (<= 60); edit needs one change |
| `PublishChecklist`, `RetireChecklist`, `ReviseChecklist` | `quality.checklist.publish` (controller) | Publish refuses an empty or malformed list (the problems as one fixed-text list); revise copies a Published checklist as version n+1 in Draft with `supersedes_id` |
| `PlanInspection` | `quality.inspection.plan` (user) | `subject_id` must be readable by the actor (hidden, missing, other project: one text `no record with that id`); a subject that itself names a subject is refused unless its subject is stored on it (design §8: no chain over two hops); `for_iwp_id` defaults to the subject; key by the numbering pattern |
| `ScheduleInspection` | `quality.inspection.plan` (user) | Planned or Scheduled; needs a Published checklist, a date, an inspector; pins the version |
| `RecordInspectionResult` | `quality.inspection.record` (user) | Scheduled only; answers by `insp_rules.validate_answers` against the pinned version; `result` by `result_of` (never typed); a `reject` or `conditional` raises one punch item per failed question **in the same unit of work** (category A for a failed required question on a `hold` point, else B), source = the inspection's subject, link `raised_against` the inspection, `punch_count` set; the draft command offline |
| `VerifyInspection` | `quality.inspection.verify` (controller) | Done only; never the person who recorded it (fixed message, as `the person who cleared a punch item may not verify it`) |
| `ReinspectInspection` | `quality.inspection.plan` (user) | From Done or Verified with `reject` or `conditional`; a new Planned inspection with `reinspection_of_id`; the old one is untouched |
| `CancelInspection` | `quality.inspection.cancel` (controller) | Planned or Scheduled, `reason` 1..300 |
Rules: each move is one unit of work, `by_module=True`, through the workflow engine; `recorded_by`, `planned_by` and the actor fields come from the context, never an input; published and retired checklists and cancelled
inspections accept nothing (fixed message naming the state); a wrong state is a fixed message naming the states the command needs.

1. **Code** in `tl_mod_quality/`: `commands.py` (add models), `handlers/checklist.py`, `handlers/inspection.py` (copy the shape of `handlers/punch.py`, `handlers/common.py`; reuse the punch handler's internals for the raised
   items, do not duplicate its numbering), `errors.py` (subclasses of core error classes, common rules), `guards.py` (a `not_cancelled` and `not_retired` guard on the generic commands), `actions.py` (RULES rows per state and level, a test holds each row's level equal to the command's word).
2. **Hook** `module.py`: `INSP_COMMANDS` (rows, same row class as `PunchCommand`), `QUALITY_COMMANDS = PUNCH_COMMANDS + INSP_COMMANDS`; **`PUNCH_COMMANDS` is unchanged** (the terminal's embedded client imports it); the spec's
   `commands=` ref becomes `"tl_mod_quality.module:QUALITY_COMMANDS"`; `command_words` over `QUALITY_COMMANDS`; `generic_commands` and `generic_guards` for `quality.Checklist` and `quality.Inspection` (`SetPsetValues`, `AddLink`,
   `AttachFile` and the link-life commands only, as for the punch item); `offline_drafts` gains `{INSPECTION: {"RecordInspectionResult"}}` (`check_offline` must pass); `PROPOSABLE` gains
   `ProposableCommand("propose_inspection", PlanInspection, handle_plan_inspection, "user")`. Surface hooks (`read_routers`, `tools`, `cli_groups`) stay as they are: the tickets add their own refs (one line each, in their own wave).
3. **Marks and decided** (`quality` is in `IN_TREE_SURFACES`: marks in `tests/tools/delegation_marks.toml`, append): `PlanInspection` eligible (`"quality proposal row, access quality.inspection.plan"`); the other ten
   `excluded:reserved`. `tests/tools/proposable_exclusions.toml` (append): the ten, `CreateChecklist` and `EditChecklist` "person acts directly", `ScheduleInspection`, `RecordInspectionResult`, `ReinspectInspection`
   "act: a finding or a plan is a person's", the controller commands "act: a controller's decision".
4. **Subject row** in `tl_core/confidentiality.py`: append `("quality.Inspection", "cur_quality_inspection", "id", "subject_id")` to `SUBJECT_LINKS` (after QR's row; the QR piece owns the `test_forms_rows.py` pin edit). Test
   `tests/confidentiality/test_insp_rows.py`: an inspection on a restricted record is absent for the five readers in the record reads, counts and feed; a punch item raised by a failed answer inherits the subject's class
   (absent for the plain user, present for the cleared); `PlanInspection` on a hidden subject and on a missing id answers the same text and writes nothing; a checklist is readable at the lowest class (no project text).
5. **Provided test of T01** (plan-check F8): write `docs/tickets/P2-INSP/provided/T01_test_insp_views.py` for `tl_mod_quality/insp_views.py`, lint-clean at `packages/tl-modules/quality/tests/test_insp_views.py` (ruff format, ruff check,
   pyright run there). Pin, following the signatures and viewer defaults of the existing punch views in `tl_mod_quality/views.py`: `inspection_list`, `inspection_detail`, `inspection_counts`, `inspections_for(conn, record_id, *, viewer=LOWEST)`,
   `checklist_list`, `checklist_detail`, `export_rows(rows, fmt)` for `csv` and `jsonl`; viewer defaults to the lowest clearance; the hidden filter runs before LIMIT and before counting; a hidden subject reads as no rows and zero counts.
   `insp_views.py` is a stub (names raise `NotImplementedError`); the provided test is red until T01.

## Provided tests (copy byte-identical)
`docs/tickets/P2-IP/provided/S2_ip_rules.py` to `tests/services/ip_rules.py` (identical to QR's copy: if QR S2 is merged it is already there, `cmp` it); `S2_test_insp_rules.py` to `tests/services/test_insp_s2_rules.py`.
Own tests in `packages/tl-modules/quality/tests/`: `test_checklist_commands.py`, `test_inspection_commands.py` (the table above, one behaviour per row; verifier differs from recorder; the punch items in the same step and none when `accept`;
a failed unit of work leaves no punch item), `test_insp_visibility.py`, `test_insp_exclusions.py` (every command is a row or an exclusion), `test_module_spec.py` (updated counts: 17 commands). A world helper: extend
`packages/tl-modules/quality/tests/punch_world.py` or add `insp_world.py` (people: a plain user, a recorder, a controller, a cleared reader, an admin).

## Allowed paths
- `packages/tl-modules/quality/src/tl_mod_quality/**` (add the files above; edit `module.py`, `names.py` (add only), `commands.py`, `errors.py`, `guards.py`, `actions.py`; `insp_views.py` stub; no change to `insp_rules.py`)
- `packages/tl-modules/quality/tests/**`, `tests/confidentiality/test_insp_rows.py`, `packages/tl-core/src/tl_core/confidentiality.py` (the one tuple and its comment)
- `tests/services/{ip_rules.py,test_insp_s2_rules.py}`, `tests/tools/{proposable_exclusions.toml,delegation_marks.toml}` (append), `docs/tickets/P2-INSP/provided/T01_test_insp_views.py`
- pinned lists by union (`tests/services/test_modules.py`, the quality command counts, the API command pins of `packages/tl-api/tests/test_module_hooks_api.py`; named in the report), `docs/reports/P2-INSP/S2.md`, `dev/accept/P2-INSP/S2.py` (SQLite, `PASS <check>` lines, final `S2 ok`)
Read-only: schema, `tl_api`, `tl_cli`, `tl_mcp`, `tl_tui`, other modules.

## Acceptance (once each, one at a time)
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-modules/quality/tests/test_checklist_commands.py packages/tl-modules/quality/tests/test_inspection_commands.py
just gate packages/tl-modules/quality/tests/test_insp_visibility.py packages/tl-modules/quality/tests/test_insp_exclusions.py packages/tl-modules/quality/tests/test_module_spec.py packages/tl-modules/quality/tests/test_punch_commands.py
just gate tests/services/test_insp_s2_rules.py tests/services/test_module_conformance.py tests/services/test_modules.py tests/services/test_modules_offline.py tests/tools/test_registry_by_hooks.py
just gate tests/confidentiality/test_insp_rows.py tests/confidentiality/test_forms_rows.py
just gate packages/tl-api/tests/test_module_hooks_api.py
just gate-pg packages/tl-modules/quality/tests/test_inspection_commands.py tests/confidentiality/test_insp_rows.py
uv run python dev/accept/P2-INSP/S2.py
```

## Mutation (sentinel and at most 5, in this worktree, 3 lines in the report)
Sentinel: `RecordInspectionResult` allowed from Planned. Targets: verifier may equal recorder; the `Inspection` row removed from `SUBJECT_LINKS`; punch items raised after the unit of work commits (a failed answer list still raises); `result_of` bypassed
for a typed result; the hidden-subject refusal names the subject.

## Report
`docs/reports/P2-INSP/S2.md` (<= 60 lines): deviations first; pins changed with old and new count; marks and exclusions; gate output (<= 5 lines per command); mutation 3 lines; final names the tickets need (`INSP_COMMANDS`,
`QUALITY_COMMANDS`, handler names, command models, the world helper). Builder return <= 15 lines. Commit `P2-INSP-S2: ...`.
