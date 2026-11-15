# tl-mod-forms

Forms (ADR-0031, ADR-0032, `docs/build-spec/module-designs/forms-eval.md`): templates, submissions with drafts and
public zero-login intake. Four record types (`forms.Template`, `forms.Submission`, `forms.IntakeCode`,
`forms.IntakeItem`) with tables `cur_forms_*`, and one operational table, `forms_intake_body`, that no event
produces.

P2-FORMS S2 holds the schema, the projectors and the names. P2-FORMS S3 (this piece) holds the eleven commands and the
one seam that runs a module command inside the caller's unit of work (`tl_core.services.nested.run_nested_command`).
Views, routes, the CLI, the tools and the intake endpoint come later.

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
