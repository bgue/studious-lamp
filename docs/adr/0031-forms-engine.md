# ADR-0031 — Forms engine: templates as data in core, typed modules on top, store and forward by outbox

Status: Accepted (owner, 2026-11-15)
Date: 2026-11-15
Deciders: orchestrator (draft by the design evaluation); accepted by the owner on 2026-11-15 with "Yes to all" on
the seven decisions of the evaluation (decisions 13 to 16 below record the answers). New core interface
(`tl_core/forms/types.py`), a new entry-point group, a new module schema and a change to the web client, so a human
gate (§25.5) and APPROVALS lines before each merge.
Brief sections: §9 M5 and §10.5 (checklist runner), §7.1 and §9 M3 (permits), §16 (web readiness), §22 (offline),
§22.9 (mobile notes). Builds on ADR-0009, ADR-0010, ADR-0016, ADR-0030; P2-X1 (idempotency);
`specs/offline-classes.md`.
Evaluation: `docs/build-spec/module-designs/forms-eval.md`.

## Context
The owner asked (2026-11-15) whether permits and inspections are special cases of a general forms module, served by
a custom API with something like SurveyJS, with store and forward when connectivity is interrupted. INSP-S1 has
built `quality.Checklist`: a versioned, immutable list of questions held as data. Permit types carry a list of
precautions as data. Both designs list "from the phone" as later work. Without a decision each module builds its
own question shape, its own fill path on four surfaces and its own offline story. With the wrong decision a generic
engine absorbs permit safety rules that must stay typed.

## Decision

1. **A forms engine lives in core as a contract and pure functions** (`tl_core/forms/`): the template document, its
   validation, answer validation, visibility, and projections to a JSON Schema, to SurveyJS JSON and to a terminal
   runner model. It reads no table and writes no event.
2. **The engine owns no lifecycle.** No states, guards, approvals, numbering or side effects. A form is a front end
   to a typed command. Meaning (an inspection result, a gas result, what a failed answer causes) stays in the typed
   module.
3. **The template format is Throughline's own, small and closed.** Format 1 is the INSP-S1 question shape as built.
   Format 2 adds optional keys only (`section`, `help`, kinds `multi`, `date`, `photo`, `visible_when`). Conditions
   are a closed grammar of comparisons joined by `all`, `any`, `not`, at most 3 deep, over earlier fields. No
   expressions, computed values, HTML, URLs or scripts. A change past this list is a new ADR.
4. **Templates are immutable data.** A Published version never changes; a change is a new version that supersedes
   it. Every version has a content hash; a record that uses a template pins id, version and hash.
5. **Modules register form sources** under the entry-point group `throughline.form_sources`: for a record and a
   viewer, a source answers the pinned template and the command that takes the answers, or `None` for a record the
   viewer cannot see. The contract is frozen once merged.
6. **Submissions are typed events.** The client sends the bound command through the command door; the handler
   reloads the pinned template and validates everything again. The client is never trusted. General forms with no
   typed home live in a new module `forms` (`forms.Template`, `forms.Submission`).
7. **SurveyJS is the web fill renderer only.** `survey-core` and `survey-js-ui` (MIT) are vendored unedited with
   manifest rows. Survey Creator, `survey-pdf` and `survey-analytics` (commercial) are never used. SurveyJS JSON is
   generated one way and never stored.
8. **Forms are not web-only.** The terminal runner, `tl form`, and the agent tools `get_form` and
   `propose_form_submission` read the same template. Agents stay closed by default and never submit directly.
9. **Store and forward is a client outbox of commands**, delivered once to the authority with the idempotency key
   of P2-X1 through `POST /forms/deliveries`, which wraps the command dispatch. Only commands that
   `capture_allowed(type, command, node="device")` allows may be queued. Controller commands are never queued.
   Permit commands are never queued, except the closed list of decision 14. It is not replica sync and adds no
   node kind.
10. **A fact is accepted late with its own time; an act is refused if its target moved; nothing is merged.**
    `expected_version` mismatches, state guards, lost access and hidden targets refuse the delivery; the answers
    stay on the device. The device clock is a claim: it may be recorded and may make a rule stricter, and it never
    makes work more permitted.
11. **Hidden looks exactly like missing** on every forms route, and a hidden target is refused before answers are
    validated. Answers are record text, hidden through the record's subject; they never enter feeds, webhooks,
    error texts or logs.
12. **Signing off is never a form field.** A sign-off is a typed controller command on the authority. A drawn
    signature is an attachment and grants nothing.
