# P2-FORMS S2 — Module `forms`: schema (templates, submissions with drafts, intake), workflows, words, settings, projectors

kind: piece
review: full
branch: p2/forms-s2-schema
worktree: /home/user/wt/forms/s2
Depends on: `p2/ip` (INSP-S1 and QR-S1 merged there). Independent of S1 (no shared file). Gated: schema, settings,
access words, new service actor (APPROVALS lines before merge; owner approves). Labels: schema.
Merge rule (P2-QR README, fan-out): the first signed schema piece merges first; a later one merges `p2/ip`, re-runs
`just gen` and `just compat-update` and re-pins its counts. Heavy runs: at most 2 at once on the box (16 GB).
This is ONE schema gate for the first slice and the intake slice (ADR-0032 is accepted: the intake schema is folded in,
decision D1 of STATE.md). The intake commands, route and purge job are not here (S6, S7c).

## Why
`docs/build-spec/module-designs/forms-eval.md` §2.4, §3, §8; ADR-0031 decisions 4, 6, 13; ADR-0032 decisions 2, 3, 5,
7, 11. Commands (S3), views, routes, CLI, tools and the intake slice are written against the names, tables and states
this piece creates. Additive only: no existing class, event, word, workflow, setting or column changes.

## Goal
1. **Schema** `schema/modules/forms/` (`module.yaml`, `template.yaml`, `submission.yaml`, `intake_code.yaml`,
   `intake_item.yaml`, `intake_body.yaml`, `events.yaml`; copy conventions from `schema/modules/quality/` and
   `schema/modules/qr/`). Scope of a template is `company` (the `ScopeId` range allows it); submissions and intake
   records take the project scope of the record they are about, else `company`.

   | Class | Table, offline | Fields |
   |---|---|---|
   | `Template` (`forms.Template`) | `cur_forms_template`, `none` | `version` (int ≥ 1, default 1, column `template_version`), `format_version` (int, 1 or 2), `form_fields` (`tl:json`, required, default `[]`; column `form_fields_json`), `field_count` (int ≥ 0), `content_hash` (64 lower hex, indexed; set at publish), `supersedes_id` (indexed), `bound_record_type` (≤ 64, null for a general form), `answer_class` (enum of the confidentiality classes `internal`, `restricted`, `privileged`; null = `internal`), `intake` (enum `IntakeFlag`: public; null otherwise), `purpose` (enum `IntakePurpose`: request, sign_on; null unless public), `accepts_as` (`tl:json` list of command names; null unless public), `published_on`, `retired_on` |
   | `Submission` (`forms.Submission`) | `cur_forms_submission`, `draft_only` | `template_id` (indexed), `template_version` (int), `template_hash` (64 hex), `subject_id` (indexed; the confidentiality subject; null when none), `answers` (`tl:json`, default `[]`), `answer_class` (as above, copied from the template at the first save), `draft_saves` (int ≥ 0, default 0), `author` (actor text ≤ 64), `submitted_on`, `reviewed_by`, `reviewed_on`, `review_note` (≤ 300), `void_reason` (≤ 300) |
   | `IntakeCode` (`forms.IntakeCode`) | `cur_forms_intake_code`, `none` | `code_hash` (64 lower hex, required, unique index), `template_id`, `template_version`, `template_hash`, `context_id` (indexed; the confidentiality subject), `context_type` (≤ 64), `heading` (≤ 60), `controller_role` (≤ 64), `issued_by`, `issued_at`, `expires_on` (date, required), `revoked_at`, `revoked_by` |
   | `IntakeItem` (`forms.IntakeItem`) | `cur_forms_intake_item`, `none` | `code_id` (indexed), `template_id`, `template_version`, `template_hash`, `body_mac` (64 hex), `body_bytes` (int ≥ 0), `received_at` (indexed), `accepted_as` (command name ≤ 64), `accepted_by`, `accepted_on`, `on_behalf_of_claim` (`tl:json` `{name, company}`; set by `Accepted` only), `rejected_reason` (enum `IntakeRejectReason`: spam, duplicate, not_ours, unclear), `rejected_by`, `purged_at` |
   | `IntakeBody` (table `forms_intake_body`) | operational: no event produces it | `item_id` (unique), `code_id` (indexed), `salt` (32 hex), `body` (text, ≤ 8192 bytes), `received_at` (indexed) |

   The title of a record is on the envelope. `IntakeBody` is operational like `idempotency_key`
   (`schema/core/idempotency.yaml`): no projector, a rebuild never clears it, and the archive, the lake, feeds and
   webhooks never read it; it uses `tl:current_state` and `tl:table` only to get one DDL for both dialects. If the
   generator cannot express an operational table inside a module schema, put that one class in
   `schema/core/forms_intake.yaml` and say so in the report (not a stop). The class descriptions document the shapes:
   template field (formats 1 and 2: `docs/build-spec/module-designs/forms-eval.md` §2.3), answer `{q, value, note}`.
