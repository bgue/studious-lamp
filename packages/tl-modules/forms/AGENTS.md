# AGENTS.md: tl-mod-forms

Rules of the root `AGENTS.md` apply. Local rules:

- Tables `cur_forms_*` are generated; never hand-write DDL (use `ddl_for`).
- `forms_intake_body` is operational: no projector writes it, a rebuild never clears it, and the archive, the lake,
  feeds and webhooks never read it. Only the intake endpoint and the purge job (S6, S7c) write it.
- No event, field, log line or error text holds an intake code, a salt or a body. Intake codes appear as hashes.
- `IntakeItem.Received` carries no typed text. No payload slot is named `code`, `token`, `url`, `body` or `salt`.
- Events are immutable; a withdrawn form is a `Submission.Voided` event, never an edit.
- A draft submission takes no number until it is submitted (D6): the first save has `key: null`; `SubmitForm` allocates.
- Answers are confidential text: never put them in a log line, an error text, a feed card or a webhook body. Only
  `Submission.DraftSaved` and `Submission.Submitted` hold them. A problem text names field ids, never a value (and
  `handlers/submission._safe` drops an id or key an answer made up).
- Visibility (P2-FORMS CR1; rows in `tl_core.confidentiality`, source in `confidential.py`): a submission is hidden when its
  subject is (`SUBJECT_LINKS`: submission, intake item through its code, intake code through its context; two hops, a deeper
  chain stops); its `answer_class` (null is `internal`) also hides it from a viewer who may not read that class, whatever
  its subject (`OWN_CLASS_TYPES`); a draft (`submitted_on` null, kept or discarded) is read by its author alone, the
  `system` viewer excepted (jobs and rebuilds; no reader serves a person through it). A proposal for a template whose class
  the viewer may not read is absent for them (`hidden_answer_templates`). A draft and a discarded draft make no feed card.
- An intake code or item with no `context_id` is its own subject and no source classes it: this module does not hide it.
  The controller words guard those reads (S7c, T03). Do not invent a class column.
- Every id a command is given goes through `handlers/common.load_submission` or `require_subject`: hidden, absent, other
  project and another author's draft answer one text, `MSG_UNKNOWN`, and the subject is checked before any answer (D11).
- A state move is a `by_module` transition in the same unit of work as the module's own event. The record fields and the
  state change only through the fifteen commands (`FORMS_GENERIC_COMMANDS` is the short list that may touch a submission).
- The reviewer is never the author (`MSG_SELF_REVIEW`), whatever the role.
- The seam (`tl_core.services.nested`) runs only a module's `ProposableCommand`; the only forms row is `SubmitForm`. A
  stored body never names its actor.
- Intake (S7c): codes come from `tl_core.qr.codes` (never redefine them, never import `tl_mod_qr`); `IssueIntakeCode` takes a
  hash, the server never holds a code. `AcceptIntakeItem` runs the controller's `command_args` (never the staged body) through
  the seam with the controller's holder, reads the body once for the claim (name, company; never the phone), then deletes
  the body row and appends `Purged` in the same unit. Texts of the four commands (`MSG_CODE_TAKEN`, `MSG_NOT_INTAKE`,
  `MSG_EXPIRY`, `MSG_NOT_ACCEPTED_AS`, `MSG_UNKNOWN`) never carry a body, claim, code, hash or command argument. An id the actor
  may not read, an absent id and another project answer `MSG_UNKNOWN` before any state or argument.
- A new command is a `FORMS_COMMANDS` row and either a `PROPOSABLE` row or a line in `tests/tools/proposable_exclusions.toml`.
- Tests live in `tests/`; `forms_world.py` runs commands as a person would (access word, intent, handler as that viewer).