13. **Drafts are kept on the server** (owner decision 3). `forms.Submission` has a `Draft` state written by
    `SaveFormDraft`, readable by its author only, saved on request and not per keystroke, bounded by
    `forms.draft_saves_max`. Typed records keep their own waiting states.
14. **Permit facts that only tighten may be queued** (owner decision 4): a suspend, and a gas reading that the
    server computes as a fail. A queued reading that computes as a pass is refused. Resume, issue, revalidate,
    approve and every isolation command stay online only. The list (`TIGHTENING_COMMANDS`) is closed; the device
    says the permit is not suspended for anyone else until the server answers.
15. **A phone may show a last-known status offline for non-permit records** (owner decision 5), always stamped
    "as of" and never as live, for lowest-class subjects, no older than `forms.offline_status_max_hours`. Permit,
    isolation and gas status is never cached. The scan card of ADR-0030 stays `no-store`; the lines travel with
    the forms payload.
16. **A queued item may be at most 72 hours old** (`forms.late_accept_hours`, owner decision 6), and **a general
    submission is reviewed by a `forms` controller who is not the submitter** (owner decision 7). The two MIT
    SurveyJS files are vendored for the fill page (owner decision 2).

## Consequences
- Contracts changed: new `tl_core/forms/types.py` and `rules.py` (frozen once merged); new entry-point group
  `throughline.form_sources`; new module `forms` with its schema, six access words `forms.*`, settings
  `forms.late_accept_hours`, `forms.clock_skew_max_seconds`, `forms.draft_saves_max` and
  `forms.offline_status_max_hours`, and the event `forms.Delivery.Received`; one part
  added to the subject rule in `tl_core/confidentiality.py`; a service worker and vendored scripts in `tl-web`.
  No existing event, route, setting or frozen contract changes. ADR-0030 and the scan-card contract stand.
- In flight: INSP-S1 and QR-S1 merge as built. INSP-T00, PTW-S1 and PTW-T00 are released unchanged. INSP T02 and
  T11 (the runner) move to the forms increment. INSP-S2 gains one optional input, `captured_at`.
  `validate_questions` and `validate_answers` move from `tl_mod_quality.insp_rules` to core, with re-exports.
- Tickets: a new increment in three slices (engine and general forms; web fill page; store and forward), about 6
  pieces and 29 tickets with the owner's answers, started after INSP C2, PTW C2 and P2-X4 C2. Zero-login intake
  is a fourth slice under ADR-0032 (proposed); totals are in the evaluation, §8.3.
- Gates affected: core interface; schema merge (module `forms`); settings and access words; security review of the
  delivery route, the form sources and the walks; the licence check (vendored files); the web client's content
  policy and service worker. The delivery route is sync-class code: builder tier with a human gate.
- Offline classes: `forms.Template` `none`; `forms.Submission` `draft_only` with `SubmitForm` and `SaveFormDraft`
  as its drafting commands. Permit types stay `none`, with the tightening list of decision 14 as the one
  exception; `permits.md` §4 and `specs/offline-classes.md` take one line each for it.

## Alternatives considered
| Option | Why not |
|---|---|
| No forms module; each typed module builds its own capture | Three template shapes and a fill path per module and surface; the offline client built more than once |
| A forms module for ad-hoc checklists only, typed modules untouched | A fourth shape; the outbox would carry nothing for inspections, punch or requisitions, which is where it pays |
| Permits and inspections as configured forms with a generic workflow | Moves isolation, gas, validity, separation of duties and readiness into configuration; an inner platform; safety rules must be code under review |
| Store SurveyJS JSON as the template | Open format with a string expression language, HTML and URL-loaded choices; no Python evaluator, so the server would trust the client or run Node per submission |
| JSON Forms or RJSF as the renderer | Good validation model (JSON Schema) but both need React and a bundler; the repository vendors prebuilt files and has no JavaScript build. Their JSON Schema idea is kept as a projection |
| Form.io | The renderer is MIT but heavy and built around its own server; a second platform |
| A generic `FormSubmitted` event for everything | Loses typed payloads, projections and guards; readiness and punch would parse answers |
| Store and forward as Phase 3 replica sync now | Needs the local segment, merge policies and a second node kind; the outbox needs none of them and its item shape is reused later |
| Queue every permit command, or none | None was the draft default; the owner chose the narrow middle (decision 14): only facts that tighten. Anything that could make work more permitted on a device's word stays refused |
| Drafts on the device only | The draft default; the owner chose server drafts (decision 13) so a form started on one device can be finished on another |
| A forms write route of its own for online use | A second way to write; the command door already carries access checks and idempotency |
