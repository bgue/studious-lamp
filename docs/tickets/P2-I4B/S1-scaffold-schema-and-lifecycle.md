# P2-I4B-S1 — scaffold module: schema, lifecycle, tag colour, dismantle check, job `scaffold.inspections_due`

Status: ready (dispatch round 1; human gate: schema)
Tier: builder
Kind: piece
Review: full
Labels: schema, core, access, job
Depends on: trunk @d4e92ffc (requisitions, I5, PUNCH, X1 on it)
Branch: `p2/i4b-s1-scaffold`
Worktree: `/home/user/wt/i4b/s1`
Approver (schema): orchestrator (P2-Q10; line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the new module `scaffold` exists end to end below the read surface: LinkML under `schema/modules/scaffold/`
(`Scaffold`, `ScaffoldInspection`), one workflow, two numbering patterns, events, offline class, access words; the package
`packages/tl-modules/scaffold` (`tl-mod-scaffold`, `tl_mod_scaffold`) with the projectors, nine commands with guards, the pure
`rules` module, the job kind `scaffold.inspections_due`, and a `ModuleSpec`. No read view, route, CLI, TUI or MCP (T01, T09b1,
T09b2, T07a). Generated models, DDL and pinned lists are current. Haiku tickets start from T01.

## Brief references (pasted; decisions D1-D5 in `STATE.md` are authoritative)
Contract `docs/build-spec/phase2-contracts-draft.md` §3 (abridged): `Scaffold` `belongs_to` its `ScaffoldRequest`; `ErectScaffold`,
`InspectScaffold` (tag colour green, red, yellow; next due from `scaffold.inspection.interval_days`), `DismantleScaffold`. The module
imports `tl_mod_requisitions.api` (read) and never its handlers (first module-to-module import; recorded in §3).
Roadmap W3-2: green tag is a scaffold superuser word (`scaffold.tag.green`), no new account role. W3-3: no hire quantities.
Setting `scaffold.inspection.interval_days` exists in `schema/settings/platform.yaml` (int, default 7; do not edit).

**Record shape** (table `cur_scaffold_scaffold`, `cur_scaffold_scaffold_inspection`; id, scope; title on the envelope; copy conventions
from `schema/modules/quality/punch_item.yaml`; dates `YYYY-MM-DD`)
| Class | Fields |
|---|---|
| `scaffold.Scaffold` | `request_id` (record id of the `ScaffoldRequest`, indexed), `for_record_id` (copied from the request; the confidentiality subject, indexed), `location_text` (<= 120), `elevation` (<= 32), `gridline` (<= 32), `load_class` (<= 32) (the last three copied from the request), `tag` (enum `TagColour` green, yellow, red; null until first inspection), `tagged_on` (date), `last_inspected_on` (date), `next_due_on` (date), `flagged_due_on` (date; set by the job), `inspection_count` (int >= 0, default 0), `modify_reason`, `dismantle_reason` (<= 300 each) |
| `scaffold.ScaffoldInspection` | `scaffold_id` (indexed), `inspector` (actor text <= 64), `inspected_on` (date), `result` (enum `InspectionResult` pass, conditional, fail), `tag` (`TagColour`), `note` (<= 300) |
**Numbering** (`schema/fixtures/numbering/patterns.yaml`, `gap_free: true`, scope `"project:*"`, template `"{project}-{type}-{seq:4}"`):
`scaffold.Scaffold` type_code `SCF` (`P123-SCF-0001`), `scaffold.ScaffoldInspection` type_code `SCI`.
**Workflow** `schema/fixtures/workflows/scaffold-scaffold.yaml` (initial `Requested`; every move a module command, `by_module=True`, no role guard):
`design` Requested -> Designed; `erect` Designed -> Erecting; `pass` Erecting -> Inspected and Modify -> Inspected; `release` Inspected -> In Use;
`modify` Inspected -> Modify and In Use -> Modify (also by a failed inspection, below); `dismantle` Inspected, In Use, Modify -> Dismantle;
`remove` Dismantle -> Removed, and Requested, Designed -> Removed (withdraw). Terminal: `Removed` only. `ScaffoldInspection` has no workflow (an inspection is a fact).
**Commands** (names are the contract for T01 to T11; `by_module` moves; all on `Scaffold`; one fine word each, `name -> table word`):
| Command | Fields | Word | Table | Effect |
|---|---|---|---|---|
| `RegisterScaffold` | `request_id`, `title`, `location_text?` | `scaffold.register` | user | creates in Requested; refused unless the request is a `requisitions.ScaffoldRequest` in state Approved or later (not Rejected, Cancelled) and visible to the actor; copies the request fields; `belongs_to` link to the request; one scaffold per request |
| `DesignScaffold` | `note?` | `scaffold.design` | user | `design` |
| `ErectScaffold` | `note?` | `scaffold.erect` | user | `erect` |
| `InspectScaffold` | `result` (conditional or fail only), `note?`, `at?` | `scaffold.inspect` | user | writes a `ScaffoldInspection`, sets tag by `rules.tag_for`, dates by `rules.next_due`; a `fail` on Inspected or In Use also does `modify` |
| `TagScaffoldGreen` | `note?`, `at?` | `scaffold.tag.green` | controller | result `pass`, tag green; from Erecting or Modify also does `pass`; allowed in Erecting, Modify, Inspected, In Use |
| `ReleaseScaffold` | — | `scaffold.release` | user | `release`; refused unless the tag is green |
| `ModifyScaffold` | `reason` | `scaffold.modify` | user | `modify`; clears nothing (the tag stays until the next inspection) |
| `DismantleScaffold` | `reason` | `scaffold.dismantle` | user | the dismantle check (below), then `dismantle` |
| `RemoveScaffold` | `reason?` | `scaffold.remove` | user | `remove` |
Plus `scaffold.view: read` (ten words; add a `scaffold:` block to `schema/settings/access-words.yaml`). No other `generic_commands` than `SetPsetValues`, `AddLink`,
`AttachFile` and the link life, while not Removed (as quality `PUNCH_GENERIC_COMMANDS`); fields and state change only through the module's commands.
**Dismantle check** = `rules.dismantle_blockers(iwp_states, other_open_requests)` (pure, provided test). The handler gathers its inputs: the IWPs with a live
`requires` link whose target is this scaffold (read the live-link query of `tl_mod_awp/views.py` ~L360-390 for the pattern; the link is IWP -> scaffold) with their workflow states,
and `tl_mod_requisitions.api.open_requisitions_for(conn, iwp_id, kinds=["scaffold"])` for each such IWP, minus the scaffold's own `request_id`. A non-empty result refuses with
the reasons joined (a `RuleRefused`-style error of the module, text = the reasons). Hidden IWPs count (the guard must not leak: the refusal names a hidden IWP only as `a work package you cannot see`; pass `viewer=LOWEST` to the api read and test the text).
**Events** (`schema/modules/scaffold/events.yaml`, each `tl:event_type`, `feed_policy: none`, every payload names `record_id`): `Scaffold.Registered` (flat), `Scaffold.Designed`, `Scaffold.Erecting`,
`Scaffold.Inspected` {inspection_id, result, tag, inspected_on, next_due_on, note}, `Scaffold.Released`, `Scaffold.Modified` {reason}, `Scaffold.DismantleStarted` {reason},
`Scaffold.Removed` {reason}, `Scaffold.InspectionDue` {due_on, state} (job only). Valid time (ADR-0026): tag `at` on `Inspected` with `tl:valid_time: at`; anything untagged goes into
`tests/tools/valid_time_baseline.toml` with a reason. **Offline class:** both `none` (`offline: full | draft_only | none`; a tag and a register entry are acts on the authority, as `requisitions.WorkOrder`); add both rows to `docs/build-spec/specs/offline-classes.md`, no `offline_drafts`.
**Confidentiality:** a scaffold inherits its request's subject class like the requisitions (`P2-I4A` D10): add a part to `hidden_sql` in `tl_core/confidentiality.py` for `scaffold.Scaffold` over `for_record_id` and `scaffold.ScaffoldInspection` through its scaffold (follow the `requisitions.*` lines ~L146-170, same hop rule). Sec row.
**Job** `scaffold.inspections_due` (follow `tl_mod_awp/readiness/job.py` and `worker.py`; job id `inspdue:<project>:<YYYY-MM-DD>`; source `job:scaffold.inspections_due`, reserved already in `PHASE2_SOURCE_PREFIXES`): one run per project and day with `today` a parameter; reads the project setting
`scaffold.inspection.interval_days` through the settings service; for each Scaffold where `rules.due_state(...)` is `due` or `overdue` and `flagged_due_on != next_due_on` (for a never-inspected one use the erect date +interval: store `next_due_on` at `ErectScaffold`) it appends
one `Scaffold.InspectionDue`; the projector sets `flagged_due_on`. It never changes tag or state. A second run the same day writes nothing. `tl scaffold worker` lists it: CLI is not this piece (see TRAPS: X4 hooks).
**Rules module** `tl_mod_scaffold/rules.py` (pure, no DB): `tag_for(result) -> str`, `next_due(inspected_on, interval_days) -> date` (1..90), `due_state(state, last_inspected_on, today, interval_days) -> "ok"|"due"|"overdue"|"n_a"`, `dismantle_blockers(iwp_states, other_open_requests) -> list[str]`, constants `INSPECTABLE_STATES`, `HOLDING_IWP_STATES = {"Issued","In progress","On hold"}`. Behaviour is pinned by the provided test.

## Provided test (copy byte-identical, do not edit)
`docs/tickets/P2-I4B/provided/S1_test_rules.py` -> `packages/tl-modules/scaffold/tests/test_rules.py`. Make it pass first; the rest of the piece rides on these names.

## Context (<= 10 files)
`docs/tickets/P2-PUNCH/S1-schema-and-module.md`, `docs/tickets/P2-PUNCH/S2-commands-and-engine.md` (shape of a lifecycle piece), `docs/tickets/P2-I4A/S1-schema-and-module.md` (only the Allowed-paths list: pinned lists),
`schema/modules/quality/punch_item.yaml`, `packages/tl-modules/quality/src/tl_mod_quality/{module,commands,guards}.py`, `packages/tl-modules/requisitions/src/tl_mod_requisitions/api.py` (L1-110),
`packages/tl-modules/awp/src/tl_mod_awp/readiness/job.py`, `packages/tl-core/src/tl_core/confidentiality.py` L140-175. may explore: `docs/reports/P2-PUNCH/S1.md`, `S2.md`, `docs/reports/P2-I4A/S1.md`.

## Allowed paths
- `schema/modules/scaffold/**` (create), `schema/fixtures/workflows/scaffold-scaffold.yaml` (create), `schema/fixtures/numbering/patterns.yaml` (two blocks), `schema/settings/access-words.yaml` (the `scaffold:` block),
  `tests/tools/valid_time_baseline.toml` (lines), `docs/build-spec/specs/offline-classes.md` (two rows), `docs/build-spec/phase2-contracts-draft.md` (§3: one "As built" paragraph for scaffold, D1-D5 wording)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output), `packages/tl-schema/compat/event-schemas.json` (`just compat-update`, additive)