2. **Events** (`feed_policy: none`; every payload names `record_id`; `tl:json` where a list or object is carried):
   `Template.Created` {format_version, form_fields, field_count, version, supersedes_id, bound_record_type,
   answer_class, intake, purpose, accepts_as}, `Template.Edited` {changes}, `Template.Published` {published_on,
   content_hash}, `Template.Retired` {retired_on};
   `Submission.DraftSaved` {template_id, template_version, template_hash, subject_id, answers, answer_class,
   save_no}, `Submission.DraftDiscarded` {}, `Submission.Submitted` {template_id, template_version, template_hash,
   subject_id, answers, answer_class, submitted_on}, `Submission.Accepted` {note}, `Submission.Returned` {note},
   `Submission.Voided` {reason};
   `IntakeCode.Issued` {code_hash, template_id, template_version, template_hash, context_id, context_type, heading,
   controller_role, expires_on}, `IntakeCode.Revoked` {reason};
   `IntakeItem.Received` {item_id, code_id, template_id, template_version, template_hash, body_mac, body_bytes,
   received_at}, `IntakeItem.Accepted` {accepted_as, on_behalf_of_claim, cause_event_id}, `IntakeItem.Rejected`
   {reason}, `IntakeItem.Purged` {purged_at}.
   No payload slot anywhere is named `code`, `token`, `url`, `body` or `salt`; `IntakeItem.Received` carries no typed
   text. Valid time (ADR-0026): tag nothing; add every event to `tests/tools/valid_time_baseline.toml` with a reason
   ("a system act, transaction time is the fact"; for `Submitted` and `Received`: "receipt time is the only time in v1").
3. **Workflows** (`schema/fixtures/workflows/`, every move `by_module`, no role guard; copy the header comment
   style of `quality-inspection.yaml`): `forms-template.yaml`: initial Draft; `publish` Draft → Published; `retire`
   Published → Retired and Draft → Retired; final Retired. `forms-submission.yaml`: initial Draft; `submit` Draft →
   Submitted and Returned → Submitted; `accept` Submitted → Accepted; `return` Submitted → Returned; `void`
   Submitted, Accepted, Returned → Voided; `discard` Draft → Discarded; final Accepted, Voided, Discarded.
   `forms-intake-code.yaml`: initial Active; `revoke` Active → Revoked; final Revoked (expiry is derived from
   `expires_on`, never a state). `forms-intake-item.yaml`: initial Pending; `accept` Pending → Accepted; `reject`
   Pending → Rejected; final Accepted, Rejected (a purge is `purged_at`, not a move).
4. **Numbering** (`schema/fixtures/numbering/patterns.yaml`, same form as the `quality.Checklist` block):
   `forms.Template` type_code `TPL` (scope `company`: use the company-scope form of an existing company pattern, check
   `patterns.yaml`), `forms.Submission` type_code `FRM` (per project; a record with no project uses the company form
   if the allocator supports it, else report it as a question for S3). Intake codes and items take no number.
   Report in one line at which event the allocator is called for `quality.Checklist` today, because S3 allocates a
   submission's number at submit, not at the first draft save (a draft "takes no number until submitted").
5. **Access words** (`schema/settings/access-words.yaml`, a `forms:` block): `forms.view: read`,
   `forms.template.edit: user`, `forms.template.publish: controller`, `forms.submit: user`, `forms.review:
   controller`, `forms.void: controller`, `forms.intake.issue: controller`, `forms.intake.review: controller`.
   Eight words. **Service actor** `svc:intake`: declare it where the other `svc:` actors are declared and held (see
   `tl_core/auth/seed.py`, `module_roles.py`); S2 only adds the constant and its test if a declaration is needed
   there; it holds no word.
