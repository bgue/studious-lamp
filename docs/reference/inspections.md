# Reference — inspections and checklists: routes, tools, verbs, commands

Purpose: the exact surfaces of inspections and checklists as built (P2-INSP slice 1): CLI verbs, API routes, MCP tools, the module
commands behind them, their access words and states, and the export columns. How to run them: [runbook](../runbooks/inspections.md).
Module: [quality](../modules/quality/README.md). Design: [inspections.md](../build-spec/module-designs/inspections.md).

## CLI
Every write takes `--project` (the project of the record) and prints one line `<verb> <KEY>  version <v>`, unless it is a refusal.
Actor: the signed-in person (`tl login`); the ledger from `--db` or `TL_DB`.

### `tl insp` (inspections)
| Verb | Arguments and options | Word (table word) | From state → to state |
|---|---|---|---|
| `plan` | `--project`, `--subject KEY`, `--title TEXT`, `--point hold\|witness\|review\|surveillance`, `--for KEY`, `--area TEXT`, `--planned-on DATE` | `quality.inspection.plan` (user) | none → Planned |
| `schedule KEY` | `--checklist KEY`, `--on DATE`, `--inspector user:X`, `--expected-version N` | `quality.inspection.plan` (user) | Planned or Scheduled → Scheduled |
| `record KEY` | `--answer Q=VALUE` (repeat) or `--answers-file FILE` (JSON list, 256 KiB), `--note TEXT`, `--expected-version N` | `quality.inspection.record` (user) | Scheduled → Done |
| `verify KEY` | `--expected-version N` | `quality.inspection.verify` (controller) | Done → Verified |
| `reinspect KEY` | `--planned-on DATE`, `--expected-version N` | `quality.inspection.plan` (user) | none → Planned (new key, names KEY) |
| `cancel KEY` | `--reason TEXT`, `--expected-version N` | `quality.inspection.cancel` (controller) | Planned or Scheduled → Cancelled |
| `ls` | `--project`, `--state`, `--point`, `--area`, `--inspector user:X`, `--subject KEY`, `--for KEY`, `--limit N` (default 200) | `quality.view` | read |
| `show KEY` | `--project` | `quality.view` | read |
| `export` | `--project`, `--format csv\|jsonl` | `quality.view` | read |

`record` prints `recorded <KEY>  version <v>`, `result accept|reject|conditional`, `punch <n>`. `ls` ends with `<shown> of <total>`.

### `tl checklist` (checklists)
| Verb | Arguments and options | Word (table word) | From state → to state |
|---|---|---|---|
| `create` | `--project`, `--title TEXT`, `--discipline TEXT`, `--questions-file FILE` (JSON list, 256 KiB) | `quality.checklist.edit` (user) | none → Draft, version 1 |
| `edit KEY` | `--title`, `--discipline`, `--questions-file` (at least one) | `quality.checklist.edit` (user) | Draft → Draft |
| `publish KEY` | `--project` | `quality.checklist.publish` (controller) | Draft → Published |
| `revise KEY` | `--project` | `quality.checklist.publish` (controller) | Published → new Draft (version n+1, `supersedes_id`) |
| `retire KEY` | `--project` | `quality.checklist.publish` (controller) | Draft or Published → Retired |
| `ls` | `--project`, `--state Draft\|Published\|Retired`, `--discipline TEXT`, `--limit N` (default 200) | `quality.view` | read |
| `show KEY` | `--project` | `quality.view` | read |

Checklist verbs use the version they read; the inspection verbs take `--expected-version`. A question file is a JSON list of questions:
`id`, `text`, `kind` (`yes_no_na`, `number`, `text`, `choice`), `required`, `unit`, `min`, `max`, `choices`, `fails_when` (`no`, `out_of_range`).

## API
Base: the API server (`tl serve`). Read routes take `project` as a query parameter (`?project=P123`), not a path segment. A missing
or hidden key answers the same 404 body (`no inspection <KEY>` or `no checklist <KEY>`). Totals and counts are taken after the viewer's
filter. Command writes go through the command door with the names of the table below (`POST /commands/<Name>`).

| Method and path | operation id | Query parameters | Reply |
|---|---|---|---|
| `GET /quality/inspections` | `list_inspections` | `project` (required), `state`, `point`, `area`, `inspector`, `subject`, `for`, `limit` (1 to 500, default 200) | rows and total |
| `GET /quality/inspections/export` | `export_inspections` | `project`, `format` (`csv` default, or `jsonl`), `state`, `point`, `area`, `inspector`, `subject`, `for`, `limit` (default 200) | the export rows |
| `GET /quality/inspections/{key}` | `get_inspection` | `project` | one inspection with answers and punch keys |
| `GET /quality/checklists` | `list_checklists` | `project`, `state`, `discipline`, `limit` | rows and total |
| `GET /quality/checklists/{key}` | `get_checklist` | `project` | one checklist with questions |

