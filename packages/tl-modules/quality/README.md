# tl-mod-quality

Purpose: the punch list (brief §9 M5, first slice). One record type, `quality.PunchItem` (`P123-PUN-0001`), raised,
edited, cleared, verified, reopened and voided through six module commands. Human docs: `docs/modules/quality/README.md`
and the runbook `docs/runbooks/punch-list.md`.

## Files
- Schema: `schema/modules/quality/` (`module.yaml`, `punch_item.yaml`, `events.yaml`); workflow
  `schema/fixtures/workflows/quality-punch-item.yaml`; numbering block `PUN` in `schema/fixtures/numbering/patterns.yaml`;
  the seven words in `schema/settings/access-words.yaml`.
- `tl_mod_quality.module:spec` (entry point `throughline.modules`): `PUNCH_COMMANDS` (six `PunchCommand` rows),
  `PROPOSABLE`, `PUNCH_GENERIC_COMMANDS`, `projectors()` (returns `PunchItemProjector`).
- `commands.py`: the six command classes (`RaisePunchItem`, `EditPunchItem`, `ClearPunchItem`, `VerifyPunchItem`,
  `ReopenPunchItem`, `VoidPunchItem`) and their field bounds.
- `handlers/punch.py`, `handlers/common.py`: the six handlers. `actions.py`: `RULES`, `states_for`, `punch_actions`.
  `guards.py`: the void refusal. `errors.py`: `PunchRuleError`, `PunchStateError`, `StaleVersionError`.
- `projectors/`: `PunchItemProjector` (handles `PunchItem.*` only). `names.py`: event, state and word constants.
- `api.py`: `open_punch_for(conn, record_id, *, categories=None, viewer=LOWEST)`, `PunchRef`, `MAX_ROWS` (500).
- `views.py`: `punch_list`, `punch_detail`, `punch_counts` (the read bodies behind the API, CLI, MCP and TUI).
- Tests in `tests/`: `punch_world.py` (shared test world), `test_punch_commands.py`, `test_punch_visibility.py`,
  `test_exclusions.py`, `test_module_spec.py`.

## Record
`quality.PunchItem`, table `cur_quality_punch_item` (generated; never hand-write DDL, use `ddl_for`). The title is the
subject; the envelope description is the detail. Fields: `area`, `system` (text, indexed), `due_on`, `category` (A, B, C;
default B), `assignee` (actor or text), `raised_by`, `source_id` (the record it was raised from, indexed; the
confidentiality subject), `cleared_by`, `cleared_on`, `clear_note`, `verified_by`, `verified_on`, `reopen_count`,
`last_reopen_reason`, `void_reason`. A `raised_against` link runs from the item to its source.

## States and moves
Workflow `quality.punch-item`: `Open`, `Cleared`, `Verified`, `Void`. `Void` is the only terminal state.

| Command | Access word (table word) | From | To | Rule |
|---|---|---|---|---|
| `RaisePunchItem` | `quality.punch.raise` (user) | none | Open | `source` may name a record; the link is `raised_against` |
| `EditPunchItem` | `quality.punch.edit` (user) | Open | Open | Raiser, assignee or a verifier only; at least one field; version checked |
| `ClearPunchItem` | `quality.punch.clear` (user) | Open | Cleared | Needs a note; sets `cleared_by`, `cleared_on` |
| `VerifyPunchItem` | `quality.punch.verify` (controller) | Cleared | Verified | Refused for the person who cleared it (fixed message) |
| `ReopenPunchItem` | `quality.punch.reopen` (controller) | Cleared or Verified | Open | Needs a reason; `reopen_count` + 1; cleared and verified columns reset |
| `VoidPunchItem` | `quality.punch.void` (controller) | Open or Cleared | Void | Needs a reason; no later change is accepted |

`PUNCH_GENERIC_COMMANDS` (`SetPsetValues`, `AddLink`, `AttachFile` and the link commands) are refused on a Void item by `guards.not_void`.
`RULES` in `actions.py` is the one source for each command's access, label and workflow states; a test holds each row's
level equal to the table word of its word.

## Verifier and clearer
The verifier must hold `quality.punch.verify` and must not be the person in `cleared_by`. The clearer is refused with the
fixed text `the person who cleared a punch item may not verify it`. Edit is open to the raiser, the assignee and a verifier
(`only the raiser, the assignee or a verifier may edit a punch item`).

## Visibility
A punch item is hidden when its source record is hidden. The subject join is one row in `SUBJECT_LINKS`
(`tl_core.confidentiality`): `("quality.PunchItem", "cur_quality_punch_item", "id", "source_id")`, followed up to two hops.
A hidden item looks like a missing one: reads and commands return the same text (`no punch item <key>`). Do not give punch
items a class of their own; the source decides.
Source rule: a punch item is raised only from a record that names no subject itself (not a `core.Constraint`, and no
type in `SUBJECT_LINKS`, including another punch item), so a chain of subjects never passes the two-hop join.

## Record shape and Phase 3 compatibility
`quality.PunchItem` (table `cur_quality_punch_item`; title is the subject, envelope description is the detail):
`area`, `system` (text <= 64, indexed), `due_on`, `category` (A, B, C; default B), `assignee` (actor or text <= 120), `raised_by`,
`source_id` (the record it was raised from, null ok, indexed; the confidentiality subject), `cleared_by`, `cleared_on`,
`clear_note`, `verified_by`, `verified_on`, `reopen_count`, `last_reopen_reason`, `void_reason`. A `raised_against` link runs from
the item to its source (the relation Phase 3 uses for `Issue` and `Deficiency`).
How Phase 3 takes it over (roadmap: rework under one point). The Phase 3 Issue engine adds `kind` (`punch`), `response_cycle` and
`escalation_level` as additive columns on the same table and registers `punch` as a kind whose numbering pattern is the existing `PUN`.
Nothing here is renamed:

| Here | Phase 3 (`docs/build-spec/09-phase3-plan.md` I1/I2, `docs/build-spec/module-designs/quality.md`) |
|---|---|
| states `Open`, `Cleared`, `Verified`, `Void` | Deficiency `Open`/`Cleared`; Issue `Verified`; `Void` is the Deficiency's `Cancelled`. Same words, no migration; `Assigned` and `Fixed` stay fields, not states (an assignment is an event, as `Issue.Assigned` is) |
| `assignee`, `due_on`, `source_id` + `raised_against` link | Issue `owner`, `due_on`, `raised_against` links |
| `category` A/B/C | Deficiency `category` (Phase 4 "punch A closed" checks) |
| events `PunchItem.Raised/Edited/Cleared/Verified/Reopened/Voided` | `Issue.Raised/Assigned/Dispositioned/Reopened/Closed`: the Issue engine emits its own events beside these; a rule or projector maps by record type |
| `quality.punch.*` access words | the Issue engine's words; the punch words stay |
| `area`, `system` text | Phase 4 links to `System` and `Subsystem` records; the text stays as the display code |

The module is `quality`, so Phase 3 adds its classes to the same schema directory and the same `ModuleSpec`.

## Surfaces (as built)
- CLI: `packages/tl-cli/src/tl_cli/punch.py` (group), `punch_write.py` (`raise`, `edit`, `clear`, `verify`, `reopen`,
  `void`), `punch_read.py` (`ls`, `show`).
- API: `packages/tl-api/src/tl_api/routes/punch.py`: `GET /projects/{project}/punch`, `GET /projects/{project}/punch/{key}`,
  `GET /projects/{project}/punch-counts`.
- MCP: `packages/tl-mcp/src/tl_mcp/punch_tools.py`: `list_punch_items`, `get_punch_item` (read-only) and
  `propose_punch_item` (proposes a `RaisePunchItem`; a person accepts it). No MCP tool clears, verifies, edits, reopens
  or voids.
- TUI: `packages/tl-tui/src/tl_tui/punch_text.py` (text, no Textual), `widgets/punch_log.py` (`PunchLogScreen`,
  `PunchScreen`); palette id `punch`.
- Demo `dev/demos/P2-PUNCH.sh`; generator `dev/seed/demo_project/quality.py`.

## Inspections and checklists (as built, P2-INSP slice 1)
Design: `docs/build-spec/module-designs/inspections.md`. Runbook: `docs/runbooks/inspections.md`. Reference: `docs/reference/inspections.md`.
Words: `quality.checklist.edit`, `quality.checklist.publish`, `quality.inspection.plan`, `quality.inspection.record`,
`quality.inspection.verify`, `quality.inspection.cancel` (in `schema/settings/access-words.yaml`); reads need `quality.view`.

- Schema: `schema/modules/quality/checklist.yaml`, `inspection.yaml`; workflows `schema/fixtures/workflows/quality-checklist.yaml`,
  `quality-inspection.yaml`; numbering `CHK` and `INS` (`P123-CHK-0001`, `P123-INS-0001`) in `schema/fixtures/numbering/patterns.yaml`.
- `commands.py`, `module.py`: `INSP_COMMANDS` (eleven commands; `QUALITY_COMMANDS` is the punch six plus these). `PROPOSABLE` adds
  `propose_inspection` (a `PlanInspection`). `handlers/checklist.py`, `handlers/inspection.py`; `actions.py` `RULES` gives each move's states.
- `insp_rules.py`: `result_of` (pure: `reject` when a required question fails, `conditional` when an optional one does, else `accept`)
  and the answer checks, shared by the handler, the CLI and the TUI. `insp_views.py`: the reads under `viewer=`.
- `checks.py`: the readiness check `inspections_planned` (entry point `throughline.readiness_checks`; watches `quality.Inspection`).
- `scan_card.py`: the scan card of `quality.Inspection` (entry point `throughline.scan_cards`).

**Checklists.** `Draft` → `Published` → `Retired`. Edit needs Draft; publish refuses an empty or malformed list. Revise copies a Published
checklist as a new Draft with the next version and `supersedes_id`; publishing the revision retires the version it replaces. A Published
checklist never changes.

**Inspections.** `Planned` → `Scheduled` (schedule pins the published checklist version) → `Done` (record computes the result) →
`Verified` (by a controller who did not record it). `Cancelled` from Planned or Scheduled. Reinspect plans a new inspection from a Done
or Verified one with `reject` or `conditional`. A `reject` or `conditional` result raises one punch item per failed question in the same
unit of work, linked `raised_against` the inspection; a failed required question on a hold point is category A, else B.

**Visibility.** An inspection is hidden through its subject (the `SUBJECT_LINKS` row for `quality.Inspection`, two hops at most). A hidden
inspection answers `no inspection <key>`, with the same text and count as a missing one. Checklists carry no project text and are readable
with `quality.view`. `for_iwp_id` is not part of the chain.

**Agents.** No agent tool plans, schedules, records, verifies, reinspects or cancels. `propose_inspection` files a pending proposal; a person
who holds `quality.inspection.plan` accepts it, and the inspection is planned as that person.

**Readiness.** `inspections_planned` answers `n_a`, `blocked`, `pending` or `ok` as in the design, section 5. Done and Verified count as
done; Cancelled counts in neither number; a conditional hold point does not block.

## Package rules
The rules of the root `AGENTS.md` apply, and the local rules in `AGENTS.md` in this directory. In short: no business
logic in screens (they call the same commands and views the API uses); every read takes keyword `viewer=`, default
`confidentiality.LOWEST`, never the ambient viewer; each move is a module command (`by_module=True`).