6. **Settings** (`schema/settings/platform.yaml`; same form as the `qr` keys): `forms.draft_saves_max` (int, default
   50, 1..500, scopes `[platform, company]`, lockable), `forms.intake.enabled` (bool, default false, scope
   `[platform]`, not lockable; "off: every /i/ address answers as a dead code"), `forms.intake.rate_per_address_per_hour`
   (int, 20, 1..1000, `[platform]`), `forms.intake.rate_per_code_per_hour` (int, 60, 1..10000, `[platform]`),
   `forms.intake.pending_per_code_max` (int, 200, 1..5000, `[platform, company]`), `forms.intake.retention_days`
   (int, 30, 1..90, `[platform, company]`; the docs say backups holding the body table are kept no longer),
   `forms.intake.code_max_days` (int, 90, 1..365, `[platform, company]`).
7. **Fixtures** `schema/fixtures/forms/templates/`: `toolbox-talk.yaml`, `job-hazard-assessment.yaml`,
   `pre-use-check.yaml` (format 2; 5 to 12 fields each; use `section`, `help`, one `visible_when`, kinds `yes_no_na`,
   `choice`, `multi`, `date`, `text`; no `photo` field in the first two) and `intake/scaffold-request.yaml`,
   `intake/toolbox-sign-on.yaml` (`intake: public` profile of ADR-0032 decision 2, with `purpose`, `accepts_as`).
   Plain data `{title, format_version, bound_record_type, answer_class, intake, purpose, accepts_as, fields}`. A
   loader is not this piece. Every fixture must pass `tl_core.forms.rules` once S1 has merged; until then a test here
   checks the shape only (no `tl_core.forms` import: S1 may not be merged).
8. **Module package** `packages/tl-modules/forms` (`tl-mod-forms`, `tl_mod_forms`; copy the skeleton of
   `packages/tl-modules/qr`): `pyproject.toml` (entry point `throughline.modules` / `forms`; no new third-party
   dependency), `README.md`, `AGENTS.md`, `__init__.py` (`MODULE = "forms"`), `names.py` (five record types, states,
   the eight words, the event names, the setting keys, `INTAKE_ACTOR = "svc:intake"`), `projectors/` (`template.py`,
   `submission.py`, `intake_code.py`, `intake_item.py`, `__init__.py`; follow `projectors/checklist.py`:
   `field_count`, `draft_saves` (`save_no`) and `punch`-style counts are set from the payloads; `Submitted` and
   `DraftSaved` both insert the row when it is the stream's first event), `module.py` `spec()` with the five record
   types, projectors, `command_words={}`, `proposable=()`; no generic commands; no hook fields; no `confidential`
   declaration (CONF-ROWS adds it with the subject rows, before any read path ships: an undeclared module is
   unfiltered and has no readers yet). No commands (S3, S7c).
9. Workspace wiring: root `pyproject.toml` (workspace source, test path, dependency line) and `uv.lock`; one dependency
   line `"tl-mod-forms"` in `packages/tl-{api,cli,mcp,tui,web}/pyproject.toml`, as QR-S1 did for `tl-mod-qr`.
10. `just gen`, `just compat-update` (additive); commit sources and generated output together. The offline-classes
    spec gets five rows (`docs/build-spec/specs/offline-classes.md`): `Template` none, `Submission` draft_only (drafting
    commands `SubmitForm`, `SaveFormDraft`), `IntakeCode` none, `IntakeItem` none, `IntakeBody` none (operational).

## Allowed paths
- `schema/modules/forms/**` (create); `schema/fixtures/workflows/forms-{template,submission,intake-code,intake-item}.yaml`
  (create); `schema/fixtures/numbering/patterns.yaml` (two blocks); `schema/fixtures/forms/**` (create);
  `schema/settings/access-words.yaml` (the `forms:` block); `schema/settings/platform.yaml` (seven keys);
  `tests/tools/valid_time_baseline.toml` (lines); `docs/build-spec/specs/offline-classes.md` (five rows);
  `schema/core/forms_intake.yaml` (only in the fallback of Goal 1)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only); `packages/tl-schema/compat/event-schemas.json`
- `packages/tl-modules/forms/**` (create, as in Goal 8, plus `tests/conftest.py`, `tests/test_module_spec.py`,
  `tests/test_projectors.py`, `tests/test_intake_body_operational.py`)
- `packages/tl-core/src/tl_core/auth/seed.py` or `module_roles.py`: one constant line, only if Goal 5 needs it; say so in the report
- root `pyproject.toml`, `uv.lock`, one line in each of `packages/tl-{api,cli,mcp,tui,web}/pyproject.toml`
- `packages/tl-schema/tests/test_forms_schema.py` (create)
- Pinned lists, union form, each named in the report with old and new count: `packages/tl-schema/tests/test_offline_classes.py`,
  `test_ddl.py`, `test_generate.py`, `test_ddl_views.py`, `packages/tl-core/tests/auth/test_access_words.py` (a `FORMS` set
  of eight), `packages/tl-core/tests/test_numbering_config.py` (two patterns), `tests/settings/test_phase2_keys.py` and
  `packages/tl-core/tests/test_settings_definitions.py` (seven keys), `tests/services/test_modules.py` (module list), and any
  other test that fails only because the module, words, keys or tables now exist
