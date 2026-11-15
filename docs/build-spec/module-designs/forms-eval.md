# Forms — design evaluation: are permits and inspections special cases of a general forms module?

This note answers the owner ask of 2026-11-15: "Permits and inspections might be special cases of a general 'forms'
module; we should leverage something like survey.js and a custom api to serve general forms. Store and forward if
connectivity is interrupted." Status: design evaluation v0.3 (plan check applied), 2026-11-15. Design only; nothing here is built.
Decision records: ADR-0031 (accepted by the owner, 2026-11-15) and ADR-0032 (public intake, proposed; §8). The
plan of record is §8; where §4, §6 or §7 differ, §8 rules. Read with `inspections.md`, `permits.md`,
`specs/qr-workface.md` (ADR-0030),
`specs/offline-classes.md`, `docs/runbooks/api-retries.md` (P2-X1), `12-extension-plan.md` §0 (binding rules).

## 0. Verdict

**Shape (a), with a hard boundary: a forms engine in core, typed modules on top.** The engine owns *capture*:
a versioned template document, validation, conditional visibility, the projections a client needs, and one generic
way to fill a form from the terminal, the CLI, an agent tool and the web. It owns **no lifecycle**: no states, no
guards, no approvals, no numbering of another module's records. A form is a front end to a typed command, never a
second way to write.

- Inspections are a thin typed module on the engine. `quality.Checklist` (INSP-S1) already *is* a versioned,
  immutable form template; the engine adopts its question shape unchanged as template format 1.
- Permits are **not** a form. A permit is a state machine with safety guards over shared records. It uses the engine
  for three capture surfaces only (the request, the precaution ticks, type extras). `permits.md` stands.
- A small module `forms` holds general forms that have no typed home (toolbox talk, job hazard assessment, daily
  report, pre-use check).
- SurveyJS is the **web renderer only**. The stored template is Throughline's own small format; the server
  validates in Python; SurveyJS JSON is generated from it, one way.

| In flight | What happens | Why |
|---|---|---|
| INSP-S1 (built, not merged) | **Merge as-is** | Its checklist shape becomes template format 1; no event or field needs to change |
| INSP-T00 (rules, on hold) | **Release as written** | Pure functions; the generic half is lifted into core later by a move, with the quality names kept |
| PTW-S1, PTW-T00 (on hold) | **Release as written** | Precautions are already `{id, text}` lists and `issue_blockers` takes ids; the engine fits without a change |
| QR-S1 (about to merge) | **Merge as-is** | `ScanCard.open_path` is enough to reach a form; the frozen contract does not change |
| INSP T02, T11 (runner; follow-up slice) | **Move to the forms increment**, built once for every form | The runner is the engine's terminal renderer |

Licence finding: `survey-core` and `survey-js-ui` 3.2.5 are MIT (npm registry, read 2026-11-15). Survey Creator,
`survey-pdf` and `survey-analytics` are commercial and must never be vendored (§2.1).

## 1. Are inspections and permits special cases of forms?

### 1.1 What is common (the engine)

| Capability | Today | In the engine |
|---|---|---|
| Template as data, versioned, never mutated | `quality.Checklist`: Draft → Published → Retired, `supersedes_id`, version n+1 | The same rule for every template; a record pins `(template id, version, content hash)` |
| Fields and sections | `yes_no_na`, `number`, `text`, `choice`; `required`, `unit`, `min`, `max`, `choices` | Format 1 = exactly these. Format 2 adds optional keys: `section` (a label; no nesting or repeating groups), `multi`, `date`, `photo`, `help` |
| Conditional logic | none | `visible_when`: a small closed condition (§2.3); a hidden field takes no answer |
| Validation | `insp_rules.validate_questions`, `validate_answers` (T00) | The same two functions, lifted to `tl_core/forms/rules.py` |
| Attachments | Files on the record (core file slots) | A `photo` field holds file ids from the existing upload routes; nothing new is stored |
| Signatures | "Verified by a controller who is not the recorder" | Not a field. A sign-off is a typed central command by the signed-in actor (§3.4) |
| Submit, review, approve | Each module's workflow | Only `forms.Submission` (general forms) has the generic one; typed records keep their own |
| Fill from every surface | Planned per module (CLI flags, a runner screen, later the phone) | Built once (§2.5) |

