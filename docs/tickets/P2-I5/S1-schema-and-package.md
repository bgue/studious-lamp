# P2-I5-S1 — schema and package: rules of credit, weekly plan, progress, closeout fields, words, settings

Status: ready (after the plan check is answered; dispatch round 2)
Tier: builder
Kind: piece
Review: full
Labels: schema, core, loader
Depends on: — (`p2/wave2-close` @ec3314d is the base)
Branch: `p2/i5-s1-schema`
Worktree: `/home/user/wt/i5-s1`
Approver (schema, roles data, new dependency): orchestrator (P2-Q10; line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece the awp LinkML holds `awp.RulesOfCredit`, `awp.WeeklyPlan` with its commitment rows, the IWP progress table, the
closeout fields and the CWP party field; the sample package `co.acme.awp-roc@1.0.0` loads through a loader function that refuses bad
weights; every event, access word, setting, code list and the `foreman` account role is data; the optional extra `pack` is declared;
generated models, DDL and pinned lists are current. No command exists yet (S2 to S5 build them). Haiku tickets T01 and T11a start from this.

## Brief references (pasted; `module-designs/field-work-packaging.md` is authoritative)
All records project scope except `RulesOfCredit` (company), confidentiality `internal`. Dates `YYYY-MM-DD`; decimals text with ASCII digits.
Copy conventions from `schema/modules/awp/{iwp,scope_item,closeout,rollup}.yaml` and `schema/fixtures/workflows/awp-scope-item.yaml`.

| Type | Shape (table in brackets) |
|---|---|
| `awp.RulesOfCredit` (company scope, key `<package>@<version>`, e.g. `co.acme.awp-roc@1.0.0`) | `package`, `version`, `title`, `entries_json`: list (<= 40) of `{commodity, kind (scope_item, weld, bolted_joint), steps: [{name (<= 40), weight (int 1..100), evidence}]}`; weights of one entry sum to exactly 100; `evidence` is `scope_state:<State>`, `record_state:<type>:<State>` (inert until the type exists) or `manual` (`cur_awp_rules_of_credit`) |
| `awp.WeeklyPlan` (key `<project>-WK-<year>W<ww>`, composed from the ISO week, one per project and week) | `week` (`YYYY-Www`), `week_start`, `ppc` (decimal text 1 dp, null until closed), `closed_at`. Workflow Draft -> Committed -> Closed (`cur_awp_weekly_plan`) |
| commitment rows (not records; module events only) | `plan_id`, `iwp_id`, `foreman` (<= 64), `committed_hours` (1 dp), `outcome` (null, done, missed), `miss_reason` (code list `MissReason`) (`cur_awp_week_commitment`, unique `plan_id, iwp_id`) |
| IWP progress (operational table) | `iwp_id`, `earned_pct` (decimal 1 dp), `edition` (the `RulesOfCredit` key used), `as_of_seq`, `manual_json` (<= 50 entries) (`cur_awp_iwp_progress`) |
| `awp.IWPCloseout` (exists) | add `redlines_file_id`, `closed_by` (actor <= 64), `punch_source` (`manual`) and a workflow-free `closed_at`; keep the key `<iwp key>-CLOSE` |
| `awp.CWP` (exists) | add `assigned_party` (free text <= 120, null ok; P2-Q13 A) |

**Events** (`schema/modules/awp/week_events.yaml` and additions to `iwp_events.yaml`, each with `tl:event_type`): `RulesOfCredit.Loaded`,
`WeeklyPlan.Opened`, `.IwpCommitted` {iwp_id, foreman, committed_hours}, `.OutcomeRecorded` {iwp_id, outcome, miss_reason}, `.Closed` {ppc},
`IWP.Started` {at}, `IWP.ProgressRecorded` {iwp_id, earned_pct, edition, at}, `IWP.FieldCompleted` {at}, `IWPCloseout.Recorded` {actual_hours, remaining_punch,
actuals_file_id, redlines_file_id}, `Cwp.PartyAssigned` {party}, `Cwp.SubcontractProgressRecorded` {rows}. Core: `Constraint.Waived` {reason (<= 500), by} added to the
core constraint events (waiver is its own event so a reader tells it from a clear). Feed cards: `WeeklyPlan.Closed`, `IWPCloseout.Recorded`; policy `none` on the rest.
**Valid time (ADR-0026 F5):** tag `at` of `IWP.Started`, `.FieldCompleted` and `.ProgressRecorded` with `tl:valid_time` if the generator accepts it
(`grep -rn "valid_time" packages/tl-schema/src`); if not, leave them untagged and say so under Deviations (P2-INT owns the pass). `week_start`, `need_by` are plans, not valid time.
**Offline classes** (`specs/offline-classes.md`): `WeeklyPlan` `none`, `RulesOfCredit` `none`, progress rows derived (no class).
**Access words** (`schema/settings/access-words.yaml`): `awp.week.plan: user`, `awp.week.commit: user`, `awp.week.close: controller`, `awp.progress.record: user`,
`awp.rules_of_credit.load: controller`, `awp.closeout.record: user`, `awp.closeout.close: controller`, `awp.subcontract.assign: controller`,
`awp.subcontract.progress: user`, `core.constraint.waive: controller`. Add them to the module tables of `module-roles.yaml` as the existing awp words appear.
**Account role `foreman`** in `module-roles.yaml` `derive`: same module roles as `user` (`{module: "*", role: user}`); no new access word. The TUI landing is T06c, not here.
**Settings** (`schema/settings/platform.yaml`, copy the `awp.iwp.size_hours` shape): `awp.pack.pdf` (bool, default false, platform/company/project, "write PDF and QR codes
into the pack when the optional libraries are installed"), `api.public_base_url` (string, default empty, platform, https only or empty, <= 200; the base of deep links in the pack).
`awp.rules_of_credit.set` already exists: do not touch it.
**Code lists** in `co.acme.awp@1.0.0.yaml`: `MissReason` (Constraint, Material, Labour, Weather, Rework, Access, Equipment, Other); add `Interface` to `ConstraintType`.
**Package** `schema/fixtures/standards/co.acme.awp-roc@1.0.0.yaml`: key `rules_of_credit`, entries: `piping` scope_item steps `Material received 30` (`manual`),
`Installed 60` (`scope_state:Installed`), `Verified 10` (`scope_state:Verified`); a `weld` entry (fit-up 20, welded 60, NDE accepted 20) and a `bolted_joint` entry (placed 50, torqued 50) as
`record_state` examples; other commodities default to the `piping` steps. Loader function `tl_mod_awp.loaders.roc.load_rules_of_credit(conn, path, *, actor)` in the awp
package: file bound 256 KiB, YAML safe load, ASCII digits, no NUL or direction marks (`tl_core/text.py`), weights integers summing to 100 per entry, otherwise `RulesOfCreditError`
with a fixed message and nothing written; writes one company-scope `awp.RulesOfCredit` record through the existing record path (by module, word `awp.rules_of_credit.load`).
**Optional extra:** in `packages/tl-modules/awp/pyproject.toml` `[project.optional-dependencies] pack = ["reportlab", "segno"]`, versions pinned by `uv lock` (BSD both);
update `tests/tools/test_check_licences.py` allow data only if it fails; if either licence check fails, stop and escalate.

## Interfaces (open these; verbatim shapes)
`schema/modules/awp/{iwp_events,closeout,cwp}.yaml`; `schema/fixtures/workflows/awp-scope-item.yaml`; `schema/settings/{access-words,module-roles,platform}.yaml`;
`packages/tl-modules/awp/src/tl_mod_awp/{names,module,loaders/awp}.py` and `projectors/rollup.py` (operational table pattern); `packages/tl-core/src/tl_core/constraints/` events;
`docs/build-spec/specs/offline-classes.md`.

## Context (<= 12 files)
The Interfaces files plus `docs/adr/0024-constraints-on-any-record.md` §4, `docs/adr/0026-attested-bitemporal-graph.md` F5, `docs/reports/P2-I2/S1.md`, `schema/fixtures/standards/co.acme.awp@1.0.0.yaml`.
may explore: `packages/tl-core/src/tl_core/auth/access_words.py` (never edit).

## Allowed paths
- `schema/modules/awp/**` (create `week.yaml`, `week_events.yaml`, `roc.yaml`, `progress.yaml`; edit `closeout.yaml`, `cwp.yaml`, `iwp_events.yaml`)
- `schema/core/**` only the `Constraint.Waived` event (one block) and nothing else
- `schema/fixtures/workflows/awp-weekly-plan.yaml` (create); `schema/fixtures/standards/co.acme.awp-roc@1.0.0.yaml` (create); `co.acme.awp@1.0.0.yaml` (two code edits)
- `schema/settings/{access-words,module-roles,platform}.yaml` (lines added)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only)
- `packages/tl-modules/awp/{pyproject.toml,src/tl_mod_awp/{names.py,loaders/roc.py,projectors/week.py,projectors/progress.py,module.py},tests/__init__.py}`; root `pyproject.toml` and `uv.lock` (lock only)
- pinned lists (rule 12): tests that enumerate record types, events, tables, workflows, words, settings, roles or code lists and change only because these exist, each written as the union; list each in the report
- `dev/accept/P2-I5/S1.py`, `docs/reports/P2-I5/S1.md` (create)
Not allowed: commands or handlers, other `tl_core/**`, other modules, any `tl-api`, `tl-cli`, `tl-tui`, `tl-mcp` file.

## Steps
1. LinkML, fixtures, settings, roles; `just gen`; commit schema and generated output together.
2. Projectors for `WeeklyPlan`, commitment rows and progress rows (they apply the events; no handler yet), `names.py` constants, `module.py` registration (no commands).
3. Loader function and the sample package; the `pack` extra and `uv lock`.
4. Fix pinned lists that fail only because these exist. Then the acceptance script.

## Acceptance (run once each; one package per gate, pinned-list files named, never the whole suite)
```
just gen
just check
uv run python dev/accept/P2-I5/S1.py
just gate packages/tl-schema/tests
just gate packages/tl-modules/awp/tests tests/services/test_modules.py tests/webhooks
just gate tests/schema tests/tools/test_check_licences.py
```
Also run by name the pinned-list tests found with `grep -rln "awp.IWPCloseout" tests packages/*/tests packages/tl-modules/*/tests`, the DDL test, `test_generate.py` and the settings and access-word tests.
`S1.py` (SQLite, dialect-neutral, `PASS <check>` lines, final `S1 ok`): every table exists in the generated DDL; the weekly plan workflow loads, `Closed` is final, `Draft -> Closed` refused; the sample package loads
and the `piping` entry sums to 100; a package with weights 30/60/20 is refused with the fixed message and no record is written; a 300 KiB file and a NUL byte are refused; every event has `tl:event_type` and the stated
feed policy; every new word resolves to its table word and `core.constraint.waive` is `controller`; the `foreman` role derives `user` module roles; `awp.pack.pdf` defaults off and `api.public_base_url` refuses `http://`; each
projector round-trips a hand-written event; the `pack` extra resolves in `uv.lock`.

## Tests for the end run (S6 writes them; none here)
## Report requirements
`docs/templates/haiku-report.md` shape, ≤ 60 lines; deviations first; list pinned-list files touched; mutation: sentinel plus ≤ 5 on the weights check, size bound, `Draft -> Closed`, the waive word, the `http://` refusal, in 3 lines.
## Escalation triggers
The standards loader cannot carry a company record (say what shape works); a licence check fails; the generator rejects `tl:valid_time`-adjacent annotations (leave untagged and report); a pinned list needs more than a union.
## Blocked
(builder writes here)
## Decision
(supervisor or orchestrator writes here)
