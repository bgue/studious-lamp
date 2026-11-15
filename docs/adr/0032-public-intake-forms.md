# ADR-0032 — Public intake forms: zero-login requests and sign-on sheets, staged for a controller

Status: Accepted (owner, 2026-11-15: yes to all three questions in forms-eval §8.4: the ADR as written, an optional phone field kept at most 30 days unless accepted, poster permit sign-on is attendance only until a signed-in controller confirms)
Date: 2026-11-15
Deciders: orchestrator (draft by the forms design evaluation); the owner decides. A new route with no sign-in, a
new operational table, new settings and access words, so a human gate (§25.5), a security review and APPROVALS
lines before each merge.
Brief sections: §16 (web readiness), §18.11 (external parties), §22.9 (mobile notes), §25.5 (gates). Builds on
ADR-0009 (accounts, rate limits), ADR-0016 (confidentiality), ADR-0030 (QR codes), ADR-0031 (forms engine), P2-X1.
Evaluation: `docs/build-spec/module-designs/forms-eval.md` §8.

## Context
The owner asked (2026-11-15): "Make sure we can serve minimalist forms via nothing but a uri/qr (ie zero-login) for
the simplest, broadest cases (eg. 'i need an X' or 'sign on to X') - these would all go through a staging
controller inbound." Most people on a site have no account: a labourer who needs a scaffold altered, a visitor at a
toolbox talk, a delivery driver. ADR-0031 serves forms to signed-in people only, and ADR-0030 decision 2 refuses
any anonymous status page. Both stand. What is added here is the opposite direction only: a stranger may **hand
something in**. The product tells a stranger nothing, and nothing a stranger writes changes a record until a
signed-in controller decides.

## Decision

1. **Intake is write-only.** The public page shows the template's title, a heading the issuer typed, and the fields.
   It shows no record, key, state, name, count, earlier submission or prefilled value, and it takes no lookup, no
   autocomplete and no search. After a submit it shows one fixed page with a short receipt word. There is no page
   that answers "what happened to my request". ADR-0030 decision 2 is unchanged: status needs a sign-in.
2. **Only a template flagged `intake: public` qualifies**, and publishing one is refused unless it fits a closed
   profile of format 2: at most 8 fields; kinds `text` (≤ 280 characters), `choice` and `number` (a quantity, with
   bounds); no `photo`, no `visible_when`, no `date`, no `multi`. Three reserved
   field ids mark typed-in claims: `claim_name`, `claim_company`, `claim_phone` (all optional to the template).
   The template names `purpose` (`request` or `sign_on`) and `accepts_as`, a closed list of the typed commands a
   controller may turn an item into. A public template is company reference data and carries no project text.
3. **Addressing is an intake code**: 80 random bits in the 16-character alphabet of ADR-0030, stored only as its
   SHA-256, shown once at print (the generate, normalise and hash functions are lifted into `tl_core/qr` so `forms`
   does not import the `qr` module), in the ledgered record `forms.IntakeCode` (`IntakeCode.Issued`, `.Revoked`). It is
   a distinct record and a distinct path, `<api.public_base_url>/i/<code>`, so a scan code never opens an intake
   page and an intake code never opens a status card. The path is outside `/web` on purpose: the session cookie is
   `Path=/web`, so the intake route never learns who is signed in and sets no cookie. A code binds the template
   id, version and hash, a target context (project, area, permit, IWP or another record) and a controller role; the
   holder sees none of that. The heading (≤ 60 characters) is typed by the issuer, never copied from the record,
   and the issue screen says it is public. Every code expires (default 30 days, at most
   `forms.intake.code_max_days`); a sign-on sheet is normally issued for one shift.
4. **One neutral answer for every dead code.** Unknown, malformed, revoked, expired, a retired template and
   intake switched off give the same 404 page, byte for byte, on GET and on POST. Misses are counted per address.
5. **Every submission is a staged item, never a command on the target.** Receipt writes one event,
   `forms.IntakeItem.Received` `{item_id, code_id, template pin, body_mac, body_bytes, received_at}`, as the
   service actor `svc:intake` with source `intake:<code id>`. The text the stranger typed is **not in the event**:
   it is held in an operational table, `forms_intake_body` (like `idempotency_key`: no event produces it, a rebuild
   never clears it, the archive, the lake, feeds and webhooks never read it), so it can be purged. `body_mac` is an
   HMAC-SHA-256 under a random per-item salt kept in the body row and purged with it: a plain hash of a name and a
   phone number could be guessed back from the permanent event. Nothing is
   validated against the target, so a refusal can never describe the target.
