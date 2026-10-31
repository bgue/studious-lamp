# P2-W0-T10 (DOC-2) — Docs for load targets, offline classes, readiness and the module-design table

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: W0-B1, W0-B2, OC-S1, OC-S2, T04, T05 (merged)
Branch: `p2/w0-t10-docs-targets-offline`

## Goal
The legacy-load runbook explains load targets by entry point; the `tl-core` README names the new modules; the module-design README lists
the offline class and the built state of roles and the readiness contract.

Do not discuss the commit trailer in the report; no model names anywhere in committed files.

## Brief references (pasted, abridged)
- Load targets: group `throughline.load_targets`; built-ins `tags` and `documents` (project scope), registered in
  `packages/tl-modules/legacy/pyproject.toml`. `uv run tl load targets` prints `name  module  scope` per target. `tl load open` takes exactly
  one of `--project P` (project target) or `--company` (company target); loads stay admin-only. A duplicate target name is a
  `ModuleLoadError`; an unknown name is refused at `open`. A generic column-mapping form exists for module targets. Publish targets
  (derived documents) use group `throughline.publish_targets` with the same two built-ins; create-only and compensation unchanged (ADR-0014).
- Offline classes: every record type carries `tl:offline` in its LinkML class: `full` (edited offline, merged), `draft_only` (drafted
  offline, issued online), `none` (online only). The generated table is `OFFLINE_CLASSES` (`generated/offline_classes.py`, human page
  `generated/docs/offline-classes.md`). `tl_core.offline.capture_allowed(type, command, node=...)` decides; a `controller`, `admin` or
  `company` command is never captured offline; `authority` nodes allow everything. `GET /record-types` lists the classes; the record screen
  shows an `Offline class` row in technical mode (Ctrl+D) only. Modules declare `ModuleSpec.offline_drafts`. A node kind other than
  `authority` stops start-up (`TL_NODE_KIND`) until Phase 3. `tl new record-type` writes `tl:offline: none` and a reason comment.
- Readiness: `tl_core.readiness` has the frozen contract types, `load_checks()` (entry-point group `throughline.readiness_checks`, empty today)
  and `check_readiness_contract` (the harness). Reserved: correlation prefixes `ready:`, `rollup:`, `progress:`; source prefix `job:`.
  Eleven new settings keys (`awp.*`, `materials.receipt.mtr_required_categories`, `scaffold.inspection.interval_days`) are in `platform.yaml`.
- Module roles: see `docs/runbooks/accounts-and-access.md` (T09 writes the section; link to it, do not duplicate).

## Context (read these, nothing else)
- `docs/runbooks/legacy-load.md` (63 lines)
- `packages/tl-core/README.md` (160 lines; the rule is about 150, so you add at most 12 lines and tighten two existing lines if needed)
- `docs/build-spec/module-designs/README.md` §3 table only (lines 54 to 75)
- `docs/templates/runbook.md`, `docs/templates/package-readme.md`
may explore: `docs/reports/P2-W0/{W0-B2,OC-S2,W0-B1}.md`

## Allowed paths
- `docs/runbooks/legacy-load.md` (modify: a "Load targets" step list; `tl load targets`; `--company`; adding a target by entry point)
- `packages/tl-core/README.md` (modify: one short section each, "Module roles (`tl_core.auth.module_roles`)", "Offline classes
  (`tl_core.offline`)", "Readiness contract (`tl_core.readiness`)"; update "Depends on / used by" only if a line is now wrong)
- `docs/build-spec/module-designs/README.md` (modify §3 only: add a row `Offline` (state: built, wave 0; where: `tl_core/offline.py`,
  `tl:offline`, `offline-classes.md`; assumption: every design names its class per type and `offline_drafts`); change the row `Access and
  roles` to say module roles are built (viewer, user, superuser per module, derived from the account role, access words as data); change the
  row `Readiness engine` state to "contract, loader and harness built (P2-W0); engine and subjects designed")
- `docs/reports/P2-W0/T10.md` (create)

## Rules (throughline-docs)
Purpose in the first sentence; tables for parallel facts; commands copy-pasteable; link, do not duplicate; no secrets; ISO dates; keep each
table row on one line like its neighbours.

## Acceptance
```
just check
uv run tl load targets
wc -l packages/tl-core/README.md
```
Expected: `just check` clean; the targets output lists `documents` and `tags`; the README is at most 160 lines (report the number; a larger
count is a *Deviation*).

## Tests to add
None (docs).

## Report requirements
Standard report (`docs/templates/haiku-report.md`): the three outputs, files changed. Deviations first.

## Escalation triggers
- A statement above does not match the tree (report which); the README cannot stay within 160 lines without deleting existing content.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
