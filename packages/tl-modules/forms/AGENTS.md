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
- Every id a command is given goes through `handlers/common.load_submission` or `require_subject`: hidden, absent, other
  project and another author's draft answer one text, `MSG_UNKNOWN`, and the subject is checked before any answer (D11).
- A state move is a `by_module` transition in the same unit of work as the module's own event. The record fields and the
  state change only through the eleven commands (`FORMS_GENERIC_COMMANDS` is the short list that may touch a submission).
- The reviewer is never the author (`MSG_SELF_REVIEW`), whatever the role.
- The seam (`tl_core.services.nested`) runs only a module's `ProposableCommand`; the only forms row is `SubmitForm`. A
  stored body never names its actor.
- A new command is a `FORMS_COMMANDS` row and either a `PROPOSABLE` row or a line in `tests/tools/proposable_exclusions.toml`.
- Tests live in `tests/`; `forms_world.py` runs commands as a person would (access word, intent, handler as that viewer).