- `packages/tl-modules/scaffold/**` (create the package; `tests/` holds the provided test, `scaffold_world.py`, `test_module_spec.py`, `test_scaffold_commands.py`, `test_scaffold_visibility.py`, `test_inspections_job.py`)
- root `pyproject.toml` (workspace source, test path `packages/tl-modules/scaffold/tests`, dependency) and `uv.lock`; one dependency line `"tl-mod-scaffold"` in `packages/tl-{api,cli,mcp,tui}/pyproject.toml`
- `packages/tl-core/src/tl_core/confidentiality.py` (the scaffold parts only), `packages/tl-core/tests/` and `tests/` files that pin the lists below (union form, each listed in the report): offline classes count, `test_ddl*.py`, `test_generate.py`, `packages/tl-core/tests/auth/test_access_words.py`, `packages/tl-core/tests/test_numbering_config.py`, `tests/services/test_modules.py`, `tests/tools/proposable_exclusions.toml` only if a test names the new commands, and any other test that fails only because the module exists
- `packages/tl-schema/tests/test_scaffold_schema.py`, `dev/accept/P2-I4B/S1.py`, `docs/reports/P2-I4B/S1.md` (create)
Not allowed: any read view, route, CLI, MCP, TUI file; `tl_core/**` other than the confidentiality parts; the requisitions module; `tl_core/modules.py` (X4 is changing it, see TRAPS).