### 1.2 What is domain-specific and stays in typed modules

| Domain rule | Why a form engine must not own it |
|---|---|
| Permit isolation and energy lockout: `permits.Isolation` shared by several permits, verify by another person, removal refused under a live permit | A shared record with its own life and a cross-record guard; no form holds that |
| Gas tests: result computed from limits in settings, a fail suspends the permit in the same step | A safety rule with a side effect on another record |
| Validity window, shift revalidation, Lapsed as a derived word, suspend by anyone and resume by the authority | Time and state rules; a pure function of state, `valid_until` and the clock |
| Simultaneous-operations conflicts (two permits, one place; `permits.md` Later) | A query across permits, not across answers |
| Separation of duties (approver is not requester, verifier is not recorder or applier) | Access rules on typed commands, checked against the context actor |
| Hold points tied to an ITP; `point` on the inspection; hold-point release | Planning data linked to IWPs and, later, `ITP` lines |
| Punch items raised from failed questions, category by point | A write into `quality.PunchItem` in the same unit of work |
| Readiness checks `inspections_planned`, `permits_planned` | The frozen readiness contract; reads typed tables |
| Result of an inspection (`accept`, `reject`, `conditional`); `fails_when` | Meaning, not shape. `fails_when` is stored in the template but read only by `quality` |

The line: **shape and capture are generic; meaning and consequence are typed.** The engine validates that an answer
is well formed for its field. It never decides what an answer causes.

### 1.3 Why (a), and not (b) or (c)

- **(c) no forms module** leaves three template shapes (checklist questions, permit precautions, X5a extras) and a
  fill path per module and surface. **(b) ad-hoc forms only** adds a fourth shape and gives store and forward
  nothing to send for inspections, punch or requisitions.
- **(a)** costs one core contract and one ADR and reworks nothing in flight. Its risk is the inner platform;
  ADR-0031 forbids it by contract: no workflow, no expression language beyond §2.3, no computed fields, no code or
  URL in a template. Property sets (X5a) stay: typed extra fields on a record, not a capture event.

## 2. SurveyJS and the alternatives

### 2.1 Licences (npm registry `latest`, read 2026-11-15)

| Package | Version | Licence | Use |
|---|---|---|---|
| `survey-core` (model, validation, expressions; no dependencies) | 3.2.5 | MIT | Yes, vendored |
| `survey-js-ui` (plain-JS renderer; peer `survey-core`) | 3.2.5 | MIT | Yes, vendored |
| `survey-creator-core` (the drag-and-drop designer) | 3.2.5 | "SEE LICENSE IN LICENSE" (commercial) | **Never** |
| `survey-pdf`, `survey-analytics` | 3.2.5 | "SEE LICENSE IN LICENSE" (commercial) | **Never** |
| `@jsonforms/core`, `@jsonforms/vanilla-renderers` | 3.8.0 | MIT | Alternative; renderers need React and a build |
| `@rjsf/core` | 6.11.1 | Apache-2.0 | Alternative; React and a build |
| `@formio/js` (renderer) | 5.7.1 | MIT | Alternative; drags Bootstrap, Quill, moment; built for the Form.io server |

`just check` runs `dev/tools/check_licences.py`. Vendored JavaScript is checked through
`packages/tl-web/src/tl_web/static/vendor/VENDORED.toml` (name, version, licence, url, sha256 per file); MIT passes,
and a statement that is not permissive is refused. To confirm before the vendoring ticket: (1) the LICENSE text
inside the two tarballs matches the MIT field; (2) the size of the two prebuilt files (the unpacked tarballs are
70 MB and 5 MB, mostly other builds and typings); (3) the renderer works under the web client's strict
content-security policy (no inline script or style); (4) a manifest row with a commercial statement is refused (add
the test). Templates are written as YAML or JSON through the CLI, the terminal and agent proposals, so the
commercial Creator is not needed.

### 2.2 Why SurveyJS for the web renderer, and why not as the stored format

