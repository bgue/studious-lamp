# tl-mod-forms

Forms (ADR-0031, ADR-0032, `docs/build-spec/module-designs/forms-eval.md`): templates, submissions with drafts and
public zero-login intake. Four record types (`forms.Template`, `forms.Submission`, `forms.IntakeCode`,
`forms.IntakeItem`) with tables `cur_forms_*`, and one operational table, `forms_intake_body`, that no event
produces.

P2-FORMS S2 holds the schema, the projectors and the names. P2-FORMS S3 holds eleven commands and the one seam that runs a
module command inside the caller's unit of work (`tl_core.services.nested.run_nested_command`). P2-FORMS S7c adds the four
intake commands (fifteen in all) and `tl_core/qr/codes.py`. Views, routes, the CLI, the tools and the intake endpoint come
later.

## Who reads what (P2-FORMS CR1)

One `confidential` source (`confidential.py`) classes a submission by its `answer_class` (null is `internal`). The subject
rows in `tl_core.confidentiality` hide a submission when its subject is hidden and an intake item when its code's context
is (two hops; a chain deeper than that stops). `OWN_CLASS_TYPES` makes the submission's own class count even when its
subject is readable. A draft (`submitted_on` null, kept or discarded) is read by its author alone; after `SubmitForm` the
class rules govern. A proposal naming a template whose class the viewer may not read is absent for them, and a draft makes
no feed card. An intake code or item with no context is not hidden by this module (S7c and T03 guard those reads).

## Commands (`module.py` `FORMS_COMMANDS`)

