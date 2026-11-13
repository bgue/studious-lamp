# P2-I5-S1 — schema and package: rules of credit as package content, weekly plan, progress, closeout fields, words, settings

Status: ready after P2-INT C2 is on the trunk and merged into `p2/i5` (plan check F4); dispatch then
Tier: builder
Kind: piece
Review: full
Labels: schema, core, package
Depends on: P2-INT C2 on the trunk (the `tl:valid_time` annotation exists); `p2/wave2-close` @ec3314d plus that merge is the base
Branch: `p2/i5-s1-schema`
Worktree: `/home/user/wt/i5-s1`
Approver (schema, settings pattern, new dependency): orchestrator (P2-Q10; line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the rules of credit are content of a schema package (the `SchemaPackage` and `Adoption` mechanism of `tl_mod_schemareg`; no new record class, no bespoke loader): the package content model
accepts a `rules_of_credit` section and the package lint refuses weights that do not sum to 100. The standards package `co.acme.awp@1.1.0` carries the sample rules. `awp.WeeklyPlan`, the commitment rows, the IWP
progress table, the closeout and CWP fields, the awp file slots, every event, word, setting and code list are data; generated models, DDL and pinned lists are current. No command exists yet (S2 to S5).

## Brief references (pasted; `module-designs/field-work-packaging.md` is authoritative)
All records project scope, confidentiality `internal`. Dates `YYYY-MM-DD`; decimals text, ASCII digits. Copy conventions from `schema/modules/awp/{iwp,scope_item,closeout,rollup}.yaml` and
`schema/fixtures/workflows/awp-scope-item.yaml`. Free-text reasons everywhere in this increment are capped at 300 characters (F2).

| Type | Shape (table in brackets) |
|---|---|
| Rules of credit (package content, section `rules_of_credit`) | list (<= 40) of `{commodity, kind (scope_item, weld, bolted_joint), steps: [{name (<= 40), weight (int 1..100), evidence}]}`; weights of one entry sum to exactly 100; `evidence` is `scope_state:<State>`, `record_state:<type>:<State>` (inert until the type exists) or `manual` |
| `awp.WeeklyPlan` (key `<project>-WK-<year>W<ww>`, composed from the ISO week, one per project and week) | `week` (`YYYY-Www`), `week_start`, `ppc` (decimal text 1 dp, null until closed), `closed_at`. Workflow Draft -> Committed -> Closed (`cur_awp_weekly_plan`) |
| commitment rows (module events only, not records) | `plan_id`, `iwp_id`, `foreman` (<= 64), `committed_hours` (1 dp), `outcome` (null, done, missed), `miss_reason` (code list `MissReason`) (`cur_awp_week_commitment`, unique `plan_id, iwp_id`) |
| IWP progress (operational table) | `iwp_id`, `earned_pct` (decimal 1 dp), `edition` (`package@version` used), `as_of_seq`, `manual_json` (<= 50 entries) (`cur_awp_iwp_progress`) |
| `awp.IWPCloseout` (exists) | add `redlines_file_id`, `closed_by` (actor <= 64), `closed_at`; keep the key `<iwp key>-CLOSE` |
| `awp.CWP` (exists) | add `assigned_party` (free text <= 120, null ok; P2-Q13 A) |

**Package.** `schema/fixtures/standards/co.acme.awp@1.1.0.yaml`: a copy of the 1.0.0 content plus code list `MissReason` (Constraint, Material, Labour, Weather, Rework, Access, Equipment, Other), code `Interface` in `ConstraintType`, and the
`rules_of_credit` section: `piping` scope_item steps `Material received 30` (`manual`), `Installed 60` (`scope_state:Installed`), `Verified 10` (`scope_state:Verified`); a `weld` entry (fit-up 20, welded 60, NDE accepted 20) and a
`bolted_joint` entry (placed 50, torqued 50) as `record_state` examples; other commodities default to the `piping` steps. Read `packages/tl-schema/src/tl_schema/packages.py` and `lint.py` first: extend the content model and add the lint rule
(fixed message `rules_of_credit: weights of <commodity> do not sum to 100`, nothing written; bounds: file 256 KiB, ASCII digits, no NUL or direction marks via `tl_core/text.py`). Keep 1.0.0 as it is; `co.acme.awp@1.1.0` supersedes it for awp
(tests that name 1.0.0 stay on it, or move to 1.1.0 in one commit if they must; list them). If the package content model is closed to new sections in a way that needs a core change, stop and escalate with the shape that works.
**Setting** `awp.rules_of_credit.set` already exists: change only its `validation.pattern` to accept `package@version` (`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}@[0-9]+\.[0-9]+\.[0-9]+$|^$`) and say in its docs that empty means `co.acme.awp@1.1.0`.
**Events** (`schema/modules/awp/week_events.yaml`, additions to `iwp_events.yaml`; each `tl:event_type`): `WeeklyPlan.Opened`, `.IwpCommitted` {iwp_id, foreman, committed_hours}, `.OutcomeRecorded` {iwp_id, outcome, miss_reason}, `.Closed` {ppc},
`IWP.Started` {at}, `IWP.ProgressRecorded` {iwp_id, earned_pct, edition, at}, `IWP.FieldCompleted` {at}, `IWPCloseout.Recorded` {actual_hours, remaining_punch, actuals_file_id, redlines_file_id}, `Cwp.PartyAssigned` {party},
`Cwp.SubcontractProgressRecorded` {rows}. No new core event: the waived clear is the existing constraint clear event with source `check` (F2). Feed cards: `WeeklyPlan.Closed`, `IWPCloseout.Recorded`; policy `none` on the rest.
**Valid time (ADR-0026 F5):** tag `at` of `IWP.Started`, `.FieldCompleted` and `.ProgressRecorded` with `tl:valid_time`; the annotation and its lint exist (P2-INT T01) and its shrink-only baseline must not grow. `week_start` and `need_by` are plans, not valid time.
**Offline classes** (`specs/offline-classes.md`): `WeeklyPlan` `none`; progress rows derived (no class).
**File slots (F6)** `schema/fixtures/files/awp-iwp.yaml` (slot `pack`: HTML, PDF, one current file, text types) and `schema/fixtures/files/awp-iwp-closeout.yaml` (slots `redlines` PDF or image, `actuals` CSV); copy the shape and bounds of `schema/fixtures/files/correspondence-correspondence.yaml`.
**Access words** (`schema/settings/access-words.yaml`): `awp.week.plan: user`, `awp.week.commit: user`, `awp.week.close: controller`, `awp.progress.record: user`, `awp.closeout.record: user`, `awp.closeout.close: controller`, `awp.subcontract.assign: controller`,
`awp.subcontract.progress: user`, `awp.worker.run: controller` (the follower worker, S4 B), `core.constraint.waive: controller`. Add them to the module tables of `module-roles.yaml` as the existing awp words appear. No new account role.
**Settings** (`schema/settings/platform.yaml`, copy the `awp.iwp.size_hours` shape): `awp.pack.pdf` (bool, default false, platform/company/project: "write PDF and QR codes into the pack when the optional libraries are installed"); `tui.landing` (string, default `default`, scopes
`[platform, user]` like the existing user-scope keys, allowed `default`, `iwp_mine`; "which screen the terminal opens on after sign-in"). No `api.public_base_url` (F12).
**Optional extra:** `packages/tl-modules/awp/pyproject.toml` `[project.optional-dependencies] pack = ["reportlab", "segno"]`, versions pinned by `uv lock` (BSD both). The licence check runs after `uv sync --extra pack` (F11): run it that way; update
`tests/tools/test_check_licences.py` data only if it fails; if either licence check fails, stop and escalate.

## Interfaces (open these)
`schema/modules/awp/{iwp_events,closeout,cwp}.yaml`; `schema/fixtures/workflows/awp-scope-item.yaml`; `schema/settings/{access-words,module-roles,platform}.yaml`; `packages/tl-modules/awp/src/tl_mod_awp/{names,module}.py` and `projectors/rollup.py` (operational table pattern);
`packages/tl-schema/src/tl_schema/{packages,lint}.py`; `packages/tl-modules/schemareg/src/tl_mod_schemareg/handlers/packages.py` (gates); `schema/fixtures/files/`; `docs/build-spec/specs/offline-classes.md`.

## Context (<= 12 files)
The Interfaces files plus `docs/adr/0026-attested-bitemporal-graph.md` F5, `docs/reports/P2-I2/S1.md`, `schema/fixtures/standards/co.acme.awp@1.0.0.yaml`.
may explore: `packages/tl-core/src/tl_core/auth/access_words.py` (never edit).

## Allowed paths
- `schema/modules/awp/**` (create `week.yaml`, `week_events.yaml`, `progress.yaml`; edit `closeout.yaml`, `cwp.yaml`, `iwp_events.yaml`)
- `schema/fixtures/workflows/awp-weekly-plan.yaml`, `schema/fixtures/standards/co.acme.awp@1.1.0.yaml`, `schema/fixtures/files/awp-iwp.yaml`, `awp-iwp-closeout.yaml` (create)
- `schema/settings/{access-words,module-roles,platform}.yaml` (lines added; one pattern edit)
- `packages/tl-schema/src/tl_schema/{packages,lint}.py` and their tests (the rules section and its lint rule only)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only)
- `packages/tl-modules/awp/{pyproject.toml,src/tl_mod_awp/{names.py,projectors/week.py,projectors/progress.py,module.py},tests/__init__.py}`; root `uv.lock` (lock only)
- pinned lists (rule 12): tests that enumerate record types, events, tables, workflows, words, settings, code lists or file slots and change only because these exist, each written as the union; list each in the report
- `dev/accept/P2-I5/S1.py`, `docs/reports/P2-I5/S1.md` (create)
Not allowed: commands or handlers, `tl_core/**`, other modules, any `tl-api`, `tl-cli`, `tl-tui`, `tl-mcp` file.