For: the two MIT packages ship prebuilt files with no runtime dependency (vendored, unedited, no JavaScript build),
and the model runs wholly in the browser, which store and forward needs. Against as the stored format: SurveyJS
JSON is a large open format with a string expression language, HTML questions and URL-loaded choices, and has no
Python implementation; the server must validate in Python by rules it owns. JSON Forms and RJSF need React and a
bundler; their good part is kept: every template projects to a JSON Schema (§2.5).

### 2.3 The template document (format 1 and 2)

A template document is a bounded JSON list of fields. Format 1 is the INSP-S1 question:
`{id, text, kind, required, unit, min, max, choices, fails_when}`, at most 60, text ≤ 200, choices ≤ 8.
Format 2 adds optional keys only: `section` (≤ 64), `help` (≤ 300), kinds `multi`, `date`, `photo`, and
`visible_when`. A condition is one of `{q, is}`, `{q, in}`, `{q, gte}`, `{q, lte}`, `{q, answered}`, or
`{all: [...]}`, `{any: [...]}`, `{not: ...}`, at most 3 deep, naming only earlier fields (so no cycles).
Not in any format: free expressions, computed values, HTML, URLs, scripts, repeating groups.
`validate_questions` today refuses an unknown key; format 2 relaxes that in pure code. No stored checklist becomes
invalid and no event changes.

### 2.4 Templates as data, submissions as typed events

- **Where a template lives.** The engine reads template documents; it does not care which record stores one.
  `quality.Checklist.questions` (INSP-S1), the precaution list of a permit type (`schema/fixtures/permits/types.yaml`)
  and `forms.Template.fields` are all sources. A module registers a **form source** per record type under the
  entry-point group `throughline.form_sources` (the scan-card pattern of ADR-0030).
- **Never mutated.** A Published template never changes; a change is version n+1 that supersedes it. Every template
  version has a `content_hash` (SHA-256 of the canonical JSON). A record that uses a template pins id, version and
  hash. `Checklist.*` events already work this way; `forms.Template` copies them.
- **A submission is a typed command.** A form source answers, for a record and a viewer, a **binding**:
  the pinned template, the command to send (`RecordInspectionResult`, `RequestPermit`, `IssuePermit`, `SubmitForm`),
  its fixed arguments (`inspection_id`, `expected_version`) and the argument that takes the answers. The client sends
  that command through the command door. The events written are the typed module's own
  (`Inspection.ResultRecorded`, `Permit.Requested`); for a general form, `forms.Submission.Submitted`
  `{template_id, template_version, template_hash, subject_id, answers}`. No generic "FormSubmitted" event stands in
  for a typed one.
- **The client is never trusted.** The handler loads the pinned template itself, recomputes which fields are visible
  from the answers, refuses an answer to a hidden or unknown field, a missing required answer, a wrong type or a
  bound breach, and computes every derived value (inspection result, gas result). The actor comes from the context,
  never from the body. What the browser validated is a courtesy to the person.

### 2.5 One template, four surfaces (forms are not web-only)

Pure projections in `tl_core/forms/`, each a function of the template document:

| Surface | Projection | Notes |
|---|---|---|
| Terminal | `runner` model (the INSP T02 design, made generic): one field per screen, back, forward, review, confirm | No rule in the screen; `tui-layout` applies |
| CLI | `tl form show <template>`, `tl form fill <record or template> --answer q1=yes ... \| --answers-file F` | `tl insp record` stays and calls the same functions |
| Agent (MCP) | `get_form` returns the template and its JSON Schema for answers; `propose_form_submission` files a proposal a person accepts | Closed until listed; no agent submits, signs or reviews; the idempotency key of X1 applies |
| Web | `to_surveyjs` (one way) for the fill page; a server-rendered read view of answers | The scan page stays script-free |

The JSON Schema states types, enums, bounds and required fields; the Python rules stay the authority (conditions
included). A property test pins that the projections agree on every fixture template.

## 3. The forms API

The API is small because writes stay at the command door. Routes come from the `forms` module (in its own package;
the hook declaration follows P2-X4 C2, as for permits).

### 3.1 Routes

