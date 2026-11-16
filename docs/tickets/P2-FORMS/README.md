# P2-FORMS — Forms engine, general forms, zero-login intake, web fill page

Status: round 3 (2026-11-16; S1, S2, S2w, S3, CR1 merged; round 3 wrote S7c, S6, W1, W2 specs, tickets T02 and I02 with provided tests). Plan of record: `docs/build-spec/module-designs/forms-eval.md` §8.3 (plan-checked there,
15 findings answered; this plan does not differ from it except as the decisions of `STATE.md` say). Pieces specified: S1, S2, S3, CR1.
Sources: ADR-0031 (accepted), ADR-0032 (accepted, owner 2026-11-15), `forms-eval.md` (§2 engine, §3 API, §8), ADR-0030
and `tl_core/qr/types.py` (the pattern), `docs/tickets/P2-INSP/README.md` (pattern for this file). Branch `p2/forms`
from the integration branch `p2/ip`; piece branches `p2/forms-s<n>-<slug>`, ticket branches `p2/forms-t<nn>-<slug>`,
worktrees `/home/user/wt/forms/<id>`. Board: `STATE.md`. Slice names: **FORMS** (first slice), **INTAKE**, **WEB**.
SF (store and forward, 2 pieces, about 9 tickets) is **Phase 3** and has no ticket here.

## Objective
After FORMS the platform has a forms engine: a template is data (format 1 = the INSP checklist question; format 2 adds
`section`, `help`, `multi`, `date`, `photo` and a closed `visible_when`), validated in Python by pure rules in
`tl_core/forms`, projected to a JSON Schema, a terminal runner and an agent tool. Modules register a form source
(`throughline.form_sources`) so a record answers "which template and which typed command". A new module `forms` holds
general forms with no typed home (toolbox talk, job hazard assessment, pre-use check): `forms.Template`,
`forms.Submission` with server-side drafts, review by a controller who is not the submitter. Permits stay typed; the
engine owns capture and never a lifecycle. INTAKE adds `/i/<code>`: a stranger hands in at most 8 plain fields, staged
for a signed-in controller. WEB vendors the two MIT SurveyJS files for the fill page. Out of scope: store and forward,
a status page for a stranger, photos on `/i/`, submissions export, intake merge and matching (forms-eval §8.3, last list).

## Demo
FORMS: `dev/demos/P2-FORMS.sh` (`just demo P2-FORMS`, SQLite then Postgres). `PASS clause N` only after a real check.
1 publish a general template; 2 fill and submit it from the CLI; 3 fill it through the terminal runner model (driver);
4 save a draft, resume it, submit; 5 a controller other than the submitter accepts it; the submitter is refused;
6 fill an inspection result through the form binding of an inspection; 7 a hidden record answers as a missing one on
every forms read; 8 a draft is invisible to every reader but its author.
INTAKE: print a poster, submit with no login, accept as a requisition, reject one, purge (`P2-FORMS-INTAKE` demo).
WEB: fill an inspection from a scanned card in a browser (`P2-FORMS-WEB` demo).

## Checkpoints
C1: S1 and S2 merged to `p2/ip` (core contract; schema; APPROVALS). C2: CONF-ROWS rows for forms and S3 merged
(commands, the seam); S3s merged when INSP C2 and PTW C2 are in `p2/ip`. C3: every FORMS ticket merged or abandoned.
C4: per-folder gates on touched packages, `gate-pg` on touched directories, demo on both adapters, security review closed.

## Items, first slice FORMS
Tier B = builder piece (`kind: piece`); H = implementer ticket. Sec = a row for the wave's security review.

