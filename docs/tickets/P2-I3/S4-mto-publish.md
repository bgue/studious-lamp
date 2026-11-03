# P2-I3-S4 — MTO publish target, AssignMtoLines, compensation refusals

Status: ready (re-scoped r4: the first attempt stopped Blocked on the documents pipeline; orchestrator approved the documents change under P2-Q10, APPROVALS entry at merge)
Tier: sonnet
Kind: piece
Review: full
Labels: core-module
Depends on: S2, S3 (merged); W0-B2 publish targets (on the trunk).
Branch: `p2/i3-s4-mto` (exists at c3398e0 with the Blocked report only; the orchestrator merges `p2/i3` into it before the run)

## Goal
A derived `mto` document can be published into a `materials.MTO` with its `materials.MTOLine`s through the documents
module's publish pipeline (ADR-0014), compensated, and republished; a user can assign lines to a work package. S2 already
projects `MTO.Defined`, `MTOLine.Defined`, `MTOLine.Assigned` (`projectors/mto.py`) and splats `MTO_COMMANDS` / `MTO_RULES`
from `mto.py`; this piece fills those two names.

## Brief references
`docs/build-spec/specs/m4-materials.md` §2 (MTO, MTOLine rows; Links), §3 (rows `PublishDerivedMto`, `AssignMtoLines`; the
compensation sentence), §6 (MTOLine rows: `RULES` rows are S3's `actions.py`, you export `MTO_RULES`), §8, §9 row S4.
`docs/build-spec/specs/wave0.md` §2 (W0-B2: `throughline.publish_targets`, the `PublishTarget` protocol in
`tl_mod_documents/derivation/publish_targets.py`). `docs/adr/0014-*` (derivation pipeline). Pattern: `tags_target` and
`documents_target` in `tl_mod_documents/derivation/publish.py`; the schema-side `mto` kind of P1-I3 (derived document schema with
`target_kind: mto`).

**Decisions (orchestrator, 2026-11-01)**
1. *Files.* In materials you own only `tl_mod_materials/mto.py`, `handlers/mto.py`, the package `pyproject.toml` (one
   `[project.entry-points."throughline.publish_targets"]` line: `mto = "tl_mod_materials.mto:mto_target"`), and the report and acceptance
   script. S3 (merged) owns `errors.py`, `commands.py`, `module.py`, `views.py`, `actions.py` and the `tl_api` glue: do not edit them. The documents files of decision 5 are the only other source files. **No new `ServiceError` class:** the supervisor
   added `MtoPublishRefusedError`, `MtoLineNotFoundError`, `MtoLineInUseError`, `WorkPackageNotFoundError` to `errors.py` (use them; reuse S2's
   `InvalidQuantityError`, `ItemNotFoundError`, `InvalidValueError`). A class you cannot do without is a Blocked question.
2. *Commands.* `MTO_COMMANDS = (CommandSpec(PublishDerivedMto, ..., "materials.mto.publish"), CommandSpec(AssignMtoLines, ...,
   "materials.mto.assign"))`; `MTO_RULES` carries the "no reservation" MTOLine row of spec §6. `actions.py` (S3, merged) imports `mto.py`, so you cannot
   import its `Rule`: define a small frozen dataclass `MtoRule` in `mto.py` with the fields `record_type, condition, label, command, word` (the names
   `actions.rule_rows()` reads by shape): `materials.MTOLine`, `no reservation`, `Assign to work package`, `AssignMtoLines`, `materials.mto.assign`.
   The "Reserve from a lot" row is S3's.
3. *Work package check by type string.* `work_package_number` resolves to an `awp.CWP` or `awp.IWP` record in the project by key and
   `type` column of `cur_core_record`; no import of an awp module. Unknown: `WorkPackageNotFoundError`. When P2-I1 is not on the trunk
   the acceptance seeds a CWP record by hand-appended events of type `awp.CWP` (as S2.py replays events) and says so in the report.
4. *Create-only publish.* Existing `ISO-1234@A/MTO` and `skip_existing`: rows already published are skipped and counted, never changed. Each
   line: `project_item_id` by item code (adopt-on-publish is NOT done: an unadopted code is a plan problem naming the row number),
   `qty` (spec bounds, `Decimal`), `uom` equal to the item's, optional tag reference (link `references` to an `engineering.Tag` if the key
   exists), `work_package_id` when a number is given. Links as spec §2 Links (module-written, source `import`). Compensation goes through the
   reverse hook of decision 5(a): the target refuses with `MtoLineInUseError` text in `problem` when any line has `reserved_qty > 0` or
   `issued_qty > 0`, else its `reverse` voids the lines and then the MTO (`compensate_mto`).
5. *Documents change (orchestrator APPROVES under P2-Q10; minimal and generic; documents never imports materials).* Three parts, all in
   `tl_mod_documents/derivation/`; tags and documents targets keep their behaviour byte for byte:
   (a) *Reverse hook.* An optional part of the `PublishTarget` protocol (`publish_targets.py`), for example `compensation_item(conn, record_id, scope)
   -> (reversible: bool, problem: str | None)` and `reverse(uow, base, record_id, reason)`. `publish.py` `_record_item` and
   `handle_compensate_publication` / `preview_compensation` look the record type up in `publish_targets()` before the `reversible=False` fallback and
   call the hook; `tags` and `documents` stay on their own code. A target without the hook is as before (not reversible).
   (b) *Mapping.* `mapping.check_mapping` accepts any name in the `publish_targets()` registry instead of the closed `names.TARGET_KINDS` literal; the
   allowed mapping fields of a registered target other than tags/documents come from the target (for example a `mapping_fields` attribute that
   `mto_target()` sets to the columns the plan reads). `TARGET_KINDS` stays for tags/documents or is derived; nothing else reads it differently.
   (c) *Schema.* `schemas.py:77` `target_kind` widens from `Literal["tags", "documents"] | None` to `str | None`, with one schema-check problem when the name
   is not in `publish_targets()`.
   Then `uv run python -m tl_api.openapi` regenerates `docs/reference/openapi.json` (S3 moved it there; the orchestrator regenerates again at merge).
   Pins that break only because the field is now a string or the hook exists are consequential pins (list them in the report). The schema YAML only
   describes the field in prose, so no `just gen` change; if one is needed, Blocked. Acceptance defines the `mto` document schema (with a mapping)
   through the documents command, not by hand-appended events. Any other documents gap (the private `_Creatable`/`_Built` types are not one: return
   `PlanRow` and your own creatable objects, the protocol types them `Any`) is Blocked.