## Steps
1. Package content model and lint rule; the 1.1.0 package; `just gen`.
2. LinkML, workflow, file slots, settings, words; `just gen`; commit schema and generated output together.
3. Projectors for `WeeklyPlan`, commitment rows and progress rows (they apply events; no handler), `names.py`, `module.py` registration (no commands); the `pack` extra and `uv lock`.
4. Fix pinned lists that fail only because these exist. Then the acceptance script.

## Acceptance (run once each; one package per gate, pinned-list files named, never the whole suite)
```
just gen
just check
uv run python dev/accept/P2-I5/S1.py
just gate packages/tl-schema/tests
just gate packages/tl-modules/awp/tests tests/services/test_modules.py tests/webhooks
just gate tests/schema
uv sync --extra pack --package tl-mod-awp && just gate tests/tools/test_check_licences.py
```
Also run by name the pinned-list tests found with `grep -rln "awp.IWPCloseout" tests packages/*/tests packages/tl-modules/*/tests`, the DDL test, `test_generate.py`, the settings and access-word tests and the file-slot fixture test.
`S1.py` (SQLite, dialect-neutral, `PASS <check>` lines, final `S1 ok`): every table exists in the generated DDL; the weekly plan workflow loads, `Closed` is final, `Draft -> Closed` refused; `co.acme.awp@1.1.0` passes the package lint and its `piping` entry sums to 100; weights 30/60/20
are refused with the fixed message; a 300 KiB file and a NUL byte are refused; the setting accepts `co.acme.awp@1.1.0` and refuses `co acme`; every event has `tl:event_type` and the stated feed policy; the three `at` fields carry `tl:valid_time`; every new word resolves to its
table word and `core.constraint.waive` is `controller`; `awp.pack.pdf` defaults off; `tui.landing` accepts `iwp_mine` and refuses `x`; both file-slot fixtures load; each projector round-trips a hand-written event; the `pack` extra resolves in `uv.lock`.

## Tests for the end run (S6 writes them; none here)
## Report requirements
`docs/templates/haiku-report.md` shape, ≤ 60 lines; deviations first; pinned-list files touched; mutation: sentinel plus ≤ 5 on the weights lint, the size bound, `Draft -> Closed`, the waive word, the setting pattern, in 3 lines.
## Escalation triggers
The package content model cannot carry a new section without a core change; a licence check fails; P2-INT C2 is not on the base; a pinned list needs more than a union.
## Blocked
(builder writes here)
## Decision
(supervisor or orchestrator writes here)