| Route | Answers |
|---|---|
| `GET /forms/templates` | Published templates the viewer may use: id, title, version, bound record type. Count after the filter |
| `GET /forms/templates/{id}/versions/{n}` | The template document, `content_hash`, state. `?as=jsonschema` gives the projection (`surveyjs` arrives with FORMS-WEB). Immutable for a Published version, so `ETag` = hash |
| `GET /forms/for/{record key}` | The binding for this record and viewer: template ref, command name, fixed arguments, `expected_version`, prefilled answers. `available: false` with a fixed reason word when the record is visible but its state takes no form |
| `GET /forms/submissions`, `/forms/submissions/{key}` | General-form submissions (list, one). The CSV and JSONL export is deferred (plan check F11) |
| `POST /commands/{Name}` (exists) | The write, online. `Idempotency-Key` as in P2-X1 |
| `POST /forms/deliveries` (Phase 3) | The write, when it was queued offline (§4.2). Wraps the same dispatch; adds the late checks and the delivery record |
| `POST /uploads` … `/complete`, `POST /files/attach` (exist) | Attachments. A `photo` answer holds the file ids |

**Drafts (owner decision 3: kept on the server).** `forms.Submission` has a `Draft` state; `SaveFormDraft` (word
`forms.submit`) writes `Submission.DraftSaved` with the partial answers, checked for shape only (required fields may
be missing). A draft is readable by its author alone, takes no number until submitted, and is discarded by
`DiscardFormDraft`. Every save is a permanent event, so the client saves on "Save draft" and on leaving the page,
not per keystroke, and a draft takes at most `forms.draft_saves_max` saves (default 50). Draft saves are ledger text: they take the template's `answer_class`,
get a security review row and the five-reader walk (F14). Server drafts cover general
forms; a typed record keeps its own waiting state (an inspection is Scheduled until recorded) and its partial
answers stay on the device. `SaveFormDraft` is a drafting command, so it may be queued (§4.2).

### 3.2 Access words

| Word → table word | Covers |
|---|---|
| `forms.view` → read | The read routes above |
| `forms.template.edit` → user | Create and edit a Draft template |
| `forms.template.publish` → controller | Publish, revise, retire |
| `forms.submit` → user | `SubmitForm` (general forms only) |
| `forms.review` → controller | Accept or return a general submission; never the submitter |
| `forms.void` → controller | Void a submission, with a reason |

A forms word never grants a typed command. Sending `RecordInspectionResult` through a form needs
`quality.inspection.record`, exactly as from the CLI. Agents hold none of these until allowed, and never a
controller word.

### 3.3 Hidden looks exactly like missing

- `GET /forms/templates/{id}/versions/{n}`: unknown id, unknown version, a Draft the viewer may not edit and a
  template restricted to a module the viewer has no view word for give the same 404, byte for byte.
- `GET /forms/for/{key}`: unknown key, hidden record and a record type with no form source give the same 404.
  `available: false` is only ever said about a record the viewer can already read.
- A write that names a hidden or unknown target is refused as a missing record **before** the answers are
  validated, so a validation message can never confirm that a hidden record exists. The same holds for a late
  delivery and for an idempotent replay (X1 already re-checks the viewer on replay).
- Lists, counts and exports filter before LIMIT and before counting. Every route, tool and export gets the
  five-reader walk (`AGENTS.md`).

### 3.4 Confidentiality of answers, and signatures

- A template is company reference data at the lowest class. It must carry no project text; the publish command
  cannot check meaning, so the runbook says it and the reviewer of a template is a controller.
- Answers are record text. A typed submission is hidden through its record's subject (inspection → subject,
  permit → `for_record_id`), with no new rule. A general submission is hidden through `subject_id` when it names a
  record, and otherwise takes the template's `answer_class` (default the lowest; a template for incident or medical
  reports sets it higher). One part is added to the subject rule in `tl_core/confidentiality.py` (a security row).
- Answers never go into feed text, webhook bodies, error texts or access logs. The answers payload is on the
  redaction list from the first event (see the open finding SR-X1 F3 on webhook detail). Not searched in v1.