| ID | Title | Tier | Depends | Sec | Review | Slice |
|---|---|---|---|---|---|---|
| S1 | `tl_core/forms/{types,rules,registry}.py`: frozen contract (`FormBinding`, `FormSource`, entry-point group), rules for formats 1 and 2, `visible_ids`, `content_hash`, intake profile; spec `S1-forms-contract-and-rules.md`, provided test | B | `p2/ip` at INSP C1 | - | full | **today** |
| S2 | Module `forms` schema: Template, Submission (drafts), IntakeCode, IntakeItem, operational `forms_intake_body`; 16 events; four workflows; 8 words; 7 settings; fixtures; projectors; package (intake schema folded in, D1); spec `S2-forms-schema.md` | B | `p2/ip` | webhook text check | full | **today** |
| CR1 | CONF-ROWS for this wave (orchestrator-scheduled serialised piece): `forms.Submission`, `forms.IntakeItem` subject rows and the `confidential` declaration; the author-only draft rule; no forms piece edits `confidentiality.py` | B | S2 | yes | full | later |
| S3 | Commands: template edit, publish, revise, retire; `SubmitForm`, `SaveFormDraft` (bounded by `forms.draft_saves_max`), `DiscardFormDraft`; review accept, return, void (reviewer is not the submitter); the one seam that runs a command inside the caller's unit of work; `PROPOSABLE` row `propose_form_submission`; submission number allocated at submit | B | S1, S2 | yes (draft row) | full | later |
| S3s | Form sources for `quality.Inspection` and permits (`RequestPermit`, precaution ticks), entry points; writes in two other modules; approvers: the INSP and PTW supervisors | B | S3, INSP C2, PTW C2 | yes | full | later |
| T01 | Projection `tl_core/forms/jsonschema.py` (`to_json_schema(fields, fmt)`; property test: agrees with `validate_answers` on every fixture template) | H | S1 | - | lite | later |
| T02 | Runner model `tl_core/forms/runner.py` (pure: one field per step, back, forward, skip hidden, review, confirm); moved from INSP T02; ticket `T02-runner-model.md`, provided test | H | S1 | - | full | **ready** |
| T03 | Views `tl_mod_forms/views.py`: template list and detail, submission list and detail, `form_for(record)` over the form sources; `viewer=` defaults to the lowest clearance; filter before LIMIT and counts | H | S3, CR1 | yes | full | later |
| T04 | API read routes (`GET /forms/templates`, `.../versions/{n}` with `?as=jsonschema` and ETag, `/forms/for/{key}`, `/forms/submissions[/{key}]`); five-reader walk; waits P2-X4 C2 | H | T03, T01, X4 C2 | yes | full | later |
| T05 | CLI `tl form` (`ls`, `show`, `fill`, `drafts`, `submit`, `review`); `--answer q1=yes`, `--answers-file`; waits X4 C2 | H | T03, T01 | - | full | later |
| T06 | MCP read tools `get_form`, listing, and `propose_form_submission`; closed until listed; walk; waits X4 C2 | H | T03, T01, S3 | yes | full | later |
| T07 | Terminal: `form_runner_text.py` and the runner screen over T02 (`tui-layout`; logic in a Textual-free module first) | H | T02, T03 | - | full | later |
| T08 | Draft resume in the runner and in `tl form fill --resume` | H | T05, T07 | - | full | later |
| T09 | Generator: general templates and submissions in the demo project (`dev/seed/demo_project/forms.py`), pins | H | S3 | - | full | later |
| T10 | Walk tests: five readers over every forms route and tool, plus the author-only draft walk, hidden-looks-missing byte comparison | H | T04, T06 | yes | full | later |
| T11 | Demo `dev/demos/P2-FORMS.sh` and driver (eight clauses above) | H | T05-T10 | - | full | later |
| T12 | Tour shots and docs: module README and AGENTS, `docs/modules/forms/`, runbook `docs/runbooks/forms.md` (templates carry no project text; backups), root `AGENTS.md` row | H | T11 | - | lite | later |
| T13 | `tl_mod_quality.insp_rules` re-exports `validate_questions` and `validate_answers` from core (keeps `failed_questions`, `result_of`); INSP T00 test stays as is | H | S1, INSP T00 merged | - | full | later |
| T14 | Webhook contract scenario delivers the Permit, Checklist, Inspection, QR and forms events; envelope `required` drops `omit` slots (S2w Open 1); spec `T14-webhook-scenario.md` | H | S2w | - | full | later |

## Items, slice INTAKE (released; waits for QR C2 for the code service; specs written after FORMS S3)
| ID | Title | Tier | Depends |
|---|---|---|---|
| I00 | **Dropped (D15)**: QR S2 is not started, so there is nothing to lift; S7c creates the frozen `tl_core/qr/codes.py` (`new_code`, `normalise_code`, `code_hash`, `grouped`) and QR S2 imports it | - | - |
| S6 | Public route and `/i/` mount, staging, limits, settings use, purge job and its delete path; owner of the `/i/` edit in `app.py`; owner approves; spec `S6-intake-public-route.md` | B | S7c, I02 |
| S7c | Commands: `IssueIntakeCode`, `RevokeIntakeCode`, `AcceptIntakeItem` (through the S3 seam), `RejectIntakeItem`; plus `tl_core/qr/codes.py` (D15); spec `S7c-intake-commands.md` | B | S3, CR1 |
| I01 | Poster: `tl intake label` over the QR renderer (additive `/i/` path argument) | H | S7c |
| I02 | Plain page render `intake_page.py` (pure, escaped, script-free; provided test `provided/I02_test_intake_page.py`; ticket `I02-intake-page-render.md`) | H | S2 |
| I03 | Queue views and signed-in routes `/forms/intake/` | H | S7c |
| I04 | `tl intake ls\|show\|accept\|reject`, `tl intake code issue\|revoke\|ls` | H | I03 |
| I05 | Terminal "Intake" log beside the proposal queue | H | I03 |
| I06 | Walks with an anonymous reader on `/i/` and five readers on the queue | H | S6, I03 |
| I07 | Runbook and demo `P2-FORMS-INTAKE` | H | I04-I06 |