## Steps
1. LinkML, fixtures, words; `just gen`; commit together. 2. Package skeleton, `rules.py` and the provided test green. 3. Projectors, commands, guards, `ModuleSpec` (`proposable` empty; no hooks). 4. Confidentiality part, job. 5. Pinned lists, tests, acceptance.

## Acceptance (once each; one gate per path set, never the whole suite)
```
just gen
just check
uv run python dev/accept/P2-I4B/S1.py
just gate packages/tl-modules/scaffold/tests packages/tl-schema/tests/test_scaffold_schema.py
just gate tests/services/test_modules.py packages/tl-core/tests/auth/test_access_words.py packages/tl-core/tests/test_numbering_config.py
just gate-pg packages/tl-modules/scaffold/tests
```
`S1.py` (SQLite, one `PASS <check>` per line, final `S1 ok`): demo clauses 2 and 3 at command level on a fresh ledger: an approved `ScaffoldRequest` -> `RegisterScaffold` (`P123-SCF-0001`) -> Design -> Erect -> `TagScaffoldGreen` (state Inspected, tag green) -> Release (In Use);
a `fail` inspection gives tag red and state Modify; `ReleaseScaffold` refused until green again; an IWP in Issued that `requires` the scaffold refuses `DismantleScaffold` with its number in the text, a Closed one does not; the job flags an overdue scaffold once and twice-run writes nothing; each of the ten words resolves to its table word;
`RegisterScaffold` refused for a Rejected request and for a second scaffold on one request.
Tests to add (the builder writes them): schema test (columns and lengths, enums, workflow moves and the one terminal, patterns, words, events, valid-time tags); `test_scaffold_commands.py` (every command: allowed, refused wrong state, refused wrong word `user` vs `controller` for the green tag, dismantle both ways, hidden IWP text);
`test_scaffold_visibility.py` (a scaffold of a restricted IWP is hidden as one that never existed to the lowest viewer: `get`, list count and the dismantle refusal text); `test_inspections_job.py`.

## Mutation (sentinel + <= 5 mutants, in this worktree, 3 lines in the report)
Guards: `TagScaffoldGreen` word `controller` -> `user`; `ReleaseScaffold` green-tag check dropped; dismantle check dropped; `HOLDING_IWP_STATES` loses `Issued`; job's `flagged_due_on` skip dropped. Name file:line for each.

## Report requirements
Standard piece report (<= 60 lines): deviations first; files; pinned lists updated and why; acceptance output (<= 5 lines per command); words as built; events and fields added or dropped; valid-time and offline outcome; confidentiality part; mutation 3 lines.

## Commit
`P2-I4B-S1: <imperative summary>`; body says what and why; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not merge; do not push.

## Escalation triggers
- Blocked if: `just gen` changes a non-scaffold generated file other than all-module registries; a pinned-list change goes beyond a name added; the live-link query for `requires` needs a new core function; `hidden_sql` needs more than the two parts; a table word other than read, user, controller is wanted.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
