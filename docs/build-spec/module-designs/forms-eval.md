# Forms — design evaluation: are permits and inspections special cases of a general forms module?

This note answers the owner ask of 2026-11-15: "Permits and inspections might be special cases of a general 'forms'
module; we should leverage something like survey.js and a custom api to serve general forms. Store and forward if
connectivity is interrupted." Status: design evaluation v0.1, 2026-11-15. Design only; nothing here is built.
Decision record: ADR-0031 (proposed). Read with `inspections.md`, `permits.md`, `specs/qr-workface.md` (ADR-0030),
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

- **(c) no forms module** leaves three template shapes in the product within a month (checklist questions, permit
  precautions, the property-set extras of X5a) and a fill path per module and surface, the phone included (both
  designs list it under Later).
- **(b) forms for ad-hoc checklists only** adds a fourth shape next to the three and gives the store-and-forward
  client nothing to send for inspections, punch walkdowns or requisitions. The offline queue is the costly part of
  this ask; it must be built once and carry typed commands.
- **(a)** costs one core contract and one ADR. It reworks nothing in flight because the engine adopts what INSP-S1
  built.
- The risk of (a) is the inner platform: a forms engine that grows states, rules and scripting until permits are
  "configured" rather than built. ADR-0031 forbids it by contract: no workflow, no expression language beyond §2.3,
  no computed fields, no code or URL in a template.
- Property sets (X5a) stay: typed extra fields *on a record*, moved by schema packages. A form is a capture *event*
  against a pinned template. Neither replaces the other.

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

For: the two MIT packages ship prebuilt files with no runtime dependency, which fits the repository's rule of
vendored, unedited files and no JavaScript build. Its model runs wholly in the browser, so a form can be filled with
no server, which store and forward needs. It covers every field kind of §1.1 and pages, panels and visibility rules.

Against as the source of truth: SurveyJS JSON is a large open format with a string expression language
(`visibleIf`, `requiredIf`, calculated values, custom functions), HTML questions and choices loaded from a URL. There
is no Python implementation. Storing it would mean either trusting the client's evaluation or running Node on the
server for every submission. Neither is acceptable: the server validates, in Python, by rules it owns.

JSON Forms and RJSF validate by JSON Schema (`jsonschema` is already a dependency) but need React and a bundler,
which the repository does not have. Their good part is kept: every template projects to a JSON Schema (§2.5).

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
| `GET /forms/templates/{id}/versions/{n}` | The template document, `content_hash`, state. `?as=jsonschema\|surveyjs` gives a projection. Immutable for a Published version, so `ETag` = hash |
| `GET /forms/for/{record key}` | The binding for this record and viewer: template ref, command name, fixed arguments, `expected_version`, prefilled answers. `available: false` with a fixed reason word when the record is visible but its state takes no form |
| `GET /forms/submissions`, `/forms/submissions/{key}`, `/forms/submissions/export` | General-form submissions (list, one, CSV or JSONL) |
| `POST /commands/{Name}` (exists) | The write, online. `Idempotency-Key` as in P2-X1 |
| `POST /forms/deliveries` | The write, when it was queued offline (§4.2). Wraps the same dispatch; adds the late checks and the delivery record |
| `POST /uploads` … `/complete`, `POST /files/attach` (exist) | Attachments. A `photo` answer holds the file ids |