- **Signatures.** Three things are called a signature; only one has authority. (1) *Who submitted*: the context
  actor on the event; nothing to build. (2) *A sign-off* (verify, approve, issue): a typed controller command, a
  central act, valid only over the recorded state (`deployment-and-merge.md` §4); never a form field, never queued
  offline. (3) *A drawn signature* (a crew member without an account signs a toolbox talk): a `photo`-kind
  attachment; it is evidence, it grants nothing. Witness sign-off by guest link stays in Phase 3.

## 4. Store and forward

**Deferred to Phase 3 by the plan check; the design is in `forms-store-and-forward.md`, with its section numbers
(§4.1 to §4.6) kept.** In one line: a client outbox of commands, delivered once with the P2-X1 key, run by the
authority under the rules of the moment of receipt; a fact is accepted late, an act is refused if its target moved,
nothing is merged. Its first version uses the receipt time only. Owner decisions 4, 5 and 6 land with it.

## 5. Fit with QR (ADR-0030)

Nothing in ADR-0030, the scan-card contract (`tl_core/qr/types.py`) or QR-S1 changes.

- A QR on an inspection or a permit opens the status card, as designed. The card's one link, `open_path`, must start
  with `/web/`. The inspection and permit card tickets (INSP T09, PTW T09) set it to `/web/forms/for/<key>` once the
  forms page exists, and to the record page until then. The forms page shows the status line first, then the form
  if the state takes one (`available`), then a link to the record.
- A general form's subject (a scaffold, an area) works the same way through that record's card. A label for a blank
  form (a toolbox-talk sheet on the trailer door) is a later ticket: the code targets the `forms.Template` record.
- Carried over unchanged: sign-in before any lookup, one 404 for every miss, agents refused on `/web`, no state on
  paper, no anonymous status route. Zero-login intake (§8.2, ADR-0032) is a separate write-only path, `/i/`.

## 6. Cost and plan delta

### 6.1 In-flight work

| Item | Verdict | Change |
|---|---|---|
| QR increment (3 pieces, tickets as planned) | Survives whole | Later: one ticket for the offline shell (forms second slice) |
| INSP-S1 | Merge as-is | None |
| INSP-T00 | Release | None now. Forms S1 later moves `validate_questions` and `validate_answers` to core and leaves re-exports |
| INSP-S2 (not yet specified) | Survives | None (receipt time only; no `captured_at` input in the first version) |
| INSP-S3, T01, T03–T10, T12–T15 | Survive | T04 `tl insp record` keeps its flags and calls the shared functions |
| INSP T02, T11 (follow-up slice) | **Move** to forms | Built once as the generic runner; INSP gets it by registering a form source |
| PTW-S1, PTW-T00, S2–S5, T01–T16 | Survive whole | Later: one ticket for a form source on `RequestPermit` and the precaution ticks |

INSP goes from 3 pieces and 16 tickets to 3 pieces and 14. PTW stays at 5 pieces and 17. Neither waits for forms.

### 6.2 The forms path

Slices, pieces, tickets and order are in §8.3 (the first table here was replaced by it).

### 6.3 Risks

| # | Risk | Answer |
|---|---|---|
| R1 | New core interface (`tl_core/forms/types.py`, entry-point group `throughline.form_sources`) | ADR-0031 and an APPROVALS line before merge; planner-tier check (over 10 tickets) |
| R2 | Schema is additive only; events never change; no migration | Format 1 is INSP-S1's shape as built. Format 2 adds optional keys in a JSON value, checked by rules. The delivery record is a new event type. Nothing existing is edited |
| R3 | Inner platform: the engine grows a workflow or a scripting language | The closed condition grammar and the "no lifecycle" rule are in the ADR; a request past them is a new ADR |
| R4 | First substantial client JavaScript; the gate has no browser | Keep outbox logic in one small module with no DOM, tested by `node --test` (Node 22 is in the build environment); the renderer is vendored and unedited; a manual device checklist in the runbook |
| R5 | Strict content-security policy against a third-party renderer | Confirm in the vendoring ticket before anything depends on it. Fallback: a server-rendered form page (no renderer), which still serves online use |
| R6 | Answers at rest on a shared phone | Only lowest-class subjects are sent to a device (`offline-classes.md` §6); storage keyed by account; wipe at sign-out; photos included |
| R7 | A crew trusts a queued item as if it were recorded | The page says "Not sent yet" until the server answers; no number is shown before the authority gives one |
| R8 | Late delivery beyond the idempotency window writes twice once the purge job exists | `forms.late_accept_hours` below the retention; the delivery route enforces it |