6. *AssignMtoLines* `{mto_lines[<=500], work_package_number}`: one `MTOLine.Assigned` per line, all or nothing; refused with
   `MtoLineInUseError` when a line has reservations; `materials.mto.assign` (user).

## Interfaces (keep these names)
- `mto.py`: `MtoRule`, `MTO_COMMANDS`, `MTO_RULES` (replace the empty tuples), `mto_target() -> PublishTarget` (`name = "mto"`, `module = "materials"`,
  `record_type = "materials.MTO"`, plus the hook and mapping fields of decision 5).
- `handlers/mto.py`: `PublishDerivedMto`, `AssignMtoLines` models, `handle_publish_derived_mto`, `handle_assign_mto_lines`,
  `compensate_mto(uow, ...)`.
- Public helper S3's readiness and views read: none; the tables are S2's.

## Context (<= 10 files)
- the Brief references; `packages/tl-modules/materials/src/tl_mod_materials/{mto.py,common.py,registry.py,handlers/po_lines.py,projectors/mto.py}`
- `packages/tl-modules/documents/src/tl_mod_documents/derivation/{publish_targets.py,publish.py,mapping.py,names.py,schemas.py}` (`tags_target`, `documents_target`, `_record_item`, `check_mapping`)
- `packages/tl-modules/materials/src/tl_mod_materials/{errors.py,actions.py}` (read only: the four MTO errors; `rule_rows`)
- `schema/modules/materials/mto.yaml`, `schema/modules/materials/events.yaml`
may explore: `dev/accept/P2-W0/*.py` (publish-target acceptance), `dev/accept/P2-I3/S2.py` (ledger setup and event replay)

## Allowed paths
- `packages/tl-modules/materials/src/tl_mod_materials/mto.py`, `handlers/mto.py` (create)
- `packages/tl-modules/materials/pyproject.toml` (the one entry-point line)
- `dev/accept/P2-I3/S4.py` (create), `docs/reports/P2-I3/S4.md` (create)
- `packages/tl-modules/documents/src/tl_mod_documents/derivation/{publish_targets.py,publish.py,mapping.py,names.py,schemas.py}` (decision 5 only)
- `docs/reference/openapi.json` (regenerated)
- consequential pins (an entry-point listing, a `TARGET_KINDS` or schema-type test) and documents derivation tests that pin the closed set: update and list them in the report
Not here: every other file of the materials package, `tl_api/**`, `schema/**`, other `documents/**` files (any other gap in the pipeline is Blocked).

## Acceptance (run once; no pytest; tests are T11's)
```
uv sync --all-packages
export NODE_OPTIONS=--max-old-space-size=6144
just check
uv run python dev/accept/P2-I3/S4.py
just gate packages/tl-modules/documents packages/tl-modules/materials packages/tl-api/tests/test_error_table.py tests/services
```
`S4.py` (SQLite, then `TL_PG_URL` when set; exit 0; one `PASS <check>` each; from spec §2/§3, not from your code): `mto` is listed among the publish
targets with module `materials`; a derived `mto` document of 3 rows (items from the library, one with a tag key) publishes: one MTO `ISO-1234@A/MTO`,
lines `…/001..003`, `line_count` 3, links present; a second publish with `skip_existing` creates 0 and counts 3 skipped; an unadopted item code and a
uom mismatch are plan problems naming row numbers and no cell text; `AssignMtoLines` sets the work package, is refused for an unknown number and a
line with a reservation (append a `Moved` reserve by hand), and all-or-nothing; compensation with a reservation or an issue refused with the fixed
message and nothing changes; compensation without removes MTO and lines; republish after compensation creates them again; a user without
`materials.mto.publish` is refused through the command's word; `tags` and `documents` targets still publish and compensate (one smoke each, as the W0 acceptance does);
an `mto` mapping naming a column the target does not offer is refused by `check_mapping`.

## Tests to add
None (deferred to T11: `test_mto.py`).

## Mutation guards (sentinel + at most 5; report in 3 lines, `file:line` each, for T11)
Create-only (skip_existing counted as created); `check_mapping` accepting an unregistered name; compensation refusal on reserved (`> 0` to `>= 0` / removed); refusal on issued; assign refusal with
reservation; word of `PublishDerivedMto` swapped to `materials.mto.assign`.

## Report requirements
Piece report (<= 60 lines): deviations first; pins changed; acceptance output (<= 5 lines per command); builder return <= 15 lines in Code 92.
Commit subjects `P2-I3-S4: ...`; the commit trailer is the attribution lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`; do not discuss the trailer. No model names in any committed file.

## Escalation triggers
Stop and write *Blocked* if: the documents change needs more than decision 5 (a file outside the five, a changed behaviour of the tags or documents targets); a `ServiceError` class beyond the four is needed; the work-package type string cannot be read from `cur_core_record`.

## Blocked
(builder writes here)
