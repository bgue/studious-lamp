# P2-PUNCH-S1 — quality schema and module spec: `quality.PunchItem`

Status: ready (dispatch round 2; human gate)
Tier: builder
Kind: piece
Review: full
Labels: schema, core
Depends on: trunk @bb6f855b
Branch: `p2/punch-s1-schema`
Worktree: `/home/user/wt/punch-s1`
Approver (schema): orchestrator (P2-Q10; line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the LinkML under `schema/modules/quality/` holds `PunchItem`; one workflow, one numbering pattern, the events,
the offline class and seven access words are fixtures; the new package `packages/tl-modules/quality` (`tl-mod-quality`, Python
package `tl_mod_quality`) exists with a `ModuleSpec` that registers the record type and its projector; the four consumer packages
(`tl-api`, `tl-cli`, `tl-mcp`, `tl-tui`) depend on it; generated models, DDL and every pinned list are current. No command exists
yet (S2). The Haiku tickets start from S2, not from this.

## Brief references (pasted; `docs/tickets/P2-PUNCH/README.md` "Record shape" is authoritative)
Project scope, confidentiality `internal`, no `ConfidentialSource` (a punch item is hidden through its source, S2). Dates `YYYY-MM-DD`.
Copy conventions from `schema/modules/materials/*.yaml` and `schema/modules/awp/iwp.yaml` (identifier `id`, `scope`, `tl:table`,
`tl:ix_*`, `tl:current_state`, `tl:record_types`).
| Class | Fields (table `cur_quality_punch_item`) |
|---|---|
| `quality.PunchItem` (id, scope, then) | `area` (<= 64), `system` (<= 64), `due_on` (date), `category` (enum `PunchCategory` A, B, C; default B), `assignee` (<= 120), `raised_by` (actor text <= 64), `source_id` (record id, null ok), `cleared_by` (<= 64), `cleared_on` (date), `clear_note` (<= 300), `verified_by` (<= 64), `verified_on` (date), `reopen_count` (int >= 0, default 0), `last_reopen_reason` (<= 300), `void_reason` (<= 300). Indexes: `tl:ix_*` on `source_id`, `area`, `system`, `due_on`. The record's title is the subject (<= 200) and its description the detail (<= 1000), both on the envelope |
**Numbering** (`schema/fixtures/numbering/patterns.yaml`, one block, `gap_free: true`): id `quality.PunchItem`, record type
`quality.PunchItem`, scope `"project:*"`, template `"{project}-{type}-{seq:4}"`, `type_code: PUN`: `P123-PUN-0001`.
**Workflow** `schema/fixtures/workflows/quality-punch-item.yaml` (record type `quality.PunchItem`; no `roles` guard; every move a
module command with `by_module=True`; explicit initial state `Open`, as the requisitions work order has): `Open -> Cleared`,
`Cleared -> Verified`, `Cleared -> Open` and `Verified -> Open` (reopen), `Open -> Void`, `Cleared -> Void`. Terminal: `Void` only.
`Open -> Verified`, `Verified -> Void` and any move out of `Void` are not moves. No constraint opt-in guard (nothing is gated on a
punch item here; ADR-0024: a blocking constraint cannot be raised on it, an advisory one can).
**Events** (`schema/modules/quality/events.yaml`, each with `tl:event_type`, payload classes generated; every event carries
`feed_policy: none` as the awp quiet events do, so no feed card and no core change): `PunchItem.Raised` (flat: all fields of the
raise), `PunchItem.Edited` {changes: {field: [old, new]}}, `PunchItem.Cleared` {by, note, at}, `PunchItem.Verified` {by, at},
`PunchItem.Reopened` {by, reason}, `PunchItem.Voided` {by, reason}. Every payload names `record_id`. **Valid time (ADR-0026):** tag
`at` of `Cleared` and `Verified` with `tl:valid_time: at`; any payload class this piece adds that stays untagged goes into
`tests/tools/valid_time_baseline.toml` with a one-line reason (`due_on` is a plan, not valid time).
**Offline class** (`docs/build-spec/specs/offline-classes.md`): `quality.PunchItem` is `draft_only` (a walkdown raises offline); add the
row to that page.
**Access words** (`schema/settings/access-words.yaml`, new `quality:` block): `quality.view: read`, `quality.punch.raise: user`, `quality.punch.edit: user`,
`quality.punch.clear: user`, `quality.punch.verify: controller`, `quality.punch.reopen: controller`, `quality.punch.void: controller`. Exactly seven; an
assignment is an edit, so there is no assign word. **No setting is added** (`platform.yaml` is untouched).
`module-roles.yaml` is not edited (the demo and the generator grant the superuser role).

## Interfaces (verbatim shapes to copy; open these)
- Module and spec: `packages/tl-modules/materials/src/tl_mod_materials/{module,names,projectors/__init__}.py`, `packages/tl-modules/materials/pyproject.toml`
  (entry point `throughline.modules`; `[project.entry-points]` only that one).
- Projector pattern: one record projector writing the `cur_quality_punch_item` row from `Record.Created` and `PunchItem.*`, calling `touch_record`, as `MtoProjector`; on `Reopened` the projector sets `cleared_*` and `verified_*` to null, adds one to `reopen_count`, stores `last_reopen_reason`; on `Cleared`/`Verified` it stores `by`, `at` (date part) and the note.
- Workflow file shape: `schema/fixtures/workflows/materials-receipt.yaml`, `awp-iwp.yaml`.

## Context (<= 10 files)
`schema/modules/materials/{module,receipt,events}.yaml`; `schema/fixtures/workflows/materials-receipt.yaml`;
`schema/fixtures/numbering/patterns.yaml` (the `awp.IWP` and `awp.ScopeItem` blocks); `schema/settings/access-words.yaml` (head and the awp block);
`packages/tl-modules/materials/src/tl_mod_materials/{module,names}.py`; `docs/build-spec/specs/offline-classes.md`; `docs/adr/0010-module-record-storage.md` (Decision 1-3).
may explore: `docs/reports/P2-I3/S1.md`, `docs/reports/P2-I2/S1.md` (its "Pinned lists updated" list).

## Allowed paths
- `schema/modules/quality/**` (create `module.yaml`, `punch_item.yaml`, `events.yaml`)
- `schema/fixtures/workflows/quality-punch-item.yaml` (create); `schema/fixtures/numbering/patterns.yaml` (one block added)
- `schema/settings/access-words.yaml` (the `quality:` block); `tests/tools/valid_time_baseline.toml` (lines added); `docs/build-spec/specs/offline-classes.md` (one row)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only)
- `packages/tl-modules/quality/**` (create: `pyproject.toml`, `README.md`, `AGENTS.md`, `src/tl_mod_quality/{__init__,module,names,projectors/__init__}.py`, `src/tl_mod_quality/py.typed`, `tests/__init__.py`, `tests/test_module_spec.py`)
- root `pyproject.toml` (workspace source line `tl-mod-quality`, the test path `packages/tl-modules/quality/tests` next to the materials one, the dependency line) and `uv.lock`; the `dependencies` list of `packages/tl-api/pyproject.toml`, `packages/tl-cli/pyproject.toml`, `packages/tl-mcp/pyproject.toml`, `packages/tl-tui/pyproject.toml` (one line each, `"tl-mod-quality"`, as `tl-mod-materials` is)
- pinned lists (rule 12), union form, each listed in the report: `packages/tl-schema/tests/test_offline_classes.py` (49 -> 50), `test_ddl.py`, `test_generate.py`, `test_ddl_views.py` (a view if the generator makes one per class), `packages/tl-core/tests/auth/test_access_words.py` (28 -> 35: add the `QUALITY` set to the sum), `packages/tl-core/tests/test_numbering_config.py` (pattern list), `tests/services/test_modules.py` (module list: `"quality"` after `"materials"`), and any other test that fails only because these exist (find with `grep -rln "materials.StockLot" tests packages/*/tests packages/tl-modules/*/tests`)
- `packages/tl-schema/tests/test_quality_schema.py` (create), `dev/accept/P2-PUNCH/S1.py`, `docs/reports/P2-PUNCH/S1.md` (create)
Not allowed: commands or handlers, `tl_core/**` (including `tl_core/feed/cards.py`), other modules, any other `tl-api`, `tl-cli`, `tl-tui`, `tl-mcp` file.

