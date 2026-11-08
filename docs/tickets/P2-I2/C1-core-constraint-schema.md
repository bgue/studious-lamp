# P2-I2-C1 — Core constraint schema (ADR-0024)

Status: ready (dispatch r3)
Tier: builder
Kind: piece
Review: full
Labels: schema, core
Depends on: S1, S2 (merged); ADR-0024 v2 (read it first; it is the spec of record for every name below)
Branch: `p2/i2-c1-constraint-schema`
Worktree: `/home/user/wt/i2-c1` (from `p2/i2` head)
Approver (schema): orchestrator (P2-Q10; line in `docs/reports/APPROVALS.md` at merge). ADR-0024 status moves to accepted at the C2 merge.

## Goal
After this piece the core schema holds `core.Constraint` (a record with a typed table), its events, the workflow
`core.constraint`, the `targets` relation, two access words and a new guard kind in the workflow definition model; the CWP and
IWP workflows carry the opt-in guard lines; `awp.Constraint` and the awp constraint commands are gone, and the tree is green. No new
command exists (C2). The frozen function stub `tl_core/constraints/__init__.py` stays as it is.

## Brief references (ADR-0024, pasted in short)
- Record `core.Constraint`, `cur_core_constraint`, numbered `{project}-CON-{seq:4}` gap-free, offline `draft_only`, confidentiality
  taken from the subject by join (no `ConfidentialSource` copy; if the schema needs a declaration, make it a join to the subject
  record, and STOP if the model cannot express that: write it under Blocked).
- Fields: `subject_id` (Ulid, any record), `phase` (`^[a-z][a-z0-9_]{0,31}$`), `severity` (`blocking|advisory`), `category` (list
  `materials labour scaffold equipment permit engineering rfi predecessor other`; a code list `ConstraintCategory` replaces awp
  `ConstraintType`), `owner` (actor text `user:<name>`, optional), `description` (<= 500, column `description_text`), `source`
  (`manual check rule feed_hold thread_hold`), `check_name` (<= 64), `suppress_hash` (sha256), `clear_reason` (<= 300),
  `target_kind` (`record|reference`, optional), `target_id` (Ulid, optional), `target_ref_type` (`purchase_order labour_requisition
  scaffold_requisition equipment permit other`), `target_ref_text` (<= 60), `effective_at`, `due_at`, `cleared_at` (world-time
  texts: date or UTC timestamp, as awp `need_by`/`raised_at` did), `cleared_by`. No `facts_hash` column: the raise event carries it, as S2 did.
- Events (each with `tl:event_type`, feed `Raised` and `Cleared` ordinary, others per awp rows): `Constraint.Raised` {constraint_id,
  subject_id, phase, severity, category, source, owner?, description?, check_name?, facts_hash?, effective_at?, due_at?, target_kind?,
  target_id?, target_ref_type?, target_ref_text?}, `Constraint.Assigned` {constraint_id, owner}, `Constraint.Cleared` {constraint_id,
  cleared_at, cleared_by, reason, resolved_by?, suppress: bool}, `Constraint.Withdrawn` {constraint_id, reason}. The awp events of these
  names are removed from `schema/modules/awp/**` (the same names move to core; check `tl:event_type` stays unique).
- Workflow `schema/fixtures/workflows/core-constraint.yaml` (from `awp-constraint.yaml`): Open -> Assigned -> Cleared; Open -> Cleared;
  any but Cleared -> Withdrawn (replaces Void); no guards. Record type `core.Constraint`.
- Numbering: move the `awp.Constraint` block in `schema/fixtures/numbering/patterns.yaml` to `core.Constraint` (same pattern).
- Relation `targets` (inverse `targeted_by`, label `targets` / `targeted by`) in `tl_core/links/vocabulary.py`
  (`blocks` and `resolves` exist). Pinned vocabulary tests change by the name added only.
- Access words (`schema/settings/access-words.yaml`): add `core.constraint.edit` = user and `core.constraint.view` = read; remove
  `awp.constraint.edit` (S2 added it). Fix the pinned count in `packages/tl-core/tests/auth/test_access_words.py` (union form).
- Guard kind, in `tl_core/workflow/definition.py` and the loader only (evaluation is C2): `NoOpenBlockingConstraintsGuard`
  `{kind: no_open_blocking_constraints, phase?: str}` joins `Guard`; the loader checks `phase` matches the phase pattern; docstring table row.
  The engine's `_evaluate` must not crash on it: add a branch returning a passed `GuardResult` with message
  `constraint guard not evaluated` (C2 replaces it). <= 30 lines of core Python in all.
- Opt-in lines: `awp-cwp.yaml` `start_execution` and `complete`: `guards: [{kind: no_open_blocking_constraints}]`; `awp-iwp.yaml`
  `ready`: `{kind: no_open_blocking_constraints, phase: ready}`; `start` and `complete`: the same with the default phase. No other transition changes.
- Remove: `schema/modules/awp/constraint.yaml`, `schema/fixtures/workflows/awp-constraint.yaml`, the awp constraint events and imports, the
  `ConstraintType` list if nothing else uses it (check the standards fixture), generated outputs (via `just gen`).