## Items, slice WEB (waits for FORMS C2)
| ID | Title | Tier | Depends |
|---|---|---|---|
| W1 | Vendor `survey-core` and `survey-js-ui` (MIT) with manifest rows, licence check, content-policy proof (browser probe); owner approves the licence line; spec `W1-vendor-surveyjs.md` (the tarballs ship no LICENSE file: text from upstream) | B | - |
| W2 | Fill page and the `/web/forms` mount (owner of that edit in `tl_web`; never in the round of S6); spec `W2-fill-page.md`; reads through the X4 hook routes of T04 | B | W1, B1, S3, T04 (X4 on trunk) |
| B1 | `to_surveyjs` projection (`tl_core/forms/surveyjs.py`) and `?as=surveyjs`; the first half is W2's input, so it runs before W2 | H | W1, T01 |
| B2 | Card `open_path` for the inspection and permit cards: `/web/forms/for/<key>` | H | W2 |
| B3 | Draft resume on the page | H | W2 |
| B4 | Demo and runbook | H | B1-B3 |

## Waves (workflows of at most 3 items; gates name test files, never a whole package)
| Wave | Runs together | Notes |
|---|---|---|
| 1 | S1 and S2 | **today**; S1 is light, S2 is heavy (schema); at most 2 heavy runs with PTW S1 building: the orchestrator staggers |
| 2 | S3 with workflow {T14}, then CR1 | CR1 is the wave's one confidentiality piece; it follows S3 (both edit forms `module.py`; D13) |
| 3 | workflow {T01, T13} (T02 after its provided test), then T09 | T13: INSP T00 is merged |
| 4 | S3s | needs INSP C2 and PTW C2 |
| 5 | T03, then workflow {T05, T06, T04} | CLI, MCP, routes wait for X4 C2 |
| 6 | {T07, T10}, T08, T11, T12 | |
Then INTAKE (I00, S7c, S6 and its tickets), then WEB; their specs follow in later rounds.

## APPROVALS lines needed before merge (the orchestrator never self-approves; the owner or a delegation does)
- S1 - core interface: `tl_core/forms/types.py` and `rules.py` frozen; entry-point group `throughline.form_sources`.
- S2 - schema merge `schema/modules/forms/**`, four workflow fixtures, two numbering patterns, `schema/fixtures/forms/**`
  (additive; no existing class or event changes); words `forms.*` (eight); settings `forms.draft_saves_max`,
  `forms.intake.*` (seven keys, intake off by default); service actor `svc:intake`; operational table `forms_intake_body`.
- CR1 - security: subject rows and the author-only draft rule in `tl_core/confidentiality.py`.
- S3 - core interface: the seam that runs a command inside the caller's unit of work; security: draft saves are ledger text.
- S3s - approvers: the INSP and PTW supervisors (writes in their modules), owner for the security line.
- S6 (INTAKE) - security: the public route, staging table, purge, limits. W1 (WEB) - licence line for the vendored files.

## Security rows (one wave review over `b91ee33d..<p2/ip head>`, union with the other increments' rows)
S2 `answers` never in webhook bodies, feed text or errors; S3 draft readable by the author alone, saves bounded, template
loaded by the handler and answers re-validated, hidden target refused before answers are validated, reviewer is not the
submitter; CR1 rows and the author-only rule; T03 `viewer=` lowest clearance, filter before LIMIT and counts; T04, T06,
T10 five-reader walks and 404 byte equality; S3s the hidden subject answers `None`.

## Risks and escalation triggers
- S1 and INSP T00 hold two copies of the format 1 rules until T13; S1's test copy of T00's validate half is the proof they
  agree. T00's provided test was never run: a failure on its own logic is a `2s` on T00, not a change to S1.
- Format 2 widens the field id pattern (D2) so the intake claim ids fit; ADR-0031 says "optional keys only": the owner
  sees it in the S1 APPROVALS line.
- S2 puts an operational table inside a module schema; fallback in the spec if the generator cannot.
- Shared files: `tl_core/confidentiality.py` (CR1 only), `tl_api/app.py` (S6 `/i/`, W2 `/web/forms`, separate rounds),
  awp and quality entry points (S3s appends its lines only).
- Combined schema gates OOM on the 16 GB box: gates are split per file group (S2 spec).
- Escalate: a frozen contract must change; a word the table lacks; a piece failing twice; S3 needing a `tl_core` change
  beyond the seam; the webhook text check failing (SR-X1 F3).

## Blocked / Decision
(none yet)

## Plan check
Plan-checked via forms-eval (`4 PLANCHK` of 2026-11-15, F1 to F15 and the cost cut list, answers in
`docs/build-spec/module-designs/forms-eval.md`). Differences since: D1 (intake schema folded into S2, commands stay S7c),
D2 (format 2 id pattern), D3 (CR1 and T13 listed as items; T13 joins the two rule copies). None changes scope, seams or waves.