## Steps
1. LinkML, fixtures, access words; `just gen`; commit schema and generated output together.
2. Package skeleton: `names.py` constants (type, table, events, workflow id), projector, `module.py` `spec` with the record type, the projector, offline drafts empty, and `PUNCH_COMMANDS = ()` (S2 fills it); workspace lines and the four dependency lines; `uv sync --all-packages`.
3. Fix pinned lists that fail only because these exist. Then the tests and the acceptance script.

## Acceptance (run once each; one package per gate, pinned-list files named, never the whole suite)
```
just gen
just check
uv run python dev/accept/P2-PUNCH/S1.py
just gate packages/tl-schema/tests
just gate packages/tl-modules/quality/tests tests/services/test_modules.py tests/webhooks packages/tl-core/tests/auth/test_access_words.py packages/tl-core/tests/test_numbering_config.py
```
`S1.py` (SQLite, dialect-neutral, one `PASS <check>` line per check, final `S1 ok`): the type is in `TYPE_LABELS` ("Punch item") and
`OFFLINE_CLASSES` (`draft_only`); the table and its four indexes are in the generated DDL; the workflow loads, `Void` is the only terminal state,
`Open -> Verified`, `Verified -> Void` and `Void -> Open` are refused, `Cleared -> Open` and `Verified -> Open` are allowed; the pattern allocates
`P123-PUN-0001` then `-0002` and is gap-free; no transition carries a guard; every event has `tl:event_type` and `feed_policy: none`; `Cleared.at` and
`Verified.at` are valid-time tagged; each of the seven words resolves to its table word; the module spec loads through `tl_core.modules` and a punch item
round-trips through its projector from a hand-written `Record.Created` plus `PunchItem.Raised`, `Cleared`, `Reopened` (cleared columns null, `reopen_count` 1).
Tests to add (the builder writes them): `packages/tl-schema/tests/test_quality_schema.py` (type and label, table columns by name and length, category enum A/B/C, workflow moves
above, pattern, words, events, valid-time tags) and `packages/tl-modules/quality/tests/test_module_spec.py` (spec loads, zero commands, projector round trip).

## Mutation (sentinel + <= 5 mutants, in this worktree, 3 lines in the report)
Guards: `Void` terminal; `Open -> Verified` refused; `gap_free` on the pattern; `reopen_count` reset on projection; the `category` enum. Name file:line for each.

## Report requirements
Standard piece report (<= 60 lines): deviations first; files; pinned lists updated and why; acceptance output (<= 5 lines per command); words as built (name -> table word); events and fields added or dropped; the valid-time outcome; mutation 3 lines.

## Commit
`P2-PUNCH-S1: <imperative summary>`; body says what and why; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: `just gen` changes a non-quality generated file other than the all-module registries; a core pinned list (`POLICY_EVENT_TYPES` in `tl_core/feed/cards.py`) rejects the quiet events (do not edit core; write which); an access word needs a table word the roles MVP lacks; `tests/tools/valid_time_baseline.toml` is missing; a pinned-list change goes beyond a name added.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