## 7. Recommended plan delta (concrete)

1. **Now.** Merge QR-S1 and INSP-S1 as planned. Release INSP-T00, PTW-S1 and PTW-T00 from hold, unchanged.
2. **INSP.** Take T02 and T11 (the runner) off the INSP follow-up table and point them at the forms increment.
   Card tickets (INSP T09, PTW T09): `open_path` is the record page now, the forms page once it exists.
3. **Plan P2-FORMS** as §8.3. No forms schema, vendored JavaScript or `tl-web` change before its gate.

### Owner decisions (decided 2026-11-15: "Yes to all")

| # | Question | Decided |
|---|---|---|
| 1 | Accept ADR-0031: engine contract in core, Throughline's own template format, no lifecycle in the engine? | **Yes.** ADR-0031 is accepted |
| 2 | Vendor `survey-core` and `survey-js-ui` (MIT) into the web client as the fill renderer? | **Yes**, for the fill page only; the fallback is a server-rendered page if the security policy cannot hold |
| 3 | Server-side drafts? | **Yes.** A `Draft` state on `forms.Submission` (§3.1). This reverses the evaluation's default |
| 4 | May anything about a permit be queued offline? | **Yes**, read narrowly: only facts that tighten (a late suspend, a late failing gas reading); nothing that makes work more permitted (§4.2, §4.4). Reverses the default |
| 5 | May a phone show a cached status "as of" for non-permit records when offline? | **Yes**, always stamped "as of", never shown as live; permit status is never cached (§4.6). Reverses the default |
| 6 | How old may a queued item be? | **72 hours** (`forms.late_accept_hours`) |
| 7 | Who reviews a general submission? | **A `forms` controller who is not the submitter** |

## 8. Plan of record, 2026-11-15: owner answers, zero-login intake (ADR-0032), plan check applied

### 8.1 What the seven answers change

| Decision | Change | Where |
|---|---|---|
| 3 server drafts | `Draft` state, `SaveFormDraft`, `DiscardFormDraft`, `forms.draft_saves_max`; resume in the runner and on the fill page; security row and walk | First slice S2, S3; +2 tickets |
| 4 tightening permit facts | `TIGHTENING_COMMANDS`, pass-is-refused, the "use the radio" screen; one line each in `permits.md` §4 and `offline-classes.md` | FORMS-SF (Phase 3) |
| 5 status "as of" | Status lines in the "my work today" payload; `forms.offline_status_max_hours` | FORMS-SF (Phase 3) |
| 6 late window 72 h | `forms.late_accept_hours` | FORMS-SF (Phase 3) |
| 1, 2, 7 | As the defaults | n/a |

### 8.2 Zero-login intake (ADR-0032, proposed; the slice is held until the owner accepts it)