A bad state, point, format or limit is 422 (`invalid_argument`). A call with no token is 401; a viewer whose word is withdrawn is 403.
The export route is not read as a key (`/quality/inspections/export` is listed before `/{key}`).

## MCP
Module tool registrar `tl_mcp.insp_tools:register_insp_tools`; each tool is closed until listed for the agent.

| Tool | Kind | Arguments | Result |
|---|---|---|---|
| `list_inspections` | read | `project`, `state`, `point`, `area`, `inspector`, `subject_key`, `for_key`, `limit` (default 50) | rows and page total |
| `get_inspection` | read | `project`, `key` | one inspection |
| `list_checklists` | read | `project`, `state`, `discipline`, `limit` (default 50) | rows and page total |
| `get_checklist` | read | `project`, `key` | one checklist |
| `propose_inspection` | proposal | `project`, `subject_key`, `title`, `point` (required); `for_key`, `area`, `planned_on`, `summary`, `intent` | a pending proposal (a `PlanInspection`) |

No MCP tool schedules, records, verifies, reinspects, cancels or edits. A proposal changes no record until a person with
`quality.inspection.plan` accepts it.

## Module commands and words
Defined in `tl_mod_quality.commands`; listed in `INSP_COMMANDS` (`tl_mod_quality.module`); rules in `actions.RULES`.

| Command | Word | Table word | States it runs from |
|---|---|---|---|
| `CreateChecklist` | `quality.checklist.edit` | user | none |
| `EditChecklist` | `quality.checklist.edit` | user | Draft |
| `PublishChecklist` | `quality.checklist.publish` | controller | Draft |
| `RetireChecklist` | `quality.checklist.publish` | controller | Draft, Published |
| `ReviseChecklist` | `quality.checklist.publish` | controller | Published |
| `PlanInspection` | `quality.inspection.plan` | user | none |
| `ScheduleInspection` | `quality.inspection.plan` | user | Planned, Scheduled |
| `RecordInspectionResult` | `quality.inspection.record` | user | Scheduled |
| `VerifyInspection` | `quality.inspection.verify` | controller | Done |
| `ReinspectInspection` | `quality.inspection.plan` | user | Done, Verified (result reject or conditional) |
| `CancelInspection` | `quality.inspection.cancel` | controller | Planned, Scheduled |

Checklist states: `Draft`, `Published`, `Retired`. Inspection states: `Planned`, `Scheduled`, `Done`, `Verified`, `Cancelled`.
A retired checklist and a cancelled inspection take no further change. Every state command takes `expected_version`.
The `quality.view` word reads both types. Six words are new: see [access words](access-words.md).

## Events and numbering
- Checklist events: `Checklist.Created`, `Checklist.Edited`, `Checklist.Published`, `Checklist.Retired`.
- Inspection events: `Inspection.Planned`, `Inspection.Scheduled`, `Inspection.ResultRecorded`, `Inspection.Verified`, `Inspection.Cancelled`.
- Keys: `<project>-CHK-nnnn` for checklists and `<project>-INS-nnnn` for inspections (`schema/fixtures/numbering/patterns.yaml`).
- A `reject` or `conditional` result raises one `quality.PunchItem` per failed question (`raised_against` the inspection).

## Export columns
`tl insp export` and `GET /quality/inspections/export` have the same rows, in this order: `number`, `subject`, `for`, `point`, `state`,
`result`, `scheduled`, `done`, `inspector`, `punch_count`. CSV writes a header even with no rows; a CSV cell that starts with `= + - @`,
TAB or CR is prefixed with an apostrophe. `punch_count` is the number of punch items the result raised.

## Readiness, scan card, TUI
- Readiness check `inspections_planned` (`tl_mod_quality.checks`; entry point `throughline.readiness_checks`). Answers `n_a`, `blocked`,
  `pending`, `ok`; watches `quality.Inspection`; setting `quality.inspections.required_for_iwp` (default off).
- Scan card: `tl_mod_quality.scan_card`, entry point `throughline.scan_cards` for `quality.Inspection`; answers nothing for a hidden record.
- TUI: palette id `inspections` (`tl_tui.widgets.inspection_log.InspectionLogScreen` and the inspection screen). Log keys `s`, `p`, `m`;
  inspection keys `v`, `r`, `x`, `escape`, `F5`. Text in `tl_tui.inspection_text` (no Textual).

## Not in this reference
Routes and tools for the checklist runner, the checklist screens, the `--answers` export and the design's Later items are not built.
See the runbook's "Not built yet" section.