**Drafts.** No server-side draft route in v1. A draft lives on the client (browser storage, or the runner's state).
A draft is partial, private and frequent, and every stored thing here is a permanent event; typed records already
have waiting states (an inspection is Scheduled until recorded). The additive path later is a `Draft` state on
`forms.Submission` with `SaveFormDraft` (owner decision 3).

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

### 4.1 What it is, and what it is not

Store and forward is a **client outbox of commands**. Nothing is written to any ledger while offline. When the
client can reach the server it delivers each queued command once, and the authority runs it then, under the rules
of that moment. It is not the Phase 3 replica sync (`offline-classes.md` §6): no local segment, no merge, no second
node kind, and `TL_NODE_KIND` stays `authority`. An outbox item has the shape Phase 3 calls `PendingCommand`, so the
replica work later reuses it rather than replaces it.

The client is the web client installed as a page with a service worker, scope `/web/forms/` in the first slice. It
keeps: the app shell, the vendored renderer, the Published templates it was sent, the bindings fetched while online
("my work today": inspections scheduled for me, the general forms of my project), an outbox and file blobs, all in
browser storage keyed by account. A native app (Phase 5) or a terminal outbox would use the same routes; neither is
in these slices.

### 4.2 What may be queued

One rule, already written: `tl_core.offline.capture_allowed(record_type, command, node="device")`. The delivery
route refuses everything else, and `GET /record-types` already tells a client which commands those are.

| Command | Class of its type | Queued? |
|---|---|---|
| `SubmitForm` (general form) | `forms.Submission`: `draft_only`, drafting command | Yes |
| `RecordInspectionResult` | `quality.Inspection`: `draft_only`, drafting command (`inspections.md` §3) | Yes |
| `RaisePunchItem`, `RaiseRequisition` (exist) | `draft_only` | Yes, once each has a form source |
| `PlanInspection`, `ScheduleInspection` | `draft_only`, not drafting | No |
| Every permit, isolation and gas-test command | `none` (`permits.md` §4) | **No** (owner decision 4) |
| Any controller command (verify, approve, issue, publish, void) | any | **Never** (`central_act`) |

### 4.3 Delivery and idempotency

- The client mints one `Idempotency-Key` per outbox item when the person presses Submit, and reuses it on every
  retry. The delivery route passes it to the same idempotency service as the command door, scoped to the actor, so
  a retry through either door replays the first answer and writes nothing new (P2-X1).
- Attachments are uploaded first through the existing upload routes (content-addressed, so a re-upload is harmless),
  then the command is delivered with the file ids. A command whose files are not complete is not sent.
- Each delivery carries `captured_at` (the device clock when Submit was pressed) and `device_now`. On success the
  route writes one event of its own in the same unit of work, `forms.Delivery.Received`
  `{command, target_id, captured_at, received_at, clock_skew_s, queued_s}`, caused by the command's event. No
  existing event or envelope changes. A refusal writes nothing, as in X1; the item stays on the device.
- A key must not outlive the idempotency window. `forms.late_accept_hours` (default 72, must be below
  `idempotency.retention_days`) bounds how old a queued item may be; an older one is refused as `too_late` and the
  person re-submits it by hand. The X1 purge job is deferred today, so this bound is what makes that job safe later.
- The session lasts 12 hours. A device offline for longer signs in again before anything is sent. An outbox belongs
  to one account; another account on the same device cannot read or send it; sign-out asks, then wipes.

### 4.4 When the world moved while the device was offline

Principle: **a fact is accepted late with its own time; an act is refused if its target moved; nothing is merged.**

| Situation at delivery | Outcome |
|---|---|
| General form, template version still Published | Accepted |
| General form, template superseded or retired since capture | Accepted late against the **pinned** version if it was Published at `captured_at` and the item is inside the late window; marked `template_superseded`. Otherwise refused `template_retired` |
| Inspection result, inspection still Scheduled, `expected_version` matches | Accepted; answers validated against the version pinned at scheduling |
| Inspection rescheduled or re-pinned meanwhile (`expected_version` differs) | Refused `stale_version`. Never auto-applied: the answers may belong to another checklist version |
| Inspection already Done by someone else, or Cancelled | Refused by the state guard. The answers stay on the device, exportable, for the QA lead to judge |
| The target is now hidden from the actor (class raised, access removed) | Refused as a missing record; the device learns nothing more |
| The actor lost the command's word, or the account is disabled | Refused; nothing is written on a past permission |
| A queued item names a permit command (an old client) | Refused `online_only`; never dropped silently |
| An inspection whose subject is a permit that was suspended meanwhile | Accepted: it records what was seen at `captured_at`. The record view shows capture and receipt times beside the suspension |

A refused item is never deleted by the client. It moves to "Needs attention" with the fixed reason word; the person
may open it against the current record, carry the answers over by field id, and submit with a **new** key (X1).

**Permits.** Nothing about a permit is queued. A late "suspend" and a late failing gas reading only make things
stricter and are real wants, but both change `permits.md` (class `none`): owner decision 4, not a default. A queued
"stop work" must never let a crew believe the permit is suspended for everyone; radio and the paper rule.

### 4.5 Clocks and valid time

- The authority's `recorded_at` is the only trusted time and is set as always. `captured_at` is a claim.
- Skew is measured at delivery (`device_now` against the server clock). Within `forms.clock_skew_max_seconds`
  (default 120) the claim is used for the typed valid-time field (`done_at`, later `taken_at`; the fields ADR-0026
  would tag `tl:valid_time`). Outside it, or when `captured_at` is in the future or earlier than the target's last
  event, the valid-time field takes the receipt time and the delivery record keeps the claim, marked
  `clock_suspect`.
- No guard that makes work *more* permitted may rest on a device time. "A passing gas test newer than 240 minutes"
  is always counted from the receipt time. A device time may only make things stricter or be shown as information.

### 4.6 QR scan at the workface while offline

| Works offline | Does not, by design |
|---|---|
| Opening the forms page the person installed, and filling any form fetched while online | Any live status, above all whether a permit is live, suspended or lapsed. A card is `no-store` (ADR-0030 decision 9); no state is cached on the phone, not even "as of" |
| After the second slice: a scan of a label whose record is in "my work today" opens that record's **form**, with a banner "Offline: status unknown. The paper on site rules." The server sends the SHA-256 of each such code with the binding, so the device matches a scan without storing a code | A scan of any other label: the phone's own error page, as today |
| Typing or scanning in the trailer on a replica: `tl qr resolve` with "as of last sync" (ADR-0030 decision 10) | Signing in, or renewing an expired session |

The second slice widens the service worker's scope to `/web/q/` for the offline shell only; online, the scan page
stays script-free. That change to the web client is in ADR-0031's gate list.

## 5. Fit with QR (ADR-0030)

Nothing in ADR-0030, the scan-card contract (`tl_core/qr/types.py`) or QR-S1 changes.

- A QR on an inspection or a permit opens the status card, as designed. The card's one link, `open_path`, must start
  with `/web/`. The inspection and permit card tickets (INSP T09, PTW T09) set it to `/web/forms/for/<key>` once the
  forms page exists, and to the record page until then. The forms page shows the status line first, then the form
  if the state takes one (`available`), then a link to the record.
- A general form's subject (a scaffold, an area) works the same way through that record's card. A label for a blank
  form (a toolbox-talk sheet on the trailer door) is a later ticket: the code targets the `forms.Template` record.
- Carried over unchanged: sign-in before any lookup, one 404 for every miss, agents refused on `/web`, no state on
  paper, no anonymous route.

## 6. Cost and plan delta

### 6.1 In-flight work

| Item | Verdict | Change |
|---|---|---|
| QR increment (3 pieces, tickets as planned) | Survives whole | Later: one ticket for the offline shell (forms second slice) |
| INSP-S1 | Merge as-is | None |
| INSP-T00 | Release | None now. Forms S1 later moves `validate_questions` and `validate_answers` to core and leaves re-exports |
| INSP-S2 (not yet specified) | Survives | Its spec gains one optional input on `RecordInspectionResult`: `captured_at`, bounded by §4.5 |
| INSP-S3, T01, T03–T10, T12–T15 | Survive | T04 `tl insp record` keeps its flags and calls the shared functions |
| INSP T02, T11 (follow-up slice) | **Move** to forms | Built once as the generic runner; INSP gets it by registering a form source |
| PTW-S1, PTW-T00, S2–S5, T01–T16 | Survive whole | Later: one ticket for a form source on `RequestPermit` and the precaution ticks |

INSP goes from 3 pieces and 16 tickets to 3 pieces and 14. PTW stays at 5 pieces and 17. Neither waits for forms.

### 6.2 The forms path (rough)

| Slice | Pieces | Tickets | Holds |
|---|---|---|---|
| P2-FORMS first slice: engine and general forms, online | 3 | about 13 | S1 core contract `tl_core/forms/` (types, rules moved from quality, projections, source registry); S2 schema of module `forms` (`Template`, `Submission`, events, two workflows, numbering, six words); S3 commands. Tickets: `to_json_schema`, `to_surveyjs`, views, read routes, `tl form`, MCP tools, generic runner model, runner screen, form sources for quality and permits, generator, demo, docs |
| P2-FORMS-WEB: fill page | 1 | about 4 | Vendor the two MIT files with manifest rows; the fill page; policy check; card `open_path` |
| P2-FORMS-SF: store and forward | 2 | about 7 | S4 delivery route, late rules and the delivery event (sync-class code: builder tier with a human gate, never an implementer ticket); S5 service worker and outbox. Tickets: "my work today" read, needs-attention view, offline QR shell, a `node --test` step for the outbox logic, settings, runbook, demo |
| Total | **6 pieces** | **about 24 tickets** | One ADR, six to eight APPROVALS lines, two security review rows |

Order: the first slice starts after INSP C2 and PTW C2 (two real sources exist) and P2-X4 C2 (hooks). Store and
forward is last and can slip to Phase 3 without hurting the rest. Forms before INSP and PTW would delay both.

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
2. **Owner.** Read ADR-0031 and answer the decisions below. Nothing in step 1 waits for this.
3. **INSP-S2 spec** (next round): add the optional `captured_at` input and its bound. Take T02 and T11 off the INSP
   follow-up table and point them at the forms increment.
4. **Card tickets** (INSP T09, PTW T09): `open_path` is the record page now, the forms page once it exists.
5. **Plan P2-FORMS** (a planner-tier round, after ADR-0031 is accepted): the first slice of §6.2, starting after
   INSP C2, PTW C2 and X4 C2; then FORMS-WEB, then FORMS-SF. No forms schema, vendored JavaScript or `tl-web` change
   before the ADR is accepted.

### Owner decisions

| # | Question | Default |
|---|---|---|
| 1 | Accept ADR-0031: engine contract in core, Throughline's own template format, no lifecycle in the engine? | Yes |
| 2 | Vendor `survey-core` and `survey-js-ui` (MIT) into the web client as the fill renderer? It is the first large script on a client that is script-light today | Yes, for the fill page only; fall back to a server-rendered page if the security policy cannot hold |
| 3 | Server-side drafts? | No in v1; drafts stay on the device |
| 4 | May anything about a permit be queued offline (a late "suspend", a late failing gas reading)? | No; permits stay online only |
| 5 | May a phone show a cached status "as of" for non-permit records when offline? | No; offline a scan opens the form only |
| 6 | How old may a queued item be? | 72 hours (`forms.late_accept_hours`) |
| 7 | Who reviews a general submission? | A `forms` controller who is not the submitter |