- `packages/tl-core/src/tl_core/feed/cards.py`: only if a test refuses the new quiet events, add their names to the list it
  names (the P2-PUNCH S1 precedent, decision D14); say so in the report
- `docs/reports/P2-FORMS/S2.md` (create)
Not allowed: commands, handlers, views, routes, CLI, MCP, TUI, web code; `tl_core/confidentiality.py` and
`tl_core/modules.py`; `tl_core/forms/**` (S1); any other module or schema file.

## Tests to add
- `test_forms_schema.py`: five classes, tables, indexes (unique on `code_hash`; one on `content_hash`); the four enums
  and their values; 16 event types with their payload fields; offline classes as above; the four workflows load with the
  moves above and reject `Submitted → Draft`, `Discarded → Draft`, `Accepted → Submitted`, a move out of Revoked,
  Accepted-intake or Rejected-intake; numbering keys `TPL` and `FRM`; no slot of any class or payload is named `code`,
  `token`, `url`, `salt` (except `IntakeBody.salt`) or `body` (except `IntakeBody.body`), and the `IntakeItem.Received`
  payload has no text slot; the fixtures parse, field ids are unique, templates with `intake: public` have at most 8
  fields and only kinds text, choice, number.
- `test_projectors.py` (events appended through the ledger, never a projection write): template created, edited,
  published, retired gives the expected row at each step; a submission saved as draft twice (`draft_saves` 2), submitted,
  accepted; a submission submitted with no draft; discarded; returned then submitted; voided; an intake code issued and
  revoked; an intake item received, accepted with a claim, and one received, rejected, purged; a rebuild of every table
  equals the live rows.
- `test_intake_body_operational.py`: a row inserted into `forms_intake_body` survives `rebuild-projections` (the same
  call the idempotency test uses) and no projector writes it.
- `test_module_spec.py`: five record types; no commands, no proposable, no `confidential`.
- Webhook check (a Sec row): render a webhook body for a `Submission.DraftSaved` and a `Submission.Submitted` event whose
  `answers` hold a marker string; the body text must not contain the marker. If it does, stop: write `121` with the
  finding (this is the open finding SR-X1 F3 on webhook detail; the fix is a piece, not part of S2).

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); then, one run at a time, one file per path (the box has 16 GB;
combined schema gates have been killed by OOM):
1. `just gate packages/tl-schema/tests/test_forms_schema.py packages/tl-schema/tests/test_offline_classes.py packages/tl-schema/tests/test_valid_time_tag.py`
2. `just gate packages/tl-schema/tests/test_ddl.py packages/tl-schema/tests/test_ddl_views.py`
3. `just gate packages/tl-schema/tests/test_generate.py packages/tl-schema/tests/test_compat.py`
4. `just gate packages/tl-core/tests/auth/test_access_words.py packages/tl-core/tests/test_numbering_config.py packages/tl-core/tests/test_settings_definitions.py tests/settings/test_phase2_keys.py`
5. `just gate tests/services/test_modules.py tests/services/test_modules_offline.py packages/tl-modules/forms/tests packages/tl-core/tests/test_webhook_detail_redaction.py`
`just gate-pg packages/tl-modules/forms/tests/test_projectors.py packages/tl-modules/forms/tests/test_intake_body_operational.py`.
Existing paths were checked with `ls` on `p2/ip` @b91ee33d; `test_forms_schema.py` and everything under
`packages/tl-modules/forms/` are created by this piece.

## Mutation cap
One sentinel plus at most 4 targeted mutants: the submission workflow allows `accept` from Draft; the projector drops
`template_hash` on `Submitted`; `draft_saves` not set from `save_no`; the intake-item workflow allows a move out of
Rejected. 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines at `docs/reports/P2-FORMS/S2.md`; first line: deviations or none; list
every pinned file changed with old and new count, the final names (record types, states, events, words, settings,
tables) as one table for S3, S7c, S6 and the tickets, the numbering line of Goal 4 and the operational-table
placement of Goal 1. Commit `P2-FORMS-S2: ...` with the session trailers; no model names in committed text.