| Command | Word (table word) | Does |
|---|---|---|
| `DraftFormTemplate` | `forms.template.edit` (user) | company scope; a Draft, key `TPL-0001`; the field list must be clean |
| `EditFormTemplate` | `forms.template.edit` | Draft only; `title`, `fields`, `answer_class`, `intake`, `purpose`, `accepts_as` |
| `PublishFormTemplate` | `forms.template.publish` (controller) | Draft to Published; questions checked again; public needs `intake_problems` clean; sets `content_hash`, `published_on` |
| `ReviseFormTemplate` | `forms.template.edit` | Published or Retired to a new Draft, version n+1; one open Draft per lineage |
| `RetireFormTemplate` | `forms.template.publish` | Published or Draft to Retired |
| `SaveFormDraft` | `forms.submit` (user), offline draft | `template_id` starts a draft, `draft_id` continues it; answers may be partial |
| `DiscardFormDraft` | `forms.submit` | the author's own Draft; takes no number |
| `SubmitForm` | `forms.submit`, offline draft; the proposable row `propose_form_submission` | complete answers; takes the number |
| `AcceptFormSubmission` | `forms.review` (controller) | Submitted only; never the author |
| `ReturnFormSubmission` | `forms.review` | as Accept; `note` required |
| `VoidFormSubmission` | `forms.void` (controller) | Submitted, Accepted or Returned; also `Record.Voided` on the envelope |
| `IssueIntakeCode` | `forms.intake.issue` (controller) | project scope; takes `code_hash`, never a code; a Published public template (version and hash pinned); optional readable `context_id`; `heading` 1-60; `expires_on` today to today + `forms.intake.code_max_days` |
| `RevokeIntakeCode` | `forms.intake.issue` | Active only; `reason` |
| `AcceptIntakeItem` | `forms.intake.review` (controller) | Pending only; runs `command_type` (in the template's `accepts_as`, a module proposable) with the controller's `command_args` as the controller, then `IntakeItem.Accepted`, the `accept` move, body delete, `IntakeItem.Purged`; one unit |
| `RejectIntakeItem` | `forms.intake.review` | Pending only; `reason` of `spam`, `duplicate`, `not_ours`, `unclear`; the body stays for retention |

None of the four is proposable (`tests/tools/proposable_exclusions.toml`, `person acts directly`).

Generic commands: none on a template; on a submission `SetPsetValues`, `AddLink`, `AttachFile` and the link life, only
once it is submitted (`guards.submitted_or_later`).

## Messages (`errors.py`; each is a fixed text, none carries an answer)

| Constant | Text |
|---|---|
| `MSG_UNKNOWN` | no record with that id (absent, hidden, other project, another author's draft) |
| `MSG_PROJECT` | a form is filled in a project |
| `MSG_STALE` | the record changed since it was read |
| `MSG_DRAFT_SAVES` | the draft was saved as often as it may be; submit it or discard it |
| `MSG_SELF_REVIEW` | the person who filled a form may not review it |
| `MSG_NOT_FILLABLE` / `MSG_NOT_PUBLISHED` | bound or public template / template not published |
| `MSG_CODE_TAKEN` | that code is already in use (a second issue of the same hash) |
| `MSG_NOT_INTAKE` | that template is not open to public intake (not public, or bound) |
| `MSG_EXPIRY` | the expiry is in the past or beyond the days a code may last |
| `MSG_NOT_ACCEPTED_AS` | that template does not accept an item as that command |
| `MSG_ONE_DRAFT` | that template already has a version in draft |
| `FormAnswersError`, `FormTemplateError` | the rules' problem texts, joined (field ids, never an answer value) |

## Decisions D6 to D11 (as applied)

- D6 numbering at submit: the first save appends `Record.Created` with `key: null` and `Submission.DraftSaved`. `SubmitForm` of
  a draft calls `allocate_key` and appends `Record.Updated {key: [null, KEY]}`, `Submission.Submitted` and the `submit`
  transition in one unit of work. With no draft the number is taken at creation. A resubmit keeps its number; a discarded
  draft never takes one.
- D7 scope: a template is company scope, a submission project scope (`MSG_PROJECT`).
- D8 the seam runs only module `ProposableCommand`s, never core, workflow, dispatch, action or setting commands.
- D9 templates: one record per version; revise makes a Draft; publish does not retire the predecessor; a Draft is always clean.
- D10 `SaveFormDraft` and `SubmitForm` take general, Published templates; an existing draft finishes after Retired.
- D11 refusal order: scope, subject (hidden looks absent, before any answer), the actor's own submission and its state, template,
  version, save bound, answers. A continued draft is looked up before its template (the draft's author comes first).

## Decisions D15 to D18 (P2-FORMS S7c, as applied)

- D15 `tl_core.qr.codes` (frozen, pure): `ALPHABET` (32 symbols, no `I O 0 1`), `CODE_LENGTH` 16, `new_code()`,
  `normalise_code(text) -> str | None`, `code_hash(code) -> str` (sha256 hex of the normalised code; `ValueError` on a
  non-code), `grouped(code)`. This module imports it and never `tl_mod_qr`; the QR module imports it and defines none.
- D16 the server never sees a code: `IssueIntakeCode` takes `code_hash`. A caller may choose a weak code; the issuer holds
  `forms.intake.issue` and a code opens a staging door only (listed for the wave's security review).
- D17 accept takes the controller's completed `command_type` and `command_args`. The staged body is read once, for
  `on_behalf_of_claim` (`claim_name`, `claim_company`, each cleaned and at most 80 characters; `claim_phone` never copied).
  The seam sets actor, scope and source (`intake:<code id>`) and the cause (the `Received` event) and gets the controller's
  holder, so the controller needs their own word for the command. The result lists the move and purge events only: the
  `Accepted` event (the claim) stays in the ledger.
- D18 accept deletes the `forms_intake_body` row and appends `IntakeItem.Purged` in the same unit; reject keeps the body.
- An intake code takes no number, so `Record.Created` is appended with `key: null` directly (as `SaveFormDraft` does);
  `create_module_record(key=None)` would look for a numbering pattern that does not exist.

## Signed-in intake (V3-F4)

`tl intake code issue|revoke|ls` and `tl intake ls|show|accept|reject|purge`, `GET /forms/intake/codes`,
`/forms/intake/items` and `/forms/intake/items/{item_id}`, the client methods `list_intake_items` and
`get_intake_item`, and the terminal "Intake" log (palette `intake`). The code is made by the CLI (`new_code`), only its
hash is sent, and it is printed once. A controller opens an item (`show`: the answers of a Pending item), accepts it as the
record the template proposes (`accept --as SubmitForm --args-file F`, through S7c's command) or rejects it, and `purge`
removes the text of items older than `forms.intake.retention_days`. A hidden item is a missing one (`no such intake
item`); an agent is refused. The public `/i/<code>` route is not part of this piece.