- Remove from `packages/tl-modules/awp/**` (pure deletion, the tree must stay green): `RaiseConstraint`, `AssignConstraint`,
  `ClearConstraint`, `VoidConstraint` models and `AWP_COMMANDS` rows, `handlers/constraint.py`, `projectors/constraint.py`, `constraints.py`,
  `RULES` rows, names, errors and `module.py` entries that only they use, constraint checks in `tests/s2_checks.py` and `tests/awp_world.py`,
  the constraint part of `dev/accept/P2-I2/S2.py` (keep its IWP and scope checks, and the seed minus constraints) and `S1.py` where it names
  `awp.Constraint`. `facts.py` and the readiness contract do not mention constraints; leave them. Matching `tl_api/errors.py` rows go; pinned
  command counts and the `controller` set shrink (union form is not possible for a removal: write the exact new numbers and say so in the report).
  The S2 code is reference for C2: `git show d2409f5:packages/tl-modules/awp/src/tl_mod_awp/constraints.py` (and `handlers/constraint.py`).
  Other awp/TUI/CLI code that names the constraint (`packages/tl-cli/src/tl_cli/awp_{read,write}.py`, `tl_tui/awp_text.py`, `package_text.py`,
  `widgets/package_log.py`, `feed_pane.py`, `tl_lake/xer.py` hits that are about awp.Constraint): keep compiling; if one reads
  `awp.Constraint` rows, change it to read nothing about constraints and list it in the report (screens return in T04b/T04d).

## Interfaces (open these)
`schema/modules/awp/constraint.yaml`, `schema/fixtures/workflows/awp-constraint.yaml`, `schema/core/{record,links,events,numbering}.yaml` (patterns to
copy for a core typed table; find an existing core class with `tl:table` and `tl:record_types`), `tl_core/workflow/{definition,loader,engine}.py`,
`tl_core/links/vocabulary.py`, `schema/settings/access-words.yaml`, ADR-0024.

## Context (<= 10 files)
ADR-0024; the files above; `docs/reports/P2-I2/S2.md`; `docs/reports/P2-I2/S1.md`.

## Allowed paths
- `schema/core/**` (new `constraint.yaml` and imports), `schema/modules/awp/**` (removals and the module import), `schema/fixtures/workflows/{core-constraint,awp-constraint,awp-cwp,awp-iwp}.yaml`, `schema/fixtures/numbering/patterns.yaml`, `schema/fixtures/standards/co.acme.awp@1.0.0.yaml` (only a code list move), `schema/settings/access-words.yaml`
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` only)
- `packages/tl-core/src/tl_core/workflow/{definition,loader,engine}.py` (the guard kind, <= 30 lines), `packages/tl-core/src/tl_core/links/vocabulary.py` (`targets`)
- `packages/tl-modules/awp/**` and `packages/tl-api/src/tl_api/errors.py`, `docs/reference/openapi.json` (generated), the CLI/TUI/lake files named above (removals only)
- consequential pins (rule 12; counts of commands, access words, event types, tables, record types, relations, workflows, numbering patterns), each listed
- `dev/accept/P2-I2/C1.py` (create), `docs/reports/P2-I2/C1.md` (create)
Not allowed: `tl_core/constraints/**` (C2's), engine evaluation, any command, other modules.

## Acceptance (run once each; one package per gate; `NODE_OPTIONS=--max-old-space-size=6144` for check)
```
just gen
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/C1.py
uv run python dev/accept/P2-I2/S1.py
uv run python dev/accept/P2-I2/S2.py
just gate packages/tl-schema/tests
just gate packages/tl-modules/awp/tests tests/services/test_modules.py tests/webhooks
just gate packages/tl-core/tests/workflow packages/tl-core/tests/auth/test_access_words.py
just gate packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_api_document_controller.py packages/tl-api/tests/test_api_proposals.py
```
`C1.py` (SQLite, one `PASS <check>` per check, final `C1 ok`): `core.Constraint` in `TYPE_LABELS` and `OFFLINE_CLASSES` (`draft_only`) and no `awp.Constraint`;
`cur_core_constraint` columns exist; the four events load with `tl:event_type`; `core-constraint` workflow loads, `Cleared` and `Withdrawn` terminal; numbering allocates
`P123-CON-0001` and `-0002`; `targets` and `targeted_by` resolve in the vocabulary; the two words exist, `awp.constraint.edit` does not; the guard loads from YAML on the CWP
and IWP transitions named, `phase: ready` is on `ready` only; a YAML with a bad phase is refused by the loader; no guard appears on any other transition.

## Guards for S5 (name file:line in the report; run no mutants here)
Phase pattern; `severity` and `category` lists; the guard union member; the three opt-in lines; the two words.

## Report requirements
`docs/templates/haiku-report.md` shape, <= 60 lines: deviations first; files; every pin changed and why; acceptance output (<= 5 lines per command); how the confidentiality join was declared (or Blocked); the awp code removed (count).

## Commit
`P2-I2-C1: <imperative summary>`; body says what and why; end with the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: the schema model cannot declare a confidentiality join to the subject; the guard union cannot take the new member without touching more than the three named core files; a removal breaks a test that is not a pin; `just gen` changes a non-constraint generated file other than all-module registries.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