6. **The inbound queue is its own stream, not the proposal queue.** A proposal (`services/proposals.py`) is a
   complete typed command, filed by a named agent, run to the end against the target before it is stored (an
   anonymous filer would get the handler's refusal: an oracle), and its whole payload is a permanent event (a
   stranger's phone number could never be removed). It has no merge and no person matching, and its budget and
   attribution are agent-shaped in a frozen contract. Intake reuses the proposal queue's **meaning of accept** and
   its review design (`specs/agent-first.md` §3.3) and nothing of its storage.
7. **A controller decides, signed in.** A person holding `forms.intake.review` who can read the code's context
   (an item is hidden through that context's subject, as any record text) does one of:
   - **Accept as** one command from the template's `accepts_as`: the staged answers prefill the command, the
     controller edits and completes it, and it runs through the command door as the controller, needing the
     controller's own word for that command. Actor = the controller, source `intake:<code id>`, cause = the
     Received event. The claim is recorded as `on_behalf_of_claim` `{name, company}` on `IntakeItem.Accepted`
     **only**, always labelled as a claim; no other module's command or event gains a field, and a reader finds the
     claim from the typed event through its cause. The command's events and `IntakeItem.Accepted` commit together,
     through the seam forms piece S3 owns for running a command inside the caller's unit of work (the shape
     `accept_proposal` uses). A refusal rolls back and leaves the item pending.
     With no typed home the command is `SubmitForm`; for owner decision 7 of ADR-0031 the submitter is the claimant,
     so the accepting controller is the reviewer.
   - **Reject** with a fixed reason word (`spam`, `duplicate`, `not_ours`, `unclear`); no free text is needed.
   Batch accept and reject are an ordered loop of single units, as for proposals. Merging duplicates into one
   item (`IntakeItem.Merged`) is deferred; in v1 a duplicate is rejected as `duplicate`.
8. **A name on a sign-on is a claim, not a sign-in.** A sign-on creates no account, session, word or party scope,
   proves no identity, and never satisfies a guard that asks for a signed-in actor. Matching a claim to a known
   person is deferred; when built, the match (`matched_person_id`, `matched_by`) lives on `IntakeItem.Accepted`
   only and candidates are computed only inside the controller's view.
9. **A public sign-on is attendance only.** Accepted, it records "claimed present, confirmed by <controller>" on
   a toolbox talk, an induction or a permit briefing. It is never a crew member's own acceptance of a permit's
   conditions and counts toward no permit guard. Where a procedure needs a person's own binding sign-on, that
   person signs in, or the permit authority records it by a typed permit command as their own attested act
   (the countersigned paper sheet). What a company accepts as a signature stays the company's procedure; the
   product's default is non-binding. The submit page says so in one line.
10. **Abuse controls, all in-house.** Per address and per code hourly limits through `tl_api.ratelimit` (address
    rules of ADR-0009 §6, `TL_TRUSTED_PROXY_HEADER`), checked before the body is read and before the code is looked
    up, with one 429 page. The per-code counter is keyed on the presented code whether or not it is live, so a 429
    never tells a live code from a dead one. A pending cap per code, past which the page says the sheet is full; a
    body cap of 8 KB; a hidden honeypot field (a filled one gets the normal thank-you page and stores nothing); no
    captcha and no third-party resource. A minimum fill time is not built in v1; if it is added, the render time
    is signed with the item key. A front-door limiter is still required, as for sign-in.
11. **Privacy.** Only the template's fields are stored; the address is used for the limit and not stored with the
    item. Bodies of rejected and undecided items are purged after
    `forms.intake.retention_days`, accepted ones at once (the accepted text now lives in the typed event the
    controller wrote); `IntakeItem.Purged` records it. Staged text is shown to holders of `forms.intake.review`
    only and never enters feeds, webhooks, search, exports, error texts, logs or an agent's context; a feed card
    to the controller role carries a count and the heading only. A purge is only as good as the backups: the
    runbook bounds the retention of backups that hold the body table by the same setting. Photos are not taken in
    v1; a later decision must re-encode on receipt (dropping EXIF), quarantine until accepted and name its image
    library.
12. **Staged text is hostile until accepted.** It is stored as plain text, normalised, with control and
    bidirectional characters removed at receipt (terminal escapes), escaped on every surface, never made into a
    link, guarded against formula injection in any export, and closed to agents in v1 (no intake tool is listed).
13. **The page is plain HTML and works with no script.** No SurveyJS on `/i/`. Headers: `no-store`,
    `no-referrer`, `X-Robots-Tag: noindex`, a policy of `default-src 'none'` plus the form's own style. The code is
    removed from access logs for `/i/` by the filter that serves `/web/q/`. A hidden random key, minted when the
    page is rendered, makes the item id (a hash of code id and key), so a double tap or a refresh writes once.
14. **No store and forward without a login in v1** (cut by the plan check). With no signal the person tells the
    supervisor. If it is built with the Phase 3 outbox: the receipt time is the only time, a code that died
    meanwhile gives the neutral answer, and revocation is absolute.
15. **Off by default.** `forms.intake.enabled` is a platform setting; while off, `/i/` answers as decision 4.

## Consequences
- Contracts changed: module `forms` gains `forms.IntakeCode` and `forms.IntakeItem` (events `IntakeCode.Issued`,
  `.Revoked`; `IntakeItem.Received`, `.Accepted`, `.Rejected`, `.Purged`), the operational table
  `forms_intake_body`, the service actor `svc:intake` and the reserved source `intake:<code id>`; template keys
  `intake`, `purpose`, `accepts_as` and the reserved claim ids (rules in `tl_core/forms/rules.py`); words
  `forms.intake.issue` and `forms.intake.review` (both controller); settings `forms.intake.enabled` (off),
  `.rate_per_address_per_hour` (20), `.rate_per_code_per_hour` (60), `.pending_per_code_max` (200),
  `.retention_days` (30), `.code_max_days` (90); a job kind for the purge; a public route family `/i/` in `tl-web`; one
  additive path argument on the label renderer (P2-QR T02) so a poster prints `/i/<code>`; one part added to the
  subject rule for intake items, added by the wave's one confidentiality piece (CONF-ROWS, forms-eval §8.3); the
  lift of the code functions into `tl_core/qr`. No existing event, route or frozen contract changes. ADR-0030 and ADR-0031 stand.
- Offline classes: `forms.IntakeCode` and `forms.IntakeItem` are `none`; every controller act on them is central.
- Surfaces: the public page; a poster (`tl intake label`, heading, QR and grouped code, no state); the controller
  queue in the terminal (an "Intake" log beside the proposal queue, `tui-layout` applies), the CLI (`tl intake
  ls|show|accept|reject`, `tl intake code issue|revoke|ls`) and signed-in JSON routes under
  `/forms/intake/`. No MCP tool in v1. A web queue page is later.
- Tickets: a slice P2-FORMS-INTAKE, **held until the owner accepts this ADR and the phone-number default**, after
  the first forms slice and QR C2; it does not need the SurveyJS fill page. 2 pieces and about 7 tickets: S6 (route,
  `/i/` mount, staging table, limits, settings, purge job) and S7 (schema and commands), S7 folded into forms S2 if
  this ADR is accepted before S2 is specified (forms-eval §8.3).
- Gates affected: security review of the public route, the staging table, the purge and the limits (builder tier
  with a human gate whose approver is the owner, never an implementer ticket; the review row lists its commit
  range); schema merge; settings and words; the five-reader walk on the
  signed-in queue routes plus an anonymous reader on `/i/`; the web client's first route with no session.

## Alternatives considered
| Option | Why not |
|---|---|
| File each submission as a proposal | See decision 6: precheck is an oracle, the payload is permanent, no merge or matching, agent-shaped frozen contract; spam would bury agent proposals |
| Let a public submission run the typed command directly as a service actor | An anonymous write to project records; no viewer, no separation of duties, guards answered to a stranger |
| Put the submitted text in the Received event | Events are permanent; a stranger's name and phone number, or abuse text, could never be removed |
| Reuse `qr.ScanCode` with a `kind` field | Changes a contract frozen by QR-S1, and one lookup table for both invites a status page reachable by an intake code |
| A guest link (Phase 3 I8) per person | A guest link is addressed to one known party, single-purpose and runs one command; a poster is for anyone and runs none. Both are kept |
| Captcha | A third party on a site safety page, poor on gloves and bad signal; the limits and the controller are the control |
| Show a status or a tracking page for the receipt word | Makes the receipt a bearer link to project state; the answer comes from a person on site |
| SurveyJS on the public page | Not needed for 8 flat fields; a large script on the one page strangers reach |
| Let agents triage staged text | Untrusted text written by anyone, read by a tool that can file proposals; closed until a separate decision |