A stranger opens `/i/<code>` from a poster, fills at most 8 plain fields ("I need an X", "Sign on to X") and gets a
receipt word. The page tells nothing about any record (ADR-0030's sign-in rule is untouched). The submission is
staged on its own stream `forms.IntakeItem`, not the proposal queue: a proposal is a whole command prechecked
against the target (an oracle for an anonymous filer) and stored for ever. The typed text sits in a purgeable
operational table; the event carries a keyed hash only. A signed-in controller accepts it as a typed command or
rejects it. A name is a claim: it grants nothing, and a poster sign-on is attendance only. Controls: hourly limits
per address and per presented code (one 429), a pending cap, 8 KB bodies, a honeypot, expiry on every code, off by
default, one neutral 404 for every dead code. No photo, captcha, SurveyJS, outbox, merge or person matching in v1.

### 8.3 Slices, pieces and tickets

| Slice | Pieces | Tickets | Holds | Exit demo |
|---|---|---|---|---|
| P2-FORMS first slice | 4 | about 12 | S1 core contract and rules (with the `intake: public` profile check). S2 schema of `forms` (drafts included). S3 commands, and the one seam that runs a command inside the caller's unit of work (F3). S3s form sources for quality and permits (a piece: it writes in two other modules; approver: the INSP and PTW supervisors). Tickets: JSON Schema projection, views, read routes, `tl form`, MCP tools, runner model, runner screen, draft resume, generator, walks, demo, docs | Fill and submit a general form and an inspection result from the terminal and the CLI; save and resume a draft |
| P2-FORMS-INTAKE (held, F1) | 2 (1 if S7 is folded into S2) | about 7 | S6 public route and `/i/` mount, staging table, limits, settings, the purge job and its delete path (security-class). S7 schema and commands for `IntakeCode` and `IntakeItem`: issue, revoke, accept-as, reject; folded into S2 if ADR-0032 is accepted before S2 is specified. Tickets: poster label, plain page render, queue views and routes, `tl intake`, terminal "Intake" log, walks with an anonymous reader, runbook and demo | Print a poster, submit with no login, accept it as a requisition, reject one, purge |
| P2-FORMS-WEB | 2 | about 4 | W1 vendoring of the two MIT files, manifest rows and the content-policy check (a piece; licence gate). W2 fill page and its `/web/forms` mount. Tickets: `to_surveyjs` and `?as=surveyjs`, card `open_path`, draft resume on the page, demo and runbook | Fill an inspection from a scanned card in a browser |
| Phase 2 total | **8 (or 7)** | **about 23** | Two ADRs | |
| P2-FORMS-SF, moved to Phase 3 | 2 | about 9 | S4 delivery route, late rules, `forms.Delivery.Received` (uses the S3 seam; receipt time only). S5 service worker, outbox and the offline QR shell (scope `/web/q/`; security row, F5). Tickets: "my work today", needs-attention view, tightening permit facts (2), status "as of", `node --test` step, settings, runbook, demo | Queue offline, deliver once, refuse a moved target |

Order and dependencies (F7, F10): S1 starts at INSP C1 (the checklist rules exist). S3s waits for INSP C2 and PTW
C2. Routes and CLI groups wait for P2-X4 C2 (hooks). Intake waits for QR C2 (the code service); generating,
normalising and hashing a code is lifted into `tl_core/qr` there, or by the first intake ticket as a move with
re-exports, so `forms` never imports the `qr` module.

Owners and gates (F8, F9, F12):
- `tl_core/confidentiality.py` subject rows (QR scan codes, inspections, permits, `forms.Submission` and drafts,
  `forms.IntakeItem`) are added by **one serialised builder piece per wave, CONF-ROWS**; no forms, QR, INSP or PTW
  piece edits that file.
- `tl_api/app.py` and the `tl_web` mount: W2 owns the `/web/forms` edit and S6 owns the `/i/` edit; each is the
  only piece of its slice to touch those files, and they do not run in the same round.
- Human gates name the **owner** as approver for the security ones (S6, S4, S5, CONF-ROWS, the draft row); the S3
  seam and S1 are core-interface gates with an APPROVALS line. Each security review row lists its commit range.

New names: words `forms.intake.issue`, `forms.intake.review` (controller); settings `forms.draft_saves_max`,
`forms.intake.enabled` (off), `.rate_per_address_per_hour`, `.rate_per_code_per_hour`, `.pending_per_code_max`,
`.retention_days`, `.code_max_days`; actor `svc:intake`. Phase 3: `forms.late_accept_hours`,
`forms.offline_status_max_hours`.

Stays out: a status or tracking page for a stranger; messages back to the submitter; accounts from a sign-on;
captcha; photos and SurveyJS on `/i/`; agents reading staged text; guest links (Phase 3 I8: one known party, one
command); a web page for the controller queue. Deferred: submissions export, intake merge and person matching, the
intake outbox, device time as valid time.

### 8.4 Owner questions on ADR-0032 (decided 2026-11-15: yes to all three; the intake slice is released)

| # | Question | Default (owner: yes) |
|---|---|---|
| 1 | Accept ADR-0032 as written (write-only, staged, own stream, off by default)? | Yes |
| 2 | May a public form ask for a phone number, kept at most 30 days unless a controller accepts it into a record? | Yes, optional per template |
| 3 | Is a poster sign-on to a permit briefing attendance only until a signed-in controller confirms it? | Yes |

## Plan check
4 PLANCHK forms-eval.md (2026-11-15), 15 findings; all accepted by the orchestrator; answers applied 2026-11-15.
- F1 HI INTAKE slice held until the owner accepts ADR-0032 (and its phone default).
  Answer: §8.2, §8.3, §8.4 and ADR-0032 Consequences: the slice is held until the owner accepts the ADR and the phone default.
- F2 HI body_hash: HMAC with a per-item salt kept and purged with the body, never a plain hash in the event.
  Answer: ADR-0032 decision 5: `body_mac`, an HMAC-SHA-256 under a random per-item salt kept in the body row and purged with it.
- F3 HI name the piece that owns the uow hook for Delivery.Received / IntakeItem.Accepted (run_command opens its own uow).
  Answer: Forms S3 owns one seam that runs a command inside the caller's unit of work (the shape `accept_proposal` uses); S4 and intake accept reuse it (§8.3, both ADRs).
- F4 HI on_behalf_of_claim and matched_person_id live on IntakeItem.Accepted only, never in other modules' command payloads.
  Answer: ADR-0032 decisions 7 and 8: the claim lives on `IntakeItem.Accepted` only; no other module's command or event carries it.
- F5 HI settings+purge job folds into S6 (job kind + DELETE path = piece); offline QR shell (SW scope /web/q/) moves into S5 with a Sec row.
  Answer: Settings and the purge job are inside S6; the offline QR shell is inside S5 with a security row (§8.3).
- F6 MD quality/permits form sources and SurveyJS vendoring are pieces (or name the dependency and its approver).
  Answer: Form sources are piece S3s and vendoring is piece W1, each with a named approver (§8.3).
- F7 HI intake depends on QR C2; code generate/hash lifted into tl_core/qr.
  Answer: Intake waits for QR C2; code generate, normalise and hash move to `tl_core/qr` (§8.3, ADR-0032 decision 3).
- F8 MD one owner for confidentiality.py SUBJECT_LINKS rows; rows serialised across QR S2, INSP, PTW, forms S2/S7.
  Answer: One serialised builder piece per wave, CONF-ROWS, owns every subject row (§8.3).
- F9 MD name the owner of tl_api/app.py and tl_web mount edits for the fill page and /i/.
  Answer: W2 owns the `/web/forms` mount edit and S6 the `/i/` edit; never in the same round (§8.3).
- F10 MD forms S1 starts at INSP C1; source tickets wait INSP/PTW C2; routes wait X4 C2.
  Answer: Applied in §8.3 "Order and dependencies".
- F11 MD exit demo per slice; cut the intake outbox; defer submissions export, ?as=surveyjs before FORMS-WEB, intake merge/match.
  Answer: Exit demo column in §8.3; the intake outbox is cut; export, `?as=surveyjs` before FORMS-WEB, merge and match are deferred (§3.1, §8.3, ADR-0032).
- F12 MD human gates name an approver; Sec rows listed with commit ranges.
  Answer: The owner approves the security gates; each security row lists its commit range (§8.3).
- F13 MD backup retention bounded under retention_days (runbook); per-code limiter keyed so a 429 does not reveal a live code.
  Answer: ADR-0032 decisions 10 and 11: the per-code counter is keyed on the presented code whether or not it is live; backups that hold the body table are kept no longer than `forms.intake.retention_days` (runbook).
- F14 MD drafts: Sec row and five-reader walk; draft saves are ledger text.
  Answer: §3.1, §8.1 and ADR-0031 decision 13: drafts get a security row and the five-reader walk; a save is ledger text.
- F15 LO render time signed with the item key.
  Answer: Not applicable while the fill-time check is cut; if it returns, the render time is signed with the item key (ADR-0032 decision 10).
- COST cut list: S4 receipt time only in v1; S6 drops photo and fill-time paths; FORMS-SF to Phase 3; fold S7 into S2 if ADR-0032 accepted first.
  Answer: All four taken: receipt time only (§4.5); no photo or fill-time path in S6; FORMS-SF moved to Phase 3; S7 folds into S2 if ADR-0032 is accepted first (§8.3).
